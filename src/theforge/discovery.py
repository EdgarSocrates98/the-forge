"""Universal specialist discovery (lf-0027, PHASE 2).

Resolves sibling specialists from every place one can legitimately exist,
cheap sources first:

1. ``registry``        — the provider registry (``providers.toml`` entries;
   ``describe``/``health`` through the governed Forge Protocol transport).
2. ``install-receipt`` — ``~/.forge/installations/<id>.json`` manifests.
3. ``forge-cli``       — ``~/.forge-cli/forges/state.json`` + per-forge
   ``install.json`` receipts (read-only; forge-cli is the only writer).
4. ``checkout``        — workspace members carrying ``forge.json`` (may be
   git checkouts; git presence is *not* required — see ``configured-path``).
5. ``configured-path`` — paths the user declared explicitly in
   ``discovery.toml`` (user config dir and project ``.forge/config/``); a
   ``forge.json`` there is enough, no ``.git`` needed — this is the
   no-git-checkout path.
6. ``package``         — installed distributions via ``importlib.metadata``
   (name/version/``Requires-Python``/file list — metadata reads only, never
   an arbitrary command from an untrusted source).
7. ``entry-point``     — ``theforge.specialists`` entry points and
   ``console_scripts`` matching a specialist's declared cli/binary.
8. ``bundled-manifest``— ``forge.capabilities.json`` /
   ``forge.agentic.json`` shipped inside a package or at a checkout root.
9. ``mcp``             — an ``mcp`` block in an install manifest, or a
   ``.mcp.json`` server registration naming the specialist.

DISCOVERED is not VERIFIED. Discovery reports where a specialist was *seen*;
verification additionally requires, through an existing governed path: a
version handshake (registry ``describe`` or a typed-argv ``--version``
probe / installed-dist metadata), a capability or agentic manifest that
parses, and a health/liveness probe when the specialist declares a health
surface. A scan with ``probe=False`` never executes a provider or a CLI and
therefore never reaches VERIFIED. A capability is executable only after the
runtime and the policy that apply to it were validated — VERIFIED is the
state that carries that.

State vocabulary (ascending trust): NOT_INSTALLED (catalog id, no evidence),
DISCOVERED (evidence, nothing validated), VERIFIED, and the honest failure
states INCOMPATIBLE (present but cannot run here — e.g. ``Requires-Python``
unsatisfied, no common protocol), DEGRADED (installed but partially broken),
UNAVAILABLE (present but not reachable/not healthy right now) and
UNTRUSTED (found but not allowed to run: untrusted registry entry, or a
declared manifest that fails contract validation).

Everything persisted passes through ``security.redact``; scanning is bounded
by ``scan_budget_s`` and every evidence item carries provenance (path and/or
sha256) so a cached report explains *what it saw*, not just what it claims.
Never ``shell=True``; stdlib only; no sibling-forge imports.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import time
import tomllib
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from importlib import metadata as importlib_metadata
from pathlib import Path
from typing import Any, Literal

from theforge import _installkit as kit
from theforge import capability_manifest as capman
from theforge import specialists
from theforge.contracts.base import ContractError, from_dict, to_dict
from theforge.contracts.canonical import sha256_hex, sha256_of, utc_now
from theforge.contracts.specialist import AgenticManifest
from theforge.contracts.specialist_capability import (
    CAPABILITY_MANIFEST_NAMES,
    SPECIALIST_CAPABILITY_SCHEMA,
    SpecialistCapability,
)
from theforge.protocol import SubprocessTransport, TransportFactory
from theforge.registry.config import ProviderEntry, user_cache_dir, user_config_dir
from theforge.registry.health import check_health
from theforge.registry.registry import Registry, RegistryRecord
from theforge.security.env import safe_env
from theforge.security.redact import redact
from theforge.state import find_forge_dir

__all__ = [
    "CAPABILITY_MANIFEST_FILE",
    "DISCOVERY_CACHE_SCHEMA",
    "DISCOVERY_SOURCES",
    "DISCOVERY_STATES",
    "ENTRY_POINT_GROUP",
    "SCAN_BUDGET_S",
    "DiscoveryEvidence",
    "DiscoveryReport",
    "DiscoverySource",
    "DiscoveryState",
    "SpecialistDiscovery",
    "configured_specialist_paths",
    "discover_specialist",
    "discover_specialists",
]

# --- vocabulary ------------------------------------------------------------

DISCOVERY_STATES: tuple[str, ...] = (
    "NOT_INSTALLED",
    "DISCOVERED",
    "VERIFIED",
    "INCOMPATIBLE",
    "DEGRADED",
    "UNAVAILABLE",
    "UNTRUSTED",
)
DiscoveryState = Literal[
    "NOT_INSTALLED",
    "DISCOVERED",
    "VERIFIED",
    "INCOMPATIBLE",
    "DEGRADED",
    "UNAVAILABLE",
    "UNTRUSTED",
]

DISCOVERY_SOURCES: tuple[str, ...] = (
    "registry",
    "install-receipt",
    "forge-cli",
    "checkout",
    "configured-path",
    "package",
    "entry-point",
    "bundled-manifest",
    "mcp",
)
DiscoverySource = Literal[
    "registry",
    "install-receipt",
    "forge-cli",
    "checkout",
    "configured-path",
    "package",
    "entry-point",
    "bundled-manifest",
    "mcp",
]

DISCOVERY_CACHE_SCHEMA = "theforge/DiscoveryCache/v1"
CAPABILITY_MANIFEST_FILE = CAPABILITY_MANIFEST_NAMES[0]
ENTRY_POINT_GROUP = "theforge.specialists"
DISCOVERY_CONFIG_FILE = "discovery.toml"

SCAN_BUDGET_S = 5.0
CACHE_TTL_S = 300.0
PROBE_TIMEOUT_S = 10.0
_VERSION_PROBE = "--version"
_VERSION_OUT_RE = re.compile(r"\d+\.\d+(?:\.\d+)?")


# --- result model ----------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class DiscoveryEvidence:
    """One observed signal: where the specialist was seen + provenance."""

    source: DiscoverySource
    detail: str
    path: str | None = None
    sha256: str | None = None


@dataclass(frozen=True, kw_only=True)
class SpecialistDiscovery:
    """The resolved view of one specialist on this machine."""

    forge_id: str
    state: DiscoveryState = "NOT_INSTALLED"
    version: str = "unknown"
    sources: list[DiscoveryEvidence] = field(default_factory=list)
    # capability/agentic manifests actually located and parsed (None = absent).
    capability_manifest: SpecialistCapability | None = None
    agentic_manifest: AgenticManifest | None = None
    # handshake | manifest | health -> PASS | FAIL | SKIP (+ free-text detail in notes)
    checks: dict[str, str] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)


@dataclass(frozen=True, kw_only=True)
class DiscoveryReport:
    """A full discovery pass; the persisted document carries provenance."""

    schema: str = DISCOVERY_CACHE_SCHEMA
    generated_at: str = ""
    probed: bool = False
    truncated: bool = False
    budget_s: float = SCAN_BUDGET_S
    elapsed_ms: int = 0
    context_digest: str = ""
    entries: list[SpecialistDiscovery] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.schema != DISCOVERY_CACHE_SCHEMA:
            raise ContractError(
                f"unsupported schema {self.schema!r}, expected {DISCOVERY_CACHE_SCHEMA!r}"
            )

    def entry(self, forge_id: str) -> SpecialistDiscovery | None:
        return next((e for e in self.entries if e.forge_id == forge_id), None)


# --- inputs ----------------------------------------------------------------


class _Budget:
    """Monotonic deadline shared by every source and probe of one scan."""

    def __init__(self, seconds: float, clock: Callable[[], float]) -> None:
        self._clock = clock
        self._deadline = clock() + max(0.0, seconds)

    def remaining(self) -> float:
        return max(0.0, self._deadline - self._clock())

    def exhausted(self) -> bool:
        return self.remaining() <= 0.0


@dataclass
class _DistMeta:
    """Normalized installed-distribution facts (importlib.metadata reads)."""

    name: str
    version: str
    requires_python: str | None
    files: list[str]
    entry_points: list[tuple[str, str, str]]  # (group, name, value)
    _dist: Any = None  # the live Distribution, for locate_file

    def read_file(self, rel: str, limit: int = 262_144) -> bytes | None:
        """Read one declared package file; bounded, never executes it."""
        if self._dist is None:
            return None
        try:
            data = Path(self._dist.locate_file(rel)).read_bytes()
        except (OSError, ValueError):
            return None
        return data[:limit]


def _load_dist(name: str) -> _DistMeta | None:
    """Default dist loader (importlib.metadata). Injectable for tests."""
    try:
        dist = importlib_metadata.distribution(name)
    except importlib_metadata.PackageNotFoundError:
        return None
    try:
        files = [str(f) for f in (dist.files or ())]
    except (OSError, ValueError):
        files = []
    eps = [
        (ep.group, ep.name, ep.value)
        for ep in (dist.entry_points or ())
        if ep.group in ("console_scripts", ENTRY_POINT_GROUP)
    ]
    return _DistMeta(
        name=_meta_get(dist, "Name") or name,
        version=dist.version,
        requires_python=_meta_get(dist, "Requires-Python"),
        files=files,
        entry_points=eps,
        _dist=dist,
    )


def _meta_get(dist: importlib_metadata.Distribution, key: str) -> str | None:
    """``PackageMetadata`` has no ``get`` in typeshed — item access + narrowing."""
    try:
        value = dist.metadata[key]
    except KeyError:
        return None
    return value if isinstance(value, str) else None


def _scan_entry_points() -> list[tuple[str, str, str]]:
    """All entry points in the two recognized groups — the slow, bounded scan."""
    out: list[tuple[str, str, str]] = []
    try:
        found = importlib_metadata.entry_points()
    except (OSError, ValueError):  # pragma: no cover — defensive
        return out
    for group in (ENTRY_POINT_GROUP, "console_scripts"):
        for ep in found.select(group=group):
            out.append((ep.group, ep.name, ep.value))
    return out


def configured_specialist_paths(
    forge_dir: Path | None = None, config_dir: Path | None = None
) -> list[tuple[str | None, Path]]:
    """Explicit user-configured specialist roots (``discovery.toml``).

    Two spellings, both deterministic:

    .. code-block:: toml

        paths = ["/opt/forges/data-sentinel"]        # id from its forge.json

        [[specialists]]
        id = "data-sentinel"                          # explicit id override
        path = "/srv/forges/data-sentinel-forge"

    User config wins over project ``.forge/config/discovery.toml`` entries
    for the same path; malformed files are ignored (never fatal to a scan).
    """
    found: list[tuple[str | None, Path]] = []
    seen: set[Path] = set()
    paths = [
        (config_dir or user_config_dir()) / DISCOVERY_CONFIG_FILE,
    ]
    if forge_dir is not None:
        paths.append(forge_dir / "config" / DISCOVERY_CONFIG_FILE)
    for path in paths:
        try:
            doc = tomllib.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
            continue
        raw_paths = doc.get("paths", [])
        if isinstance(raw_paths, list):
            for item in raw_paths:
                resolved = _config_path(item)
                if resolved is not None and resolved not in seen:
                    seen.add(resolved)
                    found.append((None, resolved))
        specialists_ = doc.get("specialists", [])
        if isinstance(specialists_, list):
            for item in specialists_:
                if not isinstance(item, dict):
                    continue
                resolved = _config_path(item.get("path"))
                forge_id = item.get("id")
                if resolved is not None and resolved not in seen:
                    seen.add(resolved)
                    found.append((forge_id if isinstance(forge_id, str) else None, resolved))
    return found


def _config_path(value: object) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        return None
    expanded = Path(value).expanduser()
    return expanded if expanded.is_dir() else None


def _read_json(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    """(parsed object, sha256 of the bytes read) — provenance per file."""
    try:
        raw = path.read_bytes()
    except OSError:
        return None, None
    try:
        doc = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None, sha256_hex(raw)
    return (doc if isinstance(doc, dict) else None), sha256_hex(raw)


def _parse_capability_manifest(
    doc: dict[str, Any], expected_id: str
) -> tuple[SpecialistCapability | None, str | None]:
    """Validate a candidate manifest document; (manifest, error)."""
    if doc.get("schema") != SPECIALIST_CAPABILITY_SCHEMA:
        return None, f"schema {doc.get('schema')!r} is not {SPECIALIST_CAPABILITY_SCHEMA!r}"
    try:
        manifest = from_dict(SpecialistCapability, doc, "$")
    except ContractError as exc:
        return None, str(exc)
    if manifest.specialist.id != expected_id:
        return None, (
            f"manifest specialist.id {manifest.specialist.id!r} != {expected_id!r}"
        )
    return manifest, None


def _dist_name_from_requirement(requirement: str) -> str:
    """``"sentinel-forge>=0.5,<0.6"`` → ``"sentinel-forge"``."""
    return re.split(r"[<>=!~;\[\s]", requirement, maxsplit=1)[0].strip()


def _normalize_dist(name: str) -> str:
    """PEP 503 normalization so ``sentinel_forge`` == ``sentinel-forge``."""
    return re.sub(r"[-_.]+", "-", name).lower()


def _requires_python_ok(spec: str | None) -> bool | None:
    """Minimal specifier check for the ecosystem's ``>=a.b[.c]``/``<a.b[.c]``.

    ``None`` return = the specifier is absent or in a form this stdlib check
    does not parse — recorded, never silently failed.
    """
    if not spec or not spec.strip():
        return None
    current = sys.version_info[:3]
    for clause in spec.split(","):
        clause = clause.strip()
        match = re.fullmatch(r"(>=|<)\s*(\d+)\.(\d+)(?:\.(\d+))?", clause)
        if match is None:
            return None  # unparseable form → unknown, not a failure
        op = match.group(1)
        patch = match.group(4)
        wanted = (int(match.group(2)), int(match.group(3)), int(patch) if patch else 0)
        if op == ">=" and not current >= wanted:
            return False
        if op == "<" and not current < wanted:
            return False
    return True


# --- candidate accumulation -------------------------------------------------


@dataclass
class _Candidate:
    forge_id: str
    evidence: list[DiscoveryEvidence] = field(default_factory=list)
    registry_entry: ProviderEntry | None = None
    registry_record: RegistryRecord | None = None
    install_manifest: dict[str, Any] | None = None
    cli_receipt: dict[str, Any] | None = None
    checkout: Path | None = None
    configured: Path | None = None
    dist: _DistMeta | None = None
    capability_manifest: SpecialistCapability | None = None
    manifest_error: str | None = None
    agentic_manifest: AgenticManifest | None = None
    cli_name: str | None = None

    def seen(
        self,
        source: DiscoverySource,
        detail: str,
        *,
        path: Path | None = None,
        sha256: str | None = None,
    ) -> None:
        self.evidence.append(
            DiscoveryEvidence(
                source=source,
                detail=detail,
                path=str(path) if path is not None else None,
                sha256=sha256,
            )
        )


def _manifest_file(root: Path, names: Sequence[str]) -> Path | None:
    for name in names:
        path = root / name
        if path.is_file():
            return path
    return None


def _load_checkout_manifests(cand: _Candidate, root: Path) -> None:
    """Read ``forge.capabilities.json``/``forge.agentic.json`` at a root."""
    cap_path = _manifest_file(root, CAPABILITY_MANIFEST_NAMES)
    if cap_path is not None:
        doc, digest = _read_json(cap_path)
        cand.seen(
            "bundled-manifest",
            f"capability manifest at {cap_path.name}",
            path=cap_path,
            sha256=digest,
        )
        if doc is None:
            cand.manifest_error = f"{cap_path}: unreadable or not a JSON object"
        else:
            manifest, error = _parse_capability_manifest(doc, cand.forge_id)
            if manifest is not None:
                cand.capability_manifest = manifest
            else:
                cand.manifest_error = f"{cap_path}: {error}"
    agentic = specialists.load_agentic_manifest(cand.forge_id, root)
    if agentic is not None:
        cand.agentic_manifest = agentic
        cand.seen("bundled-manifest", "forge.agentic.json parsed", path=root / "forge.agentic.json")
        if not cand.cli_name and agentic.cli:
            cand.cli_name = agentic.cli


def _load_dist_manifests(cand: _Candidate) -> None:
    """Locate capability/agentic manifests declared inside an installed dist."""
    if cand.dist is None:
        return
    for rel in cand.dist.files:
        base = Path(rel).name
        if base in CAPABILITY_MANIFEST_NAMES:
            raw = cand.dist.read_file(rel)
            if raw is None:
                cand.manifest_error = f"{cand.dist.name}: {rel} unreadable"
                continue
            cand.seen(
                "bundled-manifest",
                f"{base} bundled in dist {cand.dist.name}=={cand.dist.version}",
                sha256=sha256_hex(raw),
            )
            try:
                doc = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                cand.manifest_error = f"{cand.dist.name}:{rel}: not JSON"
                continue
            if not isinstance(doc, dict):
                cand.manifest_error = f"{cand.dist.name}:{rel}: not a JSON object"
                continue
            manifest, error = _parse_capability_manifest(doc, cand.forge_id)
            if manifest is not None:
                cand.capability_manifest = manifest
            else:
                cand.manifest_error = f"{cand.dist.name}:{rel}: {error}"
        elif base == "forge.agentic.json" and cand.agentic_manifest is None:
            raw = cand.dist.read_file(rel)
            if raw is None:
                continue
            try:
                doc = json.loads(raw.decode("utf-8"))
                cand.agentic_manifest = from_dict(AgenticManifest, doc)
                cand.seen(
                    "bundled-manifest",
                    f"forge.agentic.json bundled in dist {cand.dist.name}=={cand.dist.version}",
                    sha256=sha256_hex(raw),
                )
            except (UnicodeDecodeError, json.JSONDecodeError, ContractError):
                continue
    if cand.dist is not None:
        for group, name, _value in cand.dist.entry_points:
            cand.seen(
                "entry-point",
                f"{group}: {name}",
            )
            if group == "console_scripts" and not cand.cli_name:
                cand.cli_name = name


def _version_argv(cand: _Candidate) -> list[str] | None:
    """The typed argv for a version probe, or None when none is resolvable."""
    manifest = cand.install_manifest or {}
    cli = manifest.get("cli")
    if isinstance(cli, dict):
        cmd = cli.get("version_cmd")
        if isinstance(cmd, list) and cmd and all(isinstance(a, str) for a in cmd):
            return [str(a) for a in cmd]
    if cand.cli_receipt is not None:
        launcher = cand.cli_receipt.get("shim") or cand.cli_receipt.get("bin")
        if isinstance(launcher, str) and launcher:
            return [launcher, _VERSION_PROBE]
    if cand.cli_name:
        resolved = shutil.which(cand.cli_name)
        if resolved:
            return [resolved, _VERSION_PROBE]
    return None


def _fetch_capability_manifest(
    record: RegistryRecord,
    forge_id: str,
    *,
    transport_factory: TransportFactory,
    timeout: float,
    allow_unverified: bool,
) -> tuple[SpecialistCapability | None, str | None]:
    """Call the governed ``capabilities`` op of a ready registry record.

    Same trust rules as ``check_health``: blocked/unverified entries are
    never executed without explicit allowance. Returns (manifest, note);
    a failed/absent op is honest scan evidence, not an exception.
    """
    entry = record.entry
    if entry.trust == "blocked" or (entry.trust == "unverified" and not allow_unverified):
        return None, f"capabilities op not called: provider {forge_id} is {entry.trust}"
    assert record.manifest is not None  # ready records only
    from theforge.protocol import TransportError
    from theforge.registry.registry import provider_cwd

    try:
        with provider_cwd() as cwd:
            response = transport_factory(entry.argv).call(
                "capabilities", {}, timeout=timeout, cwd=Path(cwd)
            )
    except TransportError as exc:
        return None, f"capabilities op failed for {forge_id}: {exc.code} {exc.detail}"
    except OSError as exc:
        return None, f"capabilities op failed for {forge_id}: {exc}"
    if response.status != "ok":
        detail = response.error.detail if response.error else response.status
        return None, f"capabilities op answered {response.status} for {forge_id}: {detail}"
    manifest, error = _parse_capability_manifest(response.payload, forge_id)
    if manifest is None:
        return None, f"capabilities op payload invalid for {forge_id}: {error}"
    if response.producer.id != forge_id:
        return None, (
            f"capabilities op producer {response.producer.id!r} does not match {forge_id!r}"
        )
    return manifest, f"capabilities op answered ({len(manifest.capabilities)} capabilities)"


def _probe_version(cand: _Candidate, timeout: float) -> tuple[bool, str | None]:
    """Run ``<cli> --version`` — argv only, scrubbed env, bounded, no shell."""
    argv = _version_argv(cand)
    if argv is None:
        return False, None
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=safe_env(),
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False, None
    if proc.returncode != 0:
        return False, None
    out = f"{proc.stdout}\n{proc.stderr}"
    match = _VERSION_OUT_RE.search(out)
    return True, match.group(0) if match else "ok"


def _mcp_registration_paths(
    cand: _Candidate, workspace_root: Path | None, roots: Sequence[Path]
) -> None:
    """MCP evidence: install-manifest ``mcp`` block, or a ``.mcp.json`` entry."""
    manifest = cand.install_manifest or {}
    mcp = manifest.get("mcp")
    if isinstance(mcp, dict) and mcp.get("command"):
        cand.seen("mcp", "install manifest declares an mcp command")
        return
    server = _mcp_server_name(cand)
    if server is None:
        return
    for root in [p for p in ([workspace_root, *roots] if workspace_root else roots) if p]:
        mcp_json = root / ".mcp.json"
        doc, digest = _read_json(mcp_json)
        if doc is None:
            continue
        servers = doc.get("mcpServers")
        if isinstance(servers, dict) and server in servers:
            cand.seen(
                "mcp",
                f"registered as {server!r} in {mcp_json}",
                path=mcp_json,
                sha256=digest,
            )
            return


def _mcp_server_name(cand: _Candidate) -> str | None:
    for root in (cand.checkout, cand.configured):
        if root is None:
            continue
        doc, _ = _read_json(root / "forge.json")
        if doc is not None:
            server = doc.get("mcp_server_name")
            if isinstance(server, str):
                return server
    return cand.cli_name


# --- the scan ---------------------------------------------------------------


def discover_specialists(
    *,
    workspace_root: Path | None = None,
    configured_paths: Sequence[Path] = (),
    forge_dir: Path | None = None,
    config_dir: Path | None = None,
    probe: bool = False,
    allow_unverified: bool = False,
    scan_budget_s: float = SCAN_BUDGET_S,
    use_cache: bool = True,
    cache_ttl_s: float = CACHE_TTL_S,
    cache_dir: Path | None = None,
    registry: Registry | None = None,
    transport_factory: TransportFactory = SubprocessTransport,
    dist_loader: Callable[[str], _DistMeta | None] | None = None,
    entry_point_scan: Callable[[], list[tuple[str, str, str]]] | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> DiscoveryReport:
    """One bounded discovery pass over every catalog specialist.

    ``probe=True`` allows the governed execution paths to run (registry
    ``describe``/``health`` over the Forge Protocol, typed-argv version
    probes). ``probe=False`` is metadata/files only — it can never reach
    VERIFIED.
    """
    if forge_dir is None and workspace_root is not None:
        forge_dir = find_forge_dir(workspace_root)
    started = clock()
    budget = _Budget(scan_budget_s, clock)
    limitations: list[str] = []
    warnings: list[str] = []
    truncated = False

    declared = configured_specialist_paths(forge_dir, config_dir)
    extra_paths = [*(Path(p) for p in configured_paths), *(p for _i, p in declared)]
    declared_ids = {i for i, _p in declared if i}

    candidates = {
        cid: _Candidate(forge_id=cid) for cid in specialists.catalog_ids(workspace_root)
    }
    for cid in declared_ids:
        candidates.setdefault(cid, _Candidate(forge_id=cid))

    context = {
        "workspace_root": str(workspace_root) if workspace_root else None,
        "configured_paths": sorted(str(p) for p in extra_paths),
        "probe": probe,
        "allow_unverified": allow_unverified,
        "ids": sorted(candidates),
    }
    context_digest = sha256_of(context)
    cache_root = (cache_dir or user_cache_dir()) / "discovery"
    if use_cache:
        cached = _read_cache(cache_root, context_digest, cache_ttl_s)
        if cached is not None:
            return cached

    reg = registry or Registry(
        forge_dir,
        transport_factory=transport_factory,
        allow_unverified=allow_unverified,
    )

    def spend(note: str) -> bool:
        nonlocal truncated
        if budget.exhausted():
            truncated = True
            if note not in limitations:
                limitations.append(f"scan budget {scan_budget_s:g}s exhausted: {note} skipped")
            return True
        return False

    # 1. registry -----------------------------------------------------------
    records: dict[str, RegistryRecord] = {}
    try:
        entries_list = reg.entries()
    except Exception as exc:  # a malformed providers.toml is a scan limit, not a crash
        entries_list = []
        warnings.append(f"registry entries unreadable: {exc}")
    for entry in entries_list:
        cand = candidates.setdefault(entry.id, _Candidate(forge_id=entry.id))
        cand.registry_entry = entry
        cand.seen(
            "registry",
            f"providers.toml entry ({entry.trust}, {entry.source})",
        )
    if not spend("registry records"):
        try:
            source_records = reg.records() if probe else reg.cached_records()
            records = {r.entry.id: r for r in source_records}
        except Exception as exc:  # registry config errors are honest scan limits
            warnings.append(f"registry read failed: {exc}")
    for provider_id, record in records.items():
        cand = candidates[provider_id]
        cand.registry_record = record
        cand.seen("registry", f"record state {record.state}")

    # 2. ~/.forge/installations + 3. forge-cli receipts ---------------------
    install_dir = kit.installations_dir()
    cli_state = specialists._forge_cli_state()
    for forge_id, cand in list(candidates.items()):
        doc, digest = _read_json(install_dir / f"{forge_id}.json")
        if doc is not None:
            cand.install_manifest = doc
            cand.seen(
                "install-receipt",
                "installation manifest",
                path=install_dir / f"{forge_id}.json",
                sha256=digest,
            )
            if not cand.cli_name:
                cli = doc.get("cli")
                if isinstance(cli, dict) and isinstance(cli.get("name"), str):
                    cand.cli_name = str(cli["name"])
        receipt = cli_state.get(forge_id)
        if receipt is not None:
            cand.cli_receipt = receipt
            cand.seen("forge-cli", "forge-cli registry receipt")
            launcher = receipt.get("shim") or receipt.get("bin")
            if isinstance(launcher, str) and launcher and not cand.cli_name:
                cand.cli_name = Path(launcher).stem

    # 4. workspace checkouts + 5. configured paths --------------------------
    roots: list[tuple[DiscoverySource, Path, str | None]] = []
    if workspace_root is not None:
        for member in kit.discover_projects(workspace_root):
            doc, _digest = _read_json(member / "forge.json")
            fid = doc.get("forge_id") if doc else None
            if fid:
                roots.append(("checkout", member, fid))
    for explicit_id, path in [*declared, *((None, Path(p)) for p in configured_paths)]:
        doc, _digest = _read_json(path / "forge.json")
        fid = explicit_id or (doc.get("forge_id") if doc else None)
        if fid or explicit_id:
            roots.append(("configured-path", path, fid or explicit_id))
    mcp_roots: list[Path] = []
    for source, root, fid in roots:
        if fid is None:
            continue
        cand = candidates.setdefault(fid, _Candidate(forge_id=fid))
        if source == "checkout":
            cand.checkout = root
        else:
            cand.configured = root
        doc, digest = _read_json(root / "forge.json")
        cand.seen(source, f"forge.json at {root}", path=root, sha256=digest)
        if doc and not cand.cli_name and isinstance(doc.get("cli"), str):
            cand.cli_name = doc["cli"]
        _load_checkout_manifests(cand, root)
        mcp_roots.append(root)

    # 6. installed package metadata (bounded, per-known-name first) ---------
    load_dist = dist_loader or _load_dist
    dist_names = _candidate_dist_names(candidates.values(), workspace_root)
    for forge_id, dist_name in sorted(dist_names.items()):
        if spend("package metadata"):
            break
        cand = candidates[forge_id]
        meta = load_dist(dist_name)
        if meta is not None:
            cand.dist = meta
            cand.seen(
                "package",
                f"installed distribution {meta.name}=={meta.version}",
            )
            _load_dist_manifests(cand)

    # 7. global entry-point scan — the most expensive source, last ----------
    eps: list[tuple[str, str, str]] = []
    if not spend("entry-point scan"):
        scan = entry_point_scan or _scan_entry_points
        try:
            eps = scan()
        except Exception as exc:  # a broken importlib backend must not kill a scan
            warnings.append(f"entry-point scan failed: {exc}")
    known_clis = {c.cli_name for c in candidates.values() if c.cli_name}
    for group, name, value in sorted(eps):
        if group == ENTRY_POINT_GROUP:
            fid = name
            cand = candidates.setdefault(fid, _Candidate(forge_id=fid))
            cand.seen("entry-point", f"{ENTRY_POINT_GROUP}: {name} -> {value}")
        elif group == "console_scripts" and name in known_clis:
            cand = next(c for c in candidates.values() if c.cli_name == name)
            cand.seen("entry-point", f"console_scripts: {name} -> {value}")

    # 8. mcp registrations --------------------------------------------------
    for cand in candidates.values():
        _mcp_registration_paths(cand, workspace_root, mcp_roots)

    # verification + final states --------------------------------------------
    entries: list[SpecialistDiscovery] = []
    for forge_id in sorted(candidates):
        if spend("verification"):
            entries.append(
                _finalize(
                    candidates[forge_id], note="budget exhausted before verification"
                )
            )
            continue
        entries.append(
            _resolve(
                candidates[forge_id],
                probe=probe,
                budget=budget,
                transport_factory=transport_factory,
                allow_unverified=allow_unverified,
            )
        )

    report = DiscoveryReport(
        generated_at=utc_now(),
        probed=probe,
        truncated=truncated,
        budget_s=scan_budget_s,
        elapsed_ms=int((clock() - started) * 1000),
        context_digest=context_digest,
        entries=entries,
        limitations=limitations,
        warnings=warnings,
    )
    if use_cache and not truncated:
        # A truncated report is never cached: replaying it would persist the
        # incompleteness the budget cut produced.
        _write_cache(cache_root, report, warnings)
    return report


def _candidate_dist_names(
    candidates: Iterable[_Candidate], workspace_root: Path | None
) -> dict[str, str]:
    """forge_id -> dist name, from forge.json / forge-knowledge / receipts."""
    from theforge import knowledge

    packs = knowledge.load_all()
    out: dict[str, str] = {}
    for cand in candidates:
        name: str | None = None
        for root in (cand.checkout, cand.configured):
            if root is None:
                continue
            doc, _ = _read_json(root / "forge.json")
            if doc and isinstance(doc.get("distribution"), str):
                name = doc["distribution"]
                break
        if name is None and cand.forge_id in packs:
            pkg = packs[cand.forge_id].package
            if pkg:
                name = _dist_name_from_requirement(pkg)
        if name is None and cand.cli_name:
            name = cand.cli_name
        if name:
            out[cand.forge_id] = name
    return out


def _cache_path(cache_root: Path, context_digest: str) -> Path:
    return cache_root / f"report-{context_digest[:16]}.json"


def _read_cache(
    cache_root: Path, context_digest: str, ttl_s: float
) -> DiscoveryReport | None:
    path = _cache_path(cache_root, context_digest)
    try:
        if not path.is_file():
            return None
        doc = json.loads(path.read_text(encoding="utf-8"))
        report = from_dict(DiscoveryReport, doc, "$")
        if report.context_digest != context_digest:
            return None
        if time.time() - path.stat().st_mtime > ttl_s:
            return None
        return report
    except (OSError, ValueError):
        return None


def _write_cache(cache_root: Path, report: DiscoveryReport, warnings: list[str]) -> None:
    path = _cache_path(cache_root, report.context_digest)
    try:
        document = to_dict(report)
        if redact(document) != document:
            warnings.append(
                "discovery cache not written: the report contains secret-shaped values"
            )
            return
        cache_root.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(document, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(path)
    except OSError as exc:
        warnings.append(f"discovery cache not written ({path}): {exc}")


# --- verification + state resolution -----------------------------------------


def _resolve(
    cand: _Candidate,
    *,
    probe: bool,
    budget: _Budget,
    transport_factory: TransportFactory,
    allow_unverified: bool,
) -> SpecialistDiscovery:
    """Verify a candidate through governed paths, then resolve its state.

    Declared-surface problems are honored in every scan (a corrupt manifest
    is UNTRUSTED without executing anything — file evidence is enough to
    know). VERIFIED additionally requires ``probe=True`` and handshake +
    manifest + health settled through a governed path; a metadata-only scan
    tops out at DISCOVERED.
    """
    checks: dict[str, str] = {"handshake": "SKIP", "manifest": "SKIP", "health": "SKIP"}
    notes: list[str] = []
    limitations: list[str] = []
    version = "unknown"
    receipt_version = (cand.cli_receipt or {}).get("version") or (
        cand.install_manifest or {}
    ).get("version")
    if isinstance(receipt_version, str) and receipt_version:
        version = receipt_version

    declared_untrusted = False  # the declared surface itself fails validation
    entry_untrusted = False  # a configured execution route policy-blocks exec
    incompatible = False
    unavailable = False
    degraded = False
    verified = False

    # -- registry path (governed describe + health over Forge Protocol) ------
    if cand.registry_entry is not None and cand.registry_entry.trust in (
        "unverified",
        "blocked",
    ) and not (allow_unverified and cand.registry_entry.trust == "unverified"):
        entry_untrusted = True
        limitations.append(
            f"providers.toml entry is {cand.registry_entry.trust} — not executed "
            "without explicit trust"
        )
    record = cand.registry_record
    if record is not None:
        if record.state == "ready" and record.manifest is not None:
            checks["handshake"] = "PASS"
            checks["manifest"] = "PASS"
            version = record.manifest.version
            notes.append(f"registry describe ok (protocol {record.protocol})")
            if (
                probe
                and cand.capability_manifest is None
                and "capabilities" in record.manifest.ops
                and not budget.exhausted()
            ):
                # The adapter's governed capability surface is authoritative:
                # prefer its SpecialistCapability document over the fallback
                # derivation (lf-0031). A refused/absent/invalid answer is
                # recorded, never fatal to the rest of the scan.
                fetched, note = _fetch_capability_manifest(
                    record,
                    cand.forge_id,
                    transport_factory=transport_factory,
                    timeout=min(PROBE_TIMEOUT_S, max(0.1, budget.remaining())),
                    allow_unverified=allow_unverified,
                )
                if fetched is not None:
                    cand.capability_manifest = fetched
                    cand.seen(
                        "registry",
                        "capabilities op answered the SpecialistCapability manifest",
                    )
                if note:
                    notes.append(note)
            if probe:
                outcome = check_health(
                    record,
                    transport_factory=transport_factory,
                    timeout=min(PROBE_TIMEOUT_S, max(0.1, budget.remaining())),
                    allow_unverified=allow_unverified,
                )
                if outcome.status == "ok":
                    checks["health"] = "PASS"
                    verified = True
                elif outcome.status == "unavailable":
                    checks["health"] = "FAIL"
                    unavailable = True
                    notes.append("health probe reports unavailable")
                else:
                    checks["health"] = "FAIL"
                    degraded = True
                    notes.append(
                        "health probe "
                        f"{outcome.status}: {outcome.error.detail if outcome.error else ''}"
                    )
            else:
                notes.append("health not probed (probe=False)")
        elif record.state == "unreachable":
            unavailable = True
            notes.append(f"registry describe unreachable: {record.error}")
        elif record.state == "invalid":
            declared_untrusted = True
            checks["manifest"] = "FAIL"
            notes.append(f"describe produced an invalid manifest: {record.error}")
        elif record.state == "incompatible":
            incompatible = True
            notes.append(f"registry describe incompatible: {record.error}")
        elif record.state in ("untrusted", "blocked"):
            entry_untrusted = True

    # -- package path (installed dist metadata) ------------------------------
    if cand.dist is not None:
        if version == "unknown":
            version = cand.dist.version
        satisfied = _requires_python_ok(cand.dist.requires_python)
        if satisfied is False:
            incompatible = True
            limitations.append(
                f"requires-python {cand.dist.requires_python!r} not satisfied by "
                f"{sys.version_info[0]}.{sys.version_info[1]}.{sys.version_info[2]}"
            )
        elif satisfied is None and cand.dist.requires_python:
            notes.append(
                f"requires-python {cand.dist.requires_python!r} unparsed (not enforced)"
            )
        if checks["handshake"] == "SKIP" and any(
            group == "console_scripts" for group, _name, _v in cand.dist.entry_points
        ):
            # installed dist declares a console script — a metadata-level
            # handshake (no execution), provenance is the dist itself.
            checks["handshake"] = "PASS"
            notes.append(f"handshake: installed dist {cand.dist.name}=={cand.dist.version}")

    # -- declared capability/agentic manifests --------------------------------
    if cand.capability_manifest is not None:
        checks["manifest"] = "PASS"
        declared = cand.capability_manifest.specialist
        if declared.version not in ("unknown", "runtime-detected"):
            if version == "unknown":
                version = declared.version
            elif declared.version.split(".", 1)[0] != version.split(".", 1)[0]:
                incompatible = True
                notes.append(
                    f"capability manifest version {declared.version} incompatible "
                    f"with installed {version}"
                )
    elif cand.agentic_manifest is not None:
        if checks["manifest"] == "SKIP":
            checks["manifest"] = "PASS"
        if cand.agentic_manifest.version != "unknown" and version == "unknown":
            version = cand.agentic_manifest.version
    if cand.manifest_error is not None:
        declared_untrusted = True
        checks["manifest"] = "FAIL"
        notes.append(f"manifest rejected: {cand.manifest_error}")

    # -- fallback: derive the advertisement from a live describe ------------
    if cand.capability_manifest is None and record is not None and record.manifest is not None:
        try:
            cand.capability_manifest = capman.specialist_capability_from_manifest(
                record.manifest, expected_id=cand.forge_id
            )
        except ContractError as exc:
            notes.append(f"capability manifest derivation failed: {exc}")
        else:
            notes.append(
                "capability manifest derived from the ForgeManifest "
                "(no capabilities op or bundled manifest)"
            )

    # -- typed-argv handshake / liveness (non-registry path) -----------------
    # A metadata handshake (installed dist, cached record) proves presence, not
    # liveness. When a governed executable route resolves, the version probe
    # upgrades it to live evidence — a failed probe on an installed CLI is an
    # honest DEGRADED, not a silent PASS.
    ran_version_probe = False
    if probe and not verified and not budget.exhausted():
        argv = _version_argv(cand)
        if argv is not None:
            ok, observed = _probe_version(
                cand, min(PROBE_TIMEOUT_S, max(0.1, budget.remaining()))
            )
            if ok:
                checks["handshake"] = "PASS"
                ran_version_probe = True
                notes.append(f"version probe ok: {' '.join(argv)}")
                if observed and observed != "ok" and version == "unknown":
                    version = observed
            else:
                checks["handshake"] = "FAIL"
                degraded = True
                notes.append(f"version probe failed: {' '.join(argv)}")
        elif cand.cli_name:
            notes.append(f"cli {cand.cli_name!r} not resolvable for a version probe")
    if checks["health"] == "SKIP" and ran_version_probe:
        # The same governed probe is the liveness evidence for a specialist
        # without a Forge Protocol health surface.
        checks["health"] = "PASS"
        notes.append("health: liveness via the version probe")

    # -- installed-but-broken ladder (mirrors specialists.collect evidence) ---
    if (
        cand.install_manifest is not None or cand.cli_receipt is not None
    ) and checks["handshake"] != "PASS":
        install_root = (cand.install_manifest or {}).get("install_root") or (
            cand.cli_receipt or {}
        ).get("venv")
        if install_root and not Path(str(install_root)).is_dir():
            degraded = True
            notes.append("install root/venv declared but missing on disk")

    if (
        probe
        and not verified
        and ran_version_probe
        and checks["handshake"] == "PASS"
        and checks["manifest"] == "PASS"
        and checks["health"] in ("PASS", "SKIP")
    ):
        # A live governed probe ran and every check passed; health SKIP means
        # no health surface was declared or needed — recorded, not hidden.
        verified = True
    if checks["handshake"] == "PASS" and not (verified or ran_version_probe):
        limitations.append(
            "identity evidence is cached/metadata only — rerun with probe to verify"
        )
    if checks["manifest"] == "SKIP" and cand.evidence:
        limitations.append("no capability/agentic manifest found to parse")

    non_registry_evidence = any(e.source != "registry" for e in cand.evidence)
    state = _final_state(
        declared_untrusted=declared_untrusted,
        incompatible=incompatible,
        verified=verified,
        entry_untrusted=entry_untrusted and not non_registry_evidence,
        unavailable=unavailable,
        degraded=degraded,
        has_evidence=bool(cand.evidence),
    )
    return SpecialistDiscovery(
        forge_id=cand.forge_id,
        state=state,
        version=version,
        sources=cand.evidence,
        capability_manifest=cand.capability_manifest,
        agentic_manifest=cand.agentic_manifest,
        checks=checks,
        notes=notes,
        limitations=limitations,
    )


def _finalize(cand: _Candidate, *, note: str) -> SpecialistDiscovery:
    """A candidate cut short by the scan budget — evidence kept, checks SKIP."""
    return SpecialistDiscovery(
        forge_id=cand.forge_id,
        state="DISCOVERED" if cand.evidence else "NOT_INSTALLED",
        sources=cand.evidence,
        capability_manifest=cand.capability_manifest,
        agentic_manifest=cand.agentic_manifest,
        checks={"handshake": "SKIP", "manifest": "SKIP", "health": "SKIP"},
        limitations=[note],
    )


def _final_state(
    *,
    declared_untrusted: bool,
    incompatible: bool,
    verified: bool,
    entry_untrusted: bool,
    unavailable: bool,
    degraded: bool,
    has_evidence: bool,
) -> DiscoveryState:
    """Precedence: dishonest/broken declarations outrank mere presence.

    UNAVAILABLE/DEGRADED outrank VERIFIED on purpose: a governed route that
    was observed failing this scan is fresher evidence than a liveness probe
    that passed on a different route — VERIFIED must never mask a dead
    declared surface.
    """
    if declared_untrusted:
        return "UNTRUSTED"
    if incompatible:
        return "INCOMPATIBLE"
    if unavailable:
        return "UNAVAILABLE"
    if degraded:
        return "DEGRADED"
    if verified:
        return "VERIFIED"
    if entry_untrusted:
        # The only declared execution route is policy-blocked; no other
        # source verifies it — discovered, but not to be trusted.
        return "UNTRUSTED"
    if has_evidence:
        return "DISCOVERED"
    return "NOT_INSTALLED"


def discover_specialist(
    forge_id: str, **kwargs: Any
) -> SpecialistDiscovery | None:
    """Resolve a single specialist; None when it is not in the catalog."""
    return discover_specialists(**kwargs).entry(forge_id)
