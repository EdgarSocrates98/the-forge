"""Context budget audit (cycle 16.1, FRENTE D §8.5).

``theforge context budget`` measures — from the filesystem, never from
assumed host behavior — how many bytes each context category costs in a
workspace: permanent instructions (L0), skill metadata vs. skill bodies,
agent specs, knowledge, rules, the MCP config surface, cached retrieval
fingerprints, run evidence and receipts history.

Two honesty rules:

- **bytes are measured** (real file sizes, bounded walk); **tokens are
  estimated** — a documented heuristic, always labeled ``estimated`` with
  its method and confidence. The core never fabricates ``observed``
  tokens: hosts that meter real token usage report it through their own
  telemetry.
- categories that are not observable offline (``tool_output``) report
  ``unmeasured`` with a reason, never an invented zero.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

BUDGET_SCHEMA: Final = "theforge/ContextBudget/v1"

MAX_FILES: Final = 8_192
"""Hard bound on files walked per audit — a pathological tree reports
``truncated`` instead of scanning forever."""

_FRONTMATTER_MAX: Final = 65_536
"""Only the head of a SKILL.md is read to split metadata from body."""

# Host asset dirs that carry skills (project scope). Mirrors
# ``install/render.py`` + installkit ``_host_dirs`` — the install surface,
# declared here for measurement, never for routing.
SKILL_DIRS: Final[tuple[str, ...]] = (
    ".claude/skills",
    ".devin/skills",
    ".agents/skills",
    ".github/skills",
)
AGENT_DIRS: Final[tuple[str, ...]] = (
    ".claude/agents",
    ".devin/agents",
    ".agents/agents",
    ".codex/agents",
    ".github/agents",
)
KNOWLEDGE_DIRS: Final[tuple[str, ...]] = (".forge/context",)
RULES_HINT: Final = "rules"
RUNS_DIR: Final = ".forge/runs"
MEMORY_DIR: Final = ".forge/memory"
RECEIPTS_DIR: Final = ".forge/install/receipts"
PERMANENT_DOCS: Final[tuple[str, ...]] = ("AGENTS.md", "CLAUDE.md", "AGENT_PROTOCOL.md")

TOKEN_METHOD: Final = "utf-8 bytes / 4 — rough heuristic, no tokenizer"
TOKEN_CONFIDENCE: Final = "low"


@dataclass
class _Cat:
    """One category accumulator."""

    bytes: int = 0
    files: int = 0
    note: str | None = None


@dataclass
class _Walk:
    files_seen: int = 0
    overflow: bool = False


def _iter_files(base: Path, walk: _Walk) -> Iterator[Path]:
    """Bounded, symlink-free walk — files only, never follows links."""
    if not base.is_dir() or base.is_symlink():
        return
    stack = [base]
    while stack:
        current = stack.pop()
        try:
            entries = sorted(current.iterdir(), key=lambda e: e.name)
        except OSError:
            continue
        for entry in entries:
            try:
                if entry.is_symlink():
                    continue
                if entry.is_dir():
                    stack.append(entry)
                    continue
                if not entry.is_file():
                    continue
            except OSError:
                continue
            walk.files_seen += 1
            if walk.files_seen > MAX_FILES:
                walk.overflow = True
                return
            yield entry


def _measure_dir(
    base: Path,
    walk: _Walk,
    cat: _Cat,
    *,
    include: Callable[[Path], bool] | None = None,
) -> None:
    for path in _iter_files(base, walk):
        if include is not None and not include(path):
            continue
        try:
            cat.bytes += path.stat().st_size
            cat.files += 1
        except OSError:
            continue


def _frontmatter_bytes(path: Path) -> int:
    """Bytes of the YAML frontmatter block in a SKILL.md (0 when absent)."""
    try:
        head = path.read_bytes()[:_FRONTMATTER_MAX]
    except OSError:
        return 0
    if not head.startswith(b"---"):
        return 0
    close = head.find(b"\n---", 3)
    if close < 0:
        return 0
    # include the closing fence line
    end = head.find(b"\n", close + 4)
    return (end + 1) if end >= 0 else close + 4


def context_budget(root: Path) -> dict[str, Any]:
    """Per-category context cost of the workspace at ``root``.

    Pure read + stat — bounded, offline, deterministic. ``root`` is the
    workspace root (the audit scans only inside it; the fingerprint cache
    lives in the user cache dir and is matched by the same root digest the
    store uses).
    """
    root = Path(root).resolve()
    cats: dict[str, _Cat] = {name: _Cat() for name in CATEGORY_ORDER}
    per_forge: dict[str, dict[str, int]] = {}
    walk = _Walk()

    # --- L0 permanent instructions ------------------------------------
    permanent_docs: list[dict[str, Any]] = []
    for name in PERMANENT_DOCS:
        path = root / name
        size = 0
        if path.is_file() and not path.is_symlink():
            try:
                size = path.stat().st_size
            except OSError:
                size = 0
        if size or path.is_file():
            cats["permanent_instructions"].bytes += size
            cats["permanent_instructions"].files += 1
            permanent_docs.append({"file": name, "bytes": size})

    # --- skill metadata vs. body ---------------------------------------
    for rel in SKILL_DIRS:
        base = root / rel
        for path in _iter_files(base, walk):
            try:
                size = path.stat().st_size
            except OSError:
                continue
            if path.name == "SKILL.md":
                meta = _frontmatter_bytes(path)
                cats["skill_metadata"].bytes += meta
                cats["skill_metadata"].files += 1
                body = size - meta
            else:
                body = size
            cats["skill_body"].bytes += body
            cats["skill_body"].files += 1

    # --- agent specs ----------------------------------------------------
    for rel in AGENT_DIRS:
        _measure_dir(root / rel, walk, cats["agents"])

    # --- knowledge / discovery layer ------------------------------------
    ctx_dir = root / ".forge" / "context"
    for path in _iter_files(ctx_dir, walk):
        try:
            size = path.stat().st_size
        except OSError:
            continue
        cats["knowledge"].bytes += size
        cats["knowledge"].files += 1
        rel = path.relative_to(ctx_dir).as_posix()
        if rel.startswith("capabilities/") and rel.endswith(".json"):
            fid = rel.rsplit("/", 1)[-1][: -len(".json")]
            per_forge[fid] = {"capability_manifest_bytes": size}
    # skill/knowledge payloads shipped inside host dirs (…/knowledge/)
    for rel in SKILL_DIRS + AGENT_DIRS:
        base = root / rel
        for path in _iter_files(base, walk):
            if RULES_HINT in path.parts:
                continue  # counted under rules
            if "knowledge" in path.parts:
                try:
                    size = path.stat().st_size
                except OSError:
                    continue
                cats["knowledge"].bytes += size
                cats["knowledge"].files += 1

    # --- rules ------------------------------------------------------------
    for rel in SKILL_DIRS + AGENT_DIRS:
        base = root / rel
        for path in _iter_files(base, walk):
            if RULES_HINT not in path.parts:
                continue
            try:
                size = path.stat().st_size
            except OSError:
                continue
            cats["rules"].bytes += size
            cats["rules"].files += 1

    # --- MCP tools surface ------------------------------------------------
    mcp_file = root / ".mcp.json"
    if mcp_file.is_file() and not mcp_file.is_symlink():
        try:
            cats["mcp_tools"].bytes += mcp_file.stat().st_size
            cats["mcp_tools"].files += 1
        except OSError:
            pass
        doc = None
        try:
            doc = json.loads(mcp_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            doc = None
        servers = (doc or {}).get("mcpServers") if isinstance(doc, dict) else None
        cats["mcp_tools"].note = (
            f"{len(servers)} declared server(s); tool schema bytes are "
            "unverified without a handshake (`install mcp-verify`)"
            if isinstance(servers, dict)
            else "mcp config present but unreadable/unparsed"
        )
    else:
        cats["mcp_tools"].note = "no .mcp.json at the workspace root"

    # --- tool output: honestly unmeasured ---------------------------------
    cats["tool_output"].note = (
        "not observable offline — provider tool output is a runtime "
        "property; the core never invents a figure"
    )

    # --- retrieved code (fingerprint cache, observed bytes) ---------------
    fp = _fingerprint_cache(root)
    if fp is not None:
        cats["retrieved_code"].bytes = fp[0]
        cats["retrieved_code"].files = fp[1]
        cats["retrieved_code"].note = (
            "sum of sizes in the last run's fingerprint cache "
            "(measured from the cache document — what was hashed, "
            "not a live read)"
        )
    else:
        cats["retrieved_code"].files = -1  # sentinel: unmeasured, not a real 0
        cats["retrieved_code"].note = (
            "no fingerprint cache for this root — nothing retrieved yet or cache disabled"
        )

    # --- evidence + history -----------------------------------------------
    _measure_dir(root / RUNS_DIR, walk, cats["evidence"])
    _measure_dir(root / MEMORY_DIR, walk, cats["history"])
    _measure_dir(root / RECEIPTS_DIR, walk, cats["history"])

    categories: dict[str, dict[str, Any]] = {}
    total = 0
    for name in CATEGORY_ORDER:
        cat = cats[name]
        # tool_output is never observable offline — it stays unmeasured;
        # every filesystem category is measured (an empty dir is a real 0).
        measured_bytes = cat.bytes if name != "tool_output" else None
        if measured_bytes is not None:
            total += measured_bytes
        unmeasured = name == "tool_output" or cat.files < 0
        categories[name] = {
            "bytes": None if unmeasured else measured_bytes,
            "files": None if unmeasured else cat.files,
            "state": "unmeasured" if unmeasured else "measured",
            "note": cat.note,
            "estimated_tokens": _est_tokens(None if unmeasured else measured_bytes),
        }
        if walk.overflow:
            categories[name]["truncated"] = True

    return {
        "schema": BUDGET_SCHEMA,
        "root": str(root),
        "categories": categories,
        "permanent_docs": permanent_docs,
        "per_forge": dict(sorted(per_forge.items())),
        "total": {
            "bytes": total,
            "estimated_tokens": _est_tokens(total),
            "method": TOKEN_METHOD,
            "confidence": TOKEN_CONFIDENCE,
            "kind": "estimated",
        },
        "files_scanned": walk.files_seen,
        "truncated": walk.overflow,
        "limits": {
            "max_files": MAX_FILES,
            "frontmatter_read_bytes": _FRONTMATTER_MAX,
        },
        "notes": [
            "bytes are measured file sizes; tokens are estimated "
            f"({TOKEN_METHOD}) and never reported as observed",
            "categories the host does not expose stay 'unmeasured' "
            "— an honest state, never a fabricated zero",
            "permanent_instructions = installed L0 docs (AGENTS.md / "
            "CLAUDE.md / AGENT_PROTOCOL.md); capability manifests are "
            "per-forge bytes under .forge/context (see per_forge)",
        ],
    }


def _est_tokens(byte_count: int | None) -> dict[str, Any] | None:
    """Estimated tokens for ``byte_count`` — always labeled, never observed."""
    if byte_count is None:
        return None
    return {
        "tokens": max(1, round(byte_count / 4)) if byte_count else 0,
        "kind": "estimated",
        "method": TOKEN_METHOD,
        "confidence": TOKEN_CONFIDENCE,
    }


def _fingerprint_cache(root: Path) -> tuple[int, int] | None:
    """``(bytes, entries)`` fingerprinted by the last run for this root.

    Resolves the same cache path ``FingerprintStore`` uses
    (``user_cache_dir()/context/<digest12>.json``); ``None`` when absent
    or unreadable — an unverified state, not a zero.
    """
    from theforge.registry.config import user_cache_dir

    digest = hashlib.sha256(root.as_posix().encode("utf-8")).hexdigest()[:12]
    path = user_cache_dir() / "context" / f"{digest}.json"
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    entries = doc.get("entries") if isinstance(doc, dict) else None
    if not isinstance(entries, dict):
        return None
    total = 0
    count = 0
    for entry in entries.values():
        if isinstance(entry, dict) and isinstance(entry.get("size"), int):
            total += entry["size"]
            count += 1
    return total, count


CATEGORY_ORDER: Final[tuple[str, ...]] = (
    "permanent_instructions",
    "skill_metadata",
    "skill_body",
    "agents",
    "knowledge",
    "rules",
    "mcp_tools",
    "tool_output",
    "retrieved_code",
    "evidence",
    "history",
)


__all__ = [
    "BUDGET_SCHEMA",
    "CATEGORY_ORDER",
    "MAX_FILES",
    "context_budget",
]
