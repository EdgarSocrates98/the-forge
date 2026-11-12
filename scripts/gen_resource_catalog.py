"""Generate typed ``resources`` entries for a forge's ``forge.agentic.json``.

Scans conventional resource directories (skills, agents, knowledge, rules,
contracts, evals, examples, fixtures, protocols) and writes additive
``resources`` entries — never removes existing manifest fields. Idempotent:
re-running replaces the generated set with the current scan.

Usage:
    python scripts/gen_resource_catalog.py <checkout> [<checkout>...]
    python scripts/gen_resource_catalog.py --check <checkout>   # drift only
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

KIND_DIRS: list[tuple[str, tuple[str, ...], str]] = [
    # (kind, candidate dirs in priority order, resource_class)
    ("skill", ("skills", ".claude/skills", ".agents/skills", ".devin/skills"), "agentic"),
    ("agent", ("agents", ".claude/agents", ".agents/agents",
               "src/*/installation/assets/agents"), "agentic"),
    ("knowledge", ("knowledge", "docs/knowledge"), "read-only"),
    ("rule", ("rules",), "policy"),
    ("contract", ("contracts", "schemas"), "validation"),
    ("eval", ("evals", "evaluation"), "validation"),
    ("example", ("examples",), "read-only"),
    ("fixture", ("fixtures", "tests/fixtures"), "test-only"),
    ("protocol", ("protocols",), "agentic"),
]

# Kinds whose resource is the *collection unit* (top-level file or dir),
# not every nested file — keeps manifests bounded and honest.
COLLECTION_KINDS = {"rule", "contract", "eval", "example", "fixture", "protocol"}

TEXT_EXTS = {".md", ".yaml", ".yml", ".json", ".py", ".txt", ".toml"}
FMT = {".md": "markdown", ".yaml": "yaml", ".yml": "yaml", ".json": "json",
       ".py": "python", ".txt": "text", ".toml": "toml"}
SKIP_DIRS = {"__pycache__", ".pytest_cache", "node_modules", ".git"}


def _resolve_candidates(root: Path, kind: str) -> list[tuple[Path, str]]:
    """First existing conventional dir for ``kind``; ``*`` expands to packages."""
    for cand in KIND_DIRS:
        if cand[0] != kind:
            continue
        for rel in cand[1]:
            bases = sorted(root.glob(rel)) if "*" in rel else [root / rel]
            for base in bases:
                if base.is_dir():
                    return [(base, rel)]
    return []


def _scan_dir(root: Path, kind: str, rclass: str) -> list[dict[str, Any]]:
    """One entry per SKILL.md / file / collection unit in the first existing dir."""
    found = _resolve_candidates(root, kind)
    if not found:
        return []
    entries: list[dict[str, Any]] = []
    for base, _rel in found:
        if kind == "skill":
            items = sorted(
                p for p in base.iterdir()
                if p.is_dir() and (p / "SKILL.md").is_file()
            )
            entries += [
                {"id": p.name, "kind": "skill",
                 "location": p.relative_to(root).as_posix() + "/SKILL.md"}
                for p in items
            ]
        elif kind == "agent":
            items = sorted(p for p in base.glob("*.md"))
            entries += [
                {"id": p.stem, "kind": "agent",
                 "location": p.relative_to(root).as_posix()}
                for p in items
            ]
        elif kind in COLLECTION_KINDS:
            for p in sorted(base.iterdir()):
                if p.name in SKIP_DIRS:
                    continue
                entries.append({
                    "id": p.relative_to(root).as_posix(),
                    "kind": kind,
                    "location": p.relative_to(root).as_posix(),
                    "format": FMT.get(p.suffix) if p.is_file() else None,
                })
        else:
            for p in sorted(base.rglob("*")):
                if any(part in SKIP_DIRS for part in p.parts):
                    continue
                if not p.is_file() or p.suffix not in TEXT_EXTS:
                    continue
                loc = p.relative_to(root).as_posix()
                entries.append({
                    "id": loc,
                    "kind": kind,
                    "location": loc,
                    "format": FMT.get(p.suffix),
                })
        for e in entries:
            e["resource_class"] = rclass
    return entries


def generate(root: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for kind, _dirs, rclass in KIND_DIRS:
        out.extend(_scan_dir(root, kind, rclass))
    # Stable identity must be unique (catalog §9.4): when a name exists as
    # two kinds (e.g. skill + agent twin), keep the skill's bare id and
    # qualify the later kinds — never rename the skill.
    seen: dict[str, int] = {}
    for e in out:
        if e["id"] in seen:
            e["id"] = f"{e['kind']}:{e['id']}"
        seen[e["id"]] = seen.get(e["id"], 0) + 1
    return [
        {k: v for k, v in e.items() if v is not None and v != []}
        for e in out
    ]


def main(argv: list[str]) -> int:
    check = "--check" in argv
    roots = [Path(a) for a in argv if a != "--check"]
    rc = 0
    for root in roots:
        manifest_path = root / "forge.agentic.json"
        if not manifest_path.is_file():
            print(f"{root.name}: no forge.agentic.json — skipped")
            continue
        doc = json.loads(manifest_path.read_text(encoding="utf-8"))
        resources = generate(root)
        if check:
            if doc.get("resources") != resources:
                declared = len(doc.get("resources", []))
                print(
                    f"{root.name}: resources drift "
                    f"({declared} declared vs {len(resources)} scanned)"
                )
                rc = 1
            else:
                print(f"{root.name}: {len(resources)} resources in sync")
            continue
        doc["resources"] = resources
        manifest_path.write_text(
            json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print(f"{root.name}: {len(resources)} resources declared")
    return rc


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
