"""Forge Context Contract v1 — workspace context registry engine.

Canonical source: ``the-forge/scripts/installkit/forge_context.py``.
Vendored per-Forge (``<pkg>/_forgecontext.py``); keep the
``_FORGECONTEXT_VERSION``/``_SOURCE_SHA256`` header intact so drift checks
can compare copies. stdlib-only. Deterministic. No secrets — the registry
carries capability metadata only.

Documents emitted: ``forge/context/v1`` (per-forge capability manifest)
and ``forge/context-registry/v1`` (workspace registry). The published JSON
Schemas live in ``the-forge/docs/portable-installation/schemas/``; the
validators in this module mirror them so a vendored copy can validate
without the schema files or any third-party package.

What lives here
---------------
``.forge/context/`` is a *workspace-level* registry — a different layer
from ``~/.forge/installations/`` (account-level, owned by the bootstrap):

    .forge/context/
        registry.json              forge/context-registry/v1 — shared doc
        capabilities/<fid>.json    forge/context/v1 — one per forge
        ROUTING.md                 human routing doc, regenerated
        .context.lock              O_EXCL op lock
        journal.json               in-flight op record (redo journal)

Ownership (install-2.0 spec §4.3): ``registry.json`` and ``ROUTING.md``
are *shared* documents, regenerated deterministically from per-forge
entries; ``capabilities/<forge-id>.json`` is *fully-managed* by that forge
alone. A forge NEVER deletes another forge's resources: ``unregister``
refuses ``FORGE-CONTEXT-OWNERSHIP`` when the entry or the manifest is not
the caller's, and a foreign manifest at ``capabilities/<fid>.json`` (one
whose ``forge_id`` does not match the file name) is refused, not
overwritten. Unparseable files owned by name are quarantined aside
(``.corrupt-<stamp>``), never silently replaced.

Write protocol (multi-installer safe):

    1. acquire ``.context.lock`` (O_EXCL; stale locks — dead pid or age —
       are reclaimed once)
    2. if ``journal.json`` exists, redo the journaled op (idempotent),
       then remove it
    3. write ``journal.json`` with the intended op + payload
    4. apply: ``capabilities/<fid>.json`` → ``registry.json`` →
       ``ROUTING.md`` (every write is tmp+rename atomic)
    5. remove ``journal.json``
    6. release the lock

A kill between 3 and 5 leaves the journal; the next op — or an explicit
``repair_context`` — redoes the recorded op and converges.

Determinism: JSON is ``sort_keys`` + indent 2 + trailing LF; registry
entries are sorted by ``forge_id``; ``ROUTING.md`` embeds no timestamps.
Re-registering an unchanged manifest performs zero writes — the second
``install`` is byte-identical, which is what "idempotent" means here.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import sys
import tempfile
import time
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

_FORGECONTEXT_VERSION = "1.0.0"
# Filled by the vendor step (scripts/installkit/vendor.py) — the sha256 of
# the canonical source body, so drift checks can compare vendored copies.
_SOURCE_SHA256 = "ffa68ec3a9a7872d"

SCHEMA_MANIFEST = "forge/context/v1"
SCHEMA_REGISTRY = "forge/context-registry/v1"
REGISTRY_FORMAT_VERSION = 1

CONTEXT_DIR = ".forge/context"
REGISTRY_NAME = "registry.json"
CAPABILITIES_DIR = "capabilities"
ROUTING_NAME = "ROUTING.md"
JOURNAL_NAME = "journal.json"
LOCK_NAME = ".context.lock"

OWNERSHIP_KINDS = (
    "fully-managed",
    "shared",
    "managed-block",
    "user",
    "preexisting",
    "foreign-installer",
)
HOSTS = ("claude", "devin", "codex", "copilot")
SCOPES = ("project", "workspace", "user")
PROFILES = ("minimal", "recommended", "full")
MANIFEST_STATES = ("available", "degraded", "unavailable")
CHECK_STATUSES = ("PASS", "FAIL", "BLOCKED", "UNVERIFIED", "NOT_APPLICABLE")
HEALTH_STATUSES = ("healthy", "degraded", "unverified", "broken")
CAPABILITY_DISCOVERY = ("native-runtime", "cli", "mcp", "bundled", "workspace-file", "none")
COMMAND_MODES = ("direct-capability", "diagnostic-only", "specialist-workflow", "read-only")
RESOURCE_KINDS = ("copied", "referenced", "bundled", "materialized")
EVAL_KINDS = ("developer", "runtime-decision", "output-verification", "host-conformance")

# Refusal codes — forge-specific codes may extend these.
E_SCHEMA = "FORGE-CONTEXT-SCHEMA"
E_OWNERSHIP = "FORGE-CONTEXT-OWNERSHIP"
E_LOCKED = "FORGE-CONTEXT-LOCKED"
E_PATH = "FORGE-CONTEXT-PATH"

# The six capability kinds every manifest must declare (§4.1). Extra kinds
# are allowed — each value still has to match the capability shape.
CORE_CAPABILITY_KINDS = ("knowledge", "rules", "evals", "protocols", "skills", "agents")

_FORGE_ID_RE = re.compile(r"^[a-z0-9-]{1,64}$")
_DOMAIN_RE = re.compile(r"^[a-z0-9-]{1,64}$")
_ITEM_ID_RE = re.compile(r"^[a-z0-9-_]{1,128}$")
_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+([-.+][0-9A-Za-z.]+)?$")
_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

MAX_ITEMS = 512
MAX_STR = 1024


class ContextError(Exception):
    """Named refusal: ``kind`` + ``detail``."""

    def __init__(self, kind: str, detail: str) -> None:
        super().__init__(detail)
        self.kind = kind
        self.detail = detail


class LockError(ContextError):
    """The context lock is held by a live process."""


# --------------------------------------------------------------------------
# small helpers (self-contained on purpose — the module vendors alone)
# --------------------------------------------------------------------------


def _utc_now() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha_file(path: Path) -> str:
    return _sha(path.read_bytes())


def _json_bytes(doc: dict[str, Any]) -> bytes:
    return (json.dumps(doc, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _load_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name, dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _pid_alive(pid: int) -> bool | None:
    """True/False when decidable, None when the platform cannot say."""
    if pid <= 0:
        return False
    if sys.platform == "win32":
        return None
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except (PermissionError, OSError):
        return None


class _Lock:
    """O_EXCL lockfile carrying ``{pid, created_at}``. Stale locks — dead
    holder or older than ``stale_after_s`` — are reclaimed once so an
    interrupted op never bricks the registry."""

    def __init__(self, lock: Path, stale_after_s: float = 900.0) -> None:
        self._lock = lock
        self._stale = stale_after_s
        self.held = False
        self.recovered = False

    def __enter__(self) -> _Lock:
        try:
            self._create()
            return self
        except FileExistsError:
            holder = _load_json(self._lock) or {"pid": None}
            if not self._is_stale(holder):
                raise LockError(E_LOCKED, f"context lock held at {self._lock} ({holder})") from None
            try:
                self._lock.unlink()
            except OSError as exc:
                raise LockError(
                    E_LOCKED, f"context lock at {self._lock} could not be reclaimed"
                ) from exc
            self.recovered = True
            self._create()
            return self

    def _create(self) -> None:
        fd = os.open(str(self._lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, _json_bytes({"pid": os.getpid(), "created_at": _utc_now()}))
        os.close(fd)
        self.held = True

    def _is_stale(self, holder: dict[str, Any]) -> bool:
        pid = holder.get("pid")
        if isinstance(pid, int) and pid != os.getpid():
            alive = _pid_alive(pid)
            if alive is False:
                return True
            if alive is True:
                return False
        try:
            age = time.time() - self._lock.stat().st_mtime
        except OSError:
            return False
        return age > self._stale

    def __exit__(self, *exc: object) -> None:
        if self.held:
            with contextlib.suppress(OSError):
                self._lock.unlink()


def acquire_lock(ctx_dir: Path) -> _Lock:
    """Non-blocking op lock — contention is a refusal, not a hang."""
    ctx_dir.mkdir(parents=True, exist_ok=True)
    return _Lock(ctx_dir / LOCK_NAME)


# --------------------------------------------------------------------------
# layout
# --------------------------------------------------------------------------


def context_dir(root: Path | str) -> Path:
    return Path(root) / CONTEXT_DIR


def registry_path(root: Path | str) -> Path:
    return context_dir(root) / REGISTRY_NAME


def routing_path(root: Path | str) -> Path:
    return context_dir(root) / ROUTING_NAME


def capability_path(root: Path | str, forge_id: str) -> Path:
    return context_dir(root) / CAPABILITIES_DIR / f"{forge_id}.json"


def _capability_rel(forge_id: str) -> str:
    return f"{CAPABILITIES_DIR}/{forge_id}.json"


def _quarantine(path: Path, stamp: str) -> Path:
    """Move a corrupt-but-ours file aside — never delete, never overwrite."""
    dest = path.with_name(f"{path.name}.corrupt-{stamp}")
    n = 0
    while dest.exists():
        n += 1
        dest = path.with_name(f"{path.name}.corrupt-{stamp}-{n}")
    path.replace(dest)
    return dest


# --------------------------------------------------------------------------
# validation — mirrors docs/portable-installation/schemas/ForgeContext*.json
# --------------------------------------------------------------------------


def _err(problems: list[str], path: str, msg: str) -> None:
    problems.append(f"{path}: {msg}")


def _closed(doc: Any, allowed: Iterable[str], problems: list[str], path: str) -> bool:
    if not isinstance(doc, dict):
        _err(problems, path, "expected object")
        return False
    extra = sorted(set(doc) - set(allowed))
    if extra:
        _err(problems, path, f"unknown keys {extra}")
        return False
    return True


def _required(doc: dict[str, Any], keys: Iterable[str], problems: list[str], path: str) -> None:
    for k in keys:
        if k not in doc:
            _err(problems, f"{path}.{k}", "required")


def _str(v: Any, problems: list[str], path: str, *, pattern: re.Pattern[str] | None = None) -> None:
    if not isinstance(v, str) or not v or len(v) > MAX_STR:
        _err(problems, path, "expected non-empty string")
        return
    if _CONTROL_RE.search(v):
        _err(problems, path, "control characters are not allowed")
    if pattern is not None and not pattern.match(v):
        _err(problems, path, f"does not match {pattern.pattern}")


def _bool(v: Any, problems: list[str], path: str) -> None:
    if not isinstance(v, bool):
        _err(problems, path, "expected boolean")


def _enum(v: Any, allowed: Iterable[str], problems: list[str], path: str) -> None:
    if v not in tuple(allowed):
        _err(problems, path, f"expected one of {list(allowed)}")


def _str_list(
    v: Any, problems: list[str], path: str, *, pattern: re.Pattern[str] | None = None
) -> None:
    if not isinstance(v, list) or len(v) > MAX_ITEMS:
        _err(problems, path, "expected array")
        return
    for i, item in enumerate(v):
        _str(item, problems, f"{path}[{i}]", pattern=pattern)


def _argv(v: Any, problems: list[str], path: str) -> None:
    if not isinstance(v, list) or not v or len(v) > MAX_ITEMS:
        _err(problems, path, "expected non-empty argv array")
        return
    for i, item in enumerate(v):
        _str(item, problems, f"{path}[{i}]")


def _sha256_ref(v: Any, problems: list[str], path: str) -> None:
    if not isinstance(v, str) or not _SHA256_RE.match(v):
        _err(problems, path, "expected 'sha256:<64 hex>'")


def _path_str(v: Any, problems: list[str], path: str) -> None:
    """Workspace/install path: no NUL, no ``..`` escape, no ~ expansion."""
    if not isinstance(v, str) or not v or len(v) > MAX_STR:
        _err(problems, path, "expected non-empty path")
        return
    if "\x00" in v:
        _err(problems, path, "NUL in path")
    parts = re.split(r"[/\\]", v)
    if ".." in parts:
        _err(problems, path, "'..' segments are not allowed")
    if v.startswith("~"):
        _err(problems, path, "'~' expansion is not portable — use the resolved path")


def _capability(v: Any, problems: list[str], path: str) -> None:
    if not _closed(
        v, ("available", "status", "discovery", "count", "optional", "detail"), problems, path
    ):
        return
    _required(v, ("available", "status", "discovery"), problems, path)
    if "available" in v:
        _bool(v["available"], problems, f"{path}.available")
    if "status" in v:
        _enum(
            v["status"],
            ("available", "degraded", "unavailable", "unverified"),
            problems,
            f"{path}.status",
        )
    if "discovery" in v:
        _enum(v["discovery"], CAPABILITY_DISCOVERY, problems, f"{path}.discovery")
    if "count" in v and (not isinstance(v["count"], int) or v["count"] < 0):
        _err(problems, f"{path}.count", "expected integer >= 0")
    if "optional" in v:
        _bool(v["optional"], problems, f"{path}.optional")
    if "detail" in v:
        _str(v["detail"], problems, f"{path}.detail")


def _command(v: Any, problems: list[str], path: str) -> None:
    if not _closed(v, ("id", "argv", "mode", "read_only", "description"), problems, path):
        return
    _required(v, ("id", "argv", "read_only"), problems, path)
    if "id" in v:
        _str(v["id"], problems, f"{path}.id", pattern=_ITEM_ID_RE)
    if "argv" in v:
        _argv(v["argv"], problems, f"{path}.argv")
    if "mode" in v:
        _enum(v["mode"], COMMAND_MODES, problems, f"{path}.mode")
    if "read_only" in v:
        _bool(v["read_only"], problems, f"{path}.read_only")
    if "description" in v:
        _str(v["description"], problems, f"{path}.description")


def _id_retrieval(v: Any, problems: list[str], path: str) -> None:
    if not _closed(v, ("id", "interface"), problems, path):
        return
    _required(v, ("id", "interface"), problems, path)
    if "id" in v:
        _str(v["id"], problems, f"{path}.id", pattern=_ITEM_ID_RE)
    if "interface" in v:
        _enum(v["interface"], CAPABILITY_DISCOVERY, problems, f"{path}.interface")


def _eval_suite(v: Any, problems: list[str], path: str) -> None:
    if not _closed(v, ("id", "kind", "command"), problems, path):
        return
    _required(v, ("id", "kind"), problems, path)
    if "id" in v:
        _str(v["id"], problems, f"{path}.id", pattern=_ITEM_ID_RE)
    if "kind" in v:
        _enum(v["kind"], EVAL_KINDS, problems, f"{path}.kind")
    if "command" in v:
        _argv(v["command"], problems, f"{path}.command")


def _protocol(v: Any, problems: list[str], path: str) -> None:
    if not _closed(v, ("id", "version"), problems, path):
        return
    _required(v, ("id", "version"), problems, path)
    if "id" in v:
        _str(v["id"], problems, f"{path}.id")
    if "version" in v:
        _str(v["version"], problems, f"{path}.version")


def _resource(v: Any, problems: list[str], path: str) -> None:
    if not _closed(v, ("kind", "location", "optional", "sha256", "count"), problems, path):
        return
    _required(v, ("kind", "location", "optional"), problems, path)
    if "kind" in v:
        _enum(v["kind"], RESOURCE_KINDS, problems, f"{path}.kind")
    if "location" in v:
        _path_str(v["location"], problems, f"{path}.location")
    if "optional" in v:
        _bool(v["optional"], problems, f"{path}.optional")
    if "sha256" in v:
        _sha256_ref(v["sha256"], problems, f"{path}.sha256")
    if "count" in v and (not isinstance(v["count"], int) or v["count"] < 0):
        _err(problems, f"{path}.count", "expected integer >= 0")


_MANIFEST_KEYS = (
    "schema",
    "forge_id",
    "name",
    "version",
    "protocol_version",
    "domains",
    "capabilities",
    "skills",
    "agents",
    "coordinators",
    "knowledge_providers",
    "eval_suites",
    "protocols",
    "rule_areas",
    "discovery",
    "interfaces",
    "resources",
    "runtime",
    "security",
    "installed",
    "install_modes",
    "state",
    "degraded_reasons",
    "health",
    "integrity",
    "recorded_at",
    "recorded_by",
)
_MANIFEST_REQUIRED = (
    "schema",
    "forge_id",
    "name",
    "version",
    "protocol_version",
    "domains",
    "capabilities",
    "discovery",
    "interfaces",
    "resources",
    "runtime",
    "security",
    "installed",
    "state",
    "health",
    "integrity",
    "recorded_at",
    "recorded_by",
)


def validate_manifest(doc: Any) -> list[str]:
    """Structural validation of a ``forge/context/v1`` manifest.

    Returns the list of problems — empty means conforming. Mirrors
    ``ForgeContext.schema.json`` so a vendored copy validates without the
    schema file or ``jsonschema``."""
    problems: list[str] = []
    if not isinstance(doc, dict):
        return ["$: expected object"]
    _closed(doc, _MANIFEST_KEYS, problems, "$")
    _required(doc, _MANIFEST_REQUIRED, problems, "$")

    if doc.get("schema") != SCHEMA_MANIFEST:
        _err(problems, "$.schema", f"expected {SCHEMA_MANIFEST!r}")
    if "forge_id" in doc:
        _str(doc["forge_id"], problems, "$.forge_id", pattern=_FORGE_ID_RE)
    if "name" in doc:
        _str(doc["name"], problems, "$.name")
    if "version" in doc:
        _str(doc["version"], problems, "$.version", pattern=_VERSION_RE)
    if "protocol_version" in doc:
        _str(doc["protocol_version"], problems, "$.protocol_version")
    if "domains" in doc:
        _str_list(doc["domains"], problems, "$.domains", pattern=_DOMAIN_RE)

    caps = doc.get("capabilities")
    if isinstance(caps, dict):
        if not caps:
            _err(problems, "$.capabilities", "expected at least one capability")
        for kind, value in sorted(caps.items()):
            _capability(value, problems, f"$.capabilities.{kind}")
    elif "capabilities" in doc:
        _err(problems, "$.capabilities", "expected object")

    for key in ("skills", "agents", "coordinators", "rule_areas"):
        if key in doc:
            _str_list(doc[key], problems, f"$.{key}", pattern=_ITEM_ID_RE)
    if "knowledge_providers" in doc:
        _obj_list(doc["knowledge_providers"], _id_retrieval, problems, "$.knowledge_providers")
    if "eval_suites" in doc:
        _obj_list(doc["eval_suites"], _eval_suite, problems, "$.eval_suites")
    if "protocols" in doc:
        _obj_list(doc["protocols"], _protocol, problems, "$.protocols")

    disc = doc.get("discovery")
    if isinstance(disc, dict):
        _closed(disc, ("commands", "manifest"), problems, "$.discovery")
        _required(disc, ("commands",), problems, "$.discovery")
        cmds = disc.get("commands")
        if isinstance(cmds, list):
            if len(cmds) > MAX_ITEMS:
                _err(problems, "$.discovery.commands", "too many entries")
            for i, cmd in enumerate(cmds):
                _command(cmd, problems, f"$.discovery.commands[{i}]")
        elif "commands" in disc:
            _err(problems, "$.discovery.commands", "expected array")
        if "manifest" in disc:
            _path_str(disc["manifest"], problems, "$.discovery.manifest")
    elif "discovery" in doc:
        _err(problems, "$.discovery", "expected object")

    iface = doc.get("interfaces")
    if isinstance(iface, dict):
        _closed(iface, ("cli", "mcp", "python", "executable"), problems, "$.interfaces")
        if not iface:
            _err(problems, "$.interfaces", "at least one interface is required")
        cli = iface.get("cli")
        if cli is not None and _closed(
            cli, ("name", "version_cmd", "entry"), problems, "$.interfaces.cli"
        ):
            _required(cli, ("name",), problems, "$.interfaces.cli")
            if "name" in cli:
                _str(cli["name"], problems, "$.interfaces.cli.name")
            if "version_cmd" in cli:
                _argv(cli["version_cmd"], problems, "$.interfaces.cli.version_cmd")
            if "entry" in cli:
                _str(cli["entry"], problems, "$.interfaces.cli.entry")
        mcp = iface.get("mcp")
        if mcp is not None and _closed(
            mcp, ("server_name", "command", "verify_tool"), problems, "$.interfaces.mcp"
        ):
            _required(mcp, ("server_name", "command"), problems, "$.interfaces.mcp")
            if "server_name" in mcp:
                _str(mcp["server_name"], problems, "$.interfaces.mcp.server_name")
            if "command" in mcp:
                _argv(mcp["command"], problems, "$.interfaces.mcp.command")
            if "verify_tool" in mcp:
                _str(mcp["verify_tool"], problems, "$.interfaces.mcp.verify_tool")
        py = iface.get("python")
        if py is not None and _closed(
            py, ("package", "distribution"), problems, "$.interfaces.python"
        ):
            _required(py, ("package", "distribution"), problems, "$.interfaces.python")
            if "package" in py:
                _str(py["package"], problems, "$.interfaces.python.package")
            if "distribution" in py:
                _str(py["distribution"], problems, "$.interfaces.python.distribution")
        exe = iface.get("executable")
        if exe is not None and _closed(
            exe, ("path", "sha256"), problems, "$.interfaces.executable"
        ):
            _required(exe, ("path",), problems, "$.interfaces.executable")
            if "path" in exe:
                _path_str(exe["path"], problems, "$.interfaces.executable.path")
            if "sha256" in exe:
                _sha256_ref(exe["sha256"], problems, "$.interfaces.executable.sha256")
    elif "interfaces" in doc:
        _err(problems, "$.interfaces", "expected object")

    res = doc.get("resources")
    if isinstance(res, dict):
        for key, value in sorted(res.items()):
            _resource(value, problems, f"$.resources.{key}")
    elif "resources" in doc:
        _err(problems, "$.resources", "expected object")

    rt = doc.get("runtime")
    if isinstance(rt, dict):
        if _closed(
            rt,
            (
                "python",
                "package",
                "distribution",
                "requires_network",
                "requires_credentials",
                "offline_available",
                "venv",
                "executable",
            ),
            problems,
            "$.runtime",
        ):
            _required(
                rt,
                (
                    "python",
                    "package",
                    "distribution",
                    "requires_network",
                    "requires_credentials",
                    "offline_available",
                ),
                problems,
                "$.runtime",
            )
            for key in ("python", "package", "distribution"):
                if key in rt:
                    _str(rt[key], problems, f"$.runtime.{key}")
            for key in ("requires_network", "requires_credentials", "offline_available"):
                if key in rt:
                    _bool(rt[key], problems, f"$.runtime.{key}")
            for key in ("venv", "executable"):
                if key in rt:
                    _path_str(rt[key], problems, f"$.runtime.{key}")
    elif "runtime" in doc:
        _err(problems, "$.runtime", "expected object")

    sec = doc.get("security")
    if isinstance(sec, dict):
        if _closed(
            sec,
            ("read_only_default", "mutating_verbs", "requires_approval", "notes"),
            problems,
            "$.security",
        ):
            _required(
                sec,
                ("read_only_default", "mutating_verbs", "requires_approval"),
                problems,
                "$.security",
            )
            if "read_only_default" in sec:
                _bool(sec["read_only_default"], problems, "$.security.read_only_default")
            for key in ("mutating_verbs", "requires_approval"):
                if key in sec:
                    _str_list(sec[key], problems, f"$.security.{key}")
            if "notes" in sec:
                _str(sec["notes"], problems, "$.security.notes")
    elif "security" in doc:
        _err(problems, "$.security", "expected object")

    inst = doc.get("installed")
    if isinstance(inst, dict):
        if _closed(inst, ("scope", "profile", "hosts", "components"), problems, "$.installed"):
            _required(inst, ("scope", "profile", "hosts"), problems, "$.installed")
            if "scope" in inst:
                _enum(inst["scope"], SCOPES, problems, "$.installed.scope")
            if "profile" in inst:
                _enum(inst["profile"], PROFILES, problems, "$.installed.profile")
            if "hosts" in inst:
                hosts = inst["hosts"]
                if isinstance(hosts, list):
                    for i, h in enumerate(hosts):
                        _enum(h, HOSTS, problems, f"$.installed.hosts[{i}]")
                else:
                    _err(problems, "$.installed.hosts", "expected array")
            if "components" in inst and not isinstance(inst["components"], dict):
                _err(problems, "$.installed.components", "expected object")
    elif "installed" in doc:
        _err(problems, "$.installed", "expected object")

    if "install_modes" in doc:
        modes = doc["install_modes"]
        if isinstance(modes, list):
            for i, m in enumerate(modes):
                _enum(m, SCOPES, problems, f"$.install_modes[{i}]")
        else:
            _err(problems, "$.install_modes", "expected array")

    if "state" in doc:
        _enum(doc["state"], MANIFEST_STATES, problems, "$.state")
    if "degraded_reasons" in doc:
        _str_list(doc["degraded_reasons"], problems, "$.degraded_reasons")
    if doc.get("state") == "degraded" and not doc.get("degraded_reasons"):
        _err(problems, "$.degraded_reasons", "required when state is 'degraded'")

    health = doc.get("health")
    if isinstance(health, dict):
        if _closed(health, ("status", "checks"), problems, "$.health"):
            _required(health, ("status", "checks"), problems, "$.health")
            if "status" in health:
                _enum(health["status"], HEALTH_STATUSES, problems, "$.health.status")
            checks = health.get("checks")
            if isinstance(checks, list):
                for i, c in enumerate(checks):
                    if _closed(c, ("id", "status", "detail"), problems, f"$.health.checks[{i}]"):
                        _required(c, ("id", "status"), problems, f"$.health.checks[{i}]")
                        if "id" in c:
                            _str(c["id"], problems, f"$.health.checks[{i}].id")
                        if "status" in c:
                            _enum(
                                c["status"],
                                CHECK_STATUSES,
                                problems,
                                f"$.health.checks[{i}].status",
                            )
                        if "detail" in c:
                            _str(c["detail"], problems, f"$.health.checks[{i}].detail")
            elif "checks" in health:
                _err(problems, "$.health.checks", "expected array")
    elif "health" in doc:
        _err(problems, "$.health", "expected object")

    integ = doc.get("integrity")
    if isinstance(integ, dict):
        if _closed(integ, ("algorithm", "files", "attestation"), problems, "$.integrity"):
            _required(integ, ("algorithm", "files"), problems, "$.integrity")
            if integ.get("algorithm") != "sha256":
                _err(problems, "$.integrity.algorithm", "expected 'sha256'")
            files = integ.get("files")
            if isinstance(files, dict):
                for key, value in sorted(files.items()):
                    _sha256_ref(value, problems, f"$.integrity.files.{key}")
            elif "files" in integ:
                _err(problems, "$.integrity.files", "expected object")
            if "attestation" in integ:
                _str(integ["attestation"], problems, "$.integrity.attestation")
    elif "integrity" in doc:
        _err(problems, "$.integrity", "expected object")

    if "recorded_at" in doc:
        _str(doc["recorded_at"], problems, "$.recorded_at", pattern=_TS_RE)
    rb = doc.get("recorded_by")
    if isinstance(rb, dict):
        if _closed(rb, ("agent", "version"), problems, "$.recorded_by"):
            _required(rb, ("agent", "version"), problems, "$.recorded_by")
            for key in ("agent", "version"):
                if key in rb:
                    _str(rb[key], problems, f"$.recorded_by.{key}")
    elif "recorded_by" in doc:
        _err(problems, "$.recorded_by", "expected object")
    return problems


def _obj_list(v: Any, item_check: Any, problems: list[str], path: str) -> None:
    if not isinstance(v, list) or len(v) > MAX_ITEMS:
        _err(problems, path, "expected array")
        return
    for i, item in enumerate(v):
        item_check(item, problems, f"{path}[{i}]")


_REGISTRY_ENTRY_KEYS = (
    "forge_id",
    "owner",
    "name",
    "version",
    "state",
    "scope",
    "profile",
    "hosts",
    "domains",
    "manifest",
    "installed_by",
    "installed_at",
    "updated_at",
)


def _registry_entry(v: Any, problems: list[str], path: str) -> None:
    if not _closed(v, _REGISTRY_ENTRY_KEYS, problems, path):
        return
    _required(
        v,
        (
            "forge_id",
            "owner",
            "name",
            "version",
            "state",
            "scope",
            "profile",
            "hosts",
            "domains",
            "manifest",
            "installed_by",
            "installed_at",
            "updated_at",
        ),
        problems,
        path,
    )
    for key in ("forge_id", "owner"):
        if key in v:
            _str(v[key], problems, f"{path}.{key}", pattern=_FORGE_ID_RE)
    if "name" in v:
        _str(v["name"], problems, f"{path}.name")
    if "version" in v:
        _str(v["version"], problems, f"{path}.version")
    if "state" in v:
        _enum(v["state"], MANIFEST_STATES, problems, f"{path}.state")
    if "scope" in v:
        _enum(v["scope"], SCOPES, problems, f"{path}.scope")
    if "profile" in v:
        _enum(v["profile"], PROFILES, problems, f"{path}.profile")
    if "hosts" in v:
        hosts = v["hosts"]
        if isinstance(hosts, list):
            for i, h in enumerate(hosts):
                _enum(h, HOSTS, problems, f"{path}.hosts[{i}]")
        else:
            _err(problems, f"{path}.hosts", "expected array")
    if "domains" in v:
        _str_list(v["domains"], problems, f"{path}.domains", pattern=_DOMAIN_RE)
    man = v.get("manifest")
    if isinstance(man, dict):
        if _closed(man, ("path", "sha256"), problems, f"{path}.manifest"):
            _required(man, ("path", "sha256"), problems, f"{path}.manifest")
            if "path" in man:
                _path_str(man["path"], problems, f"{path}.manifest.path")
            if "sha256" in man:
                _sha256_ref(man["sha256"], problems, f"{path}.manifest.sha256")
    elif "manifest" in v:
        _err(problems, f"{path}.manifest", "expected object")
    ib = v.get("installed_by")
    if isinstance(ib, dict):
        if _closed(ib, ("agent", "version"), problems, f"{path}.installed_by"):
            _required(ib, ("agent", "version"), problems, f"{path}.installed_by")
            for key in ("agent", "version"):
                if key in ib:
                    _str(ib[key], problems, f"{path}.installed_by.{key}")
    elif "installed_by" in v:
        _err(problems, f"{path}.installed_by", "expected object")
    for key in ("installed_at", "updated_at"):
        if key in v:
            _str(v[key], problems, f"{path}.{key}", pattern=_TS_RE)


def validate_registry(doc: Any) -> list[str]:
    """Structural validation of a ``forge/context-registry/v1`` document."""
    problems: list[str] = []
    if not isinstance(doc, dict):
        return ["$: expected object"]
    _closed(
        doc,
        (
            "schema",
            "version",
            "workspace_root",
            "forges",
            "domains_index",
            "ownership",
            "updated_at",
        ),
        problems,
        "$",
    )
    _required(
        doc,
        (
            "schema",
            "version",
            "workspace_root",
            "forges",
            "domains_index",
            "ownership",
            "updated_at",
        ),
        problems,
        "$",
    )
    if doc.get("schema") != SCHEMA_REGISTRY:
        _err(problems, "$.schema", f"expected {SCHEMA_REGISTRY!r}")
    if "version" in doc and doc["version"] != REGISTRY_FORMAT_VERSION:
        _err(problems, "$.version", f"expected {REGISTRY_FORMAT_VERSION}")
    if "workspace_root" in doc:
        _str(doc["workspace_root"], problems, "$.workspace_root")
    forges = doc.get("forges")
    if isinstance(forges, list):
        seen: set[str] = set()
        for i, entry in enumerate(forges):
            _registry_entry(entry, problems, f"$.forges[{i}]")
            fid = isinstance(entry, dict) and entry.get("forge_id")
            if isinstance(fid, str):
                if fid in seen:
                    _err(problems, f"$.forges[{i}].forge_id", f"duplicate {fid!r}")
                seen.add(fid)
    elif "forges" in doc:
        _err(problems, "$.forges", "expected array")
    idx = doc.get("domains_index")
    if isinstance(idx, dict):
        for domain, fids in sorted(idx.items()):
            if isinstance(fids, list):
                for i, fid in enumerate(fids):
                    _str(fid, problems, f"$.domains_index.{domain}[{i}]", pattern=_FORGE_ID_RE)
            else:
                _err(problems, f"$.domains_index.{domain}", "expected array")
    elif "domains_index" in doc:
        _err(problems, "$.domains_index", "expected object")
    own = doc.get("ownership")
    if isinstance(own, dict):
        _closed(own, ("policy", "files", "kinds"), problems, "$.ownership")
    elif "ownership" in doc:
        _err(problems, "$.ownership", "expected object")
    if "updated_at" in doc:
        _str(doc["updated_at"], problems, "$.updated_at", pattern=_TS_RE)
    return problems


# --------------------------------------------------------------------------
# manifest builder — real metadata in, forge/context/v1 document out
# --------------------------------------------------------------------------


def source_digest(doc: Mapping[str, Any]) -> str:
    """sha256 over the canonical JSON of a metadata document — the
    integrity attestation for ``integrity.files``."""
    return f"sha256:{_sha(_json_bytes(dict(doc)))}"


def _capability_doc(
    available: bool,
    *,
    discovery: str = "none",
    count: int | None = None,
    optional: bool = True,
    detail: str | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "available": available,
        "status": "available" if available else "unavailable",
        "discovery": discovery if available else "none",
    }
    if count is not None:
        out["count"] = count
    if optional:
        out["optional"] = True
    if detail:
        out["detail"] = detail
    return out


def _agentic_commands(agentic: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Translate ``forge/SpecialistAgenticManifest/v1`` workflows into
    forge-context discovery commands (mode enum lowercased)."""
    commands: list[dict[str, Any]] = []
    for wf in agentic.get("workflows") or []:
        if not isinstance(wf, dict):
            continue
        argv = wf.get("command")
        if not isinstance(argv, list) or not argv:
            continue
        cmd: dict[str, Any] = {
            "id": str(wf.get("id") or argv[0]),
            "argv": [str(a) for a in argv],
            "read_only": bool(wf.get("read_only", True)),
        }
        if wf.get("mode"):
            cmd["mode"] = str(wf["mode"]).lower().replace("_", "-")
        if wf.get("description"):
            cmd["description"] = str(wf["description"])
        commands.append(cmd)
    return commands


def build_manifest(
    *,
    forge_id: str,
    name: str,
    version: str,
    cli: str,
    package: str,
    distribution: str,
    python_spec: str,
    scope: str,
    profile: str = "recommended",
    hosts: Iterable[str] = (),
    protocol_version: str = "1",
    install_modes: Iterable[str] = SCOPES,
    domains: Iterable[str] = (),
    capabilities: Mapping[str, Any] | None = None,
    skills: Iterable[str] = (),
    agents: Iterable[str] = (),
    coordinators: Iterable[str] = (),
    knowledge_providers: Iterable[Mapping[str, Any]] = (),
    eval_suites: Iterable[Mapping[str, Any]] = (),
    protocols: Iterable[Mapping[str, Any]] = (),
    rule_areas: Iterable[str] = (),
    discovery_commands: Iterable[Mapping[str, Any]] = (),
    agentic: Mapping[str, Any] | None = None,
    forge_json: Mapping[str, Any] | None = None,
    mcp: Mapping[str, Any] | None = None,
    executable: str | None = None,
    venv: str | None = None,
    resources: Mapping[str, Mapping[str, Any]] | None = None,
    requires_network: bool | None = None,
    requires_credentials: bool | None = None,
    read_only_default: bool | None = None,
    mutating_verbs: Iterable[str] = (),
    requires_approval: Iterable[str] = (),
    security_notes: str | None = None,
    offline_available: bool = True,
    state: str = "available",
    degraded_reasons: Iterable[str] = (),
    health: Mapping[str, Any] | None = None,
    integrity_files: Mapping[str, str] | None = None,
    components: Mapping[str, Any] | None = None,
    recorded_by: str | None = None,
    recorded_at: str | None = None,
) -> dict[str, Any]:
    """Compose a ``forge/context/v1`` manifest from real forge metadata.

    Explicit arguments win; ``agentic`` (``forge.agentic.json``) and
    ``forge_json`` fill gaps — workflows become discovery commands, host
    adapters become supported hosts, the MCP block comes from whichever
    source declares it."""
    agentic = dict(agentic or {})
    forge_json = dict(forge_json or {})

    skill_ids = sorted(set(skills) | set(agentic.get("skills") or ()))
    agent_ids = sorted(set(agents) | set(agentic.get("agents") or ()))
    coord_ids = sorted(set(coordinators) | set(agentic.get("coordinators") or ()))
    kp_list = [dict(k) for k in knowledge_providers]
    eval_list = [dict(e) for e in eval_suites]
    proto_list = [dict(p) for p in protocols]
    commands = [dict(c) for c in discovery_commands] or _agentic_commands(agentic)
    host_list = sorted(set(hosts) | set(agentic.get("host_adapters") or ()))

    if capabilities is None:
        capabilities = {
            "skills": _capability_doc(
                bool(skill_ids), discovery="workspace-file", count=len(skill_ids)
            ),
            "agents": _capability_doc(
                bool(agent_ids or coord_ids),
                discovery="workspace-file",
                count=len(agent_ids) + len(coord_ids),
            ),
            "knowledge": _capability_doc(
                bool(kp_list), discovery="native-runtime", count=len(kp_list)
            ),
            "rules": _capability_doc(
                bool(rule_areas), discovery="native-runtime", count=len(tuple(rule_areas))
            ),
            "evals": _capability_doc(bool(eval_list), discovery="cli", count=len(eval_list)),
            "protocols": _capability_doc(
                bool(proto_list), discovery="bundled", count=len(proto_list)
            ),
        }
    else:
        capabilities = {k: dict(v) for k, v in capabilities.items()}

    if mcp is None and (forge_json.get("mcp_server_name") or agentic.get("mcp_command")):
        mcp = {
            "server_name": forge_json.get("mcp_server_name") or agentic.get("cli") or cli,
            "command": forge_json.get("mcp_command") or agentic.get("mcp_command"),
        }
    if requires_network is None:
        requires_network = bool(agentic.get("requires_network", False))
    if requires_credentials is None:
        requires_credentials = bool(agentic.get("requires_credentials", False))
    if read_only_default is None:
        read_only_default = bool(agentic.get("read_only_default", True))

    interfaces: dict[str, Any] = {
        "cli": {"name": cli, "version_cmd": [cli, "--version"]},
        "python": {"package": package, "distribution": distribution},
    }
    if agentic.get("cli_entry"):
        interfaces["cli"]["entry"] = str(agentic["cli_entry"])
    if mcp is not None:
        interfaces["mcp"] = {
            "server_name": str(mcp.get("server_name") or cli),
            "command": [str(a) for a in (mcp.get("command") or (cli, "mcp", "serve"))],
        }
        if mcp.get("verify_tool"):
            interfaces["mcp"]["verify_tool"] = str(mcp["verify_tool"])
    if executable:
        interfaces["executable"] = {"path": executable}

    res = {k: dict(v) for k, v in (resources or {}).items()}
    res.setdefault(
        "context-manifest",
        {
            "kind": "copied",
            "location": f"{CONTEXT_DIR}/{_capability_rel(forge_id)}",
            "optional": False,
        },
    )

    runtime: dict[str, Any] = {
        "python": python_spec,
        "package": package,
        "distribution": distribution,
        "requires_network": requires_network,
        "requires_credentials": requires_credentials,
        "offline_available": offline_available,
    }
    if venv:
        runtime["venv"] = venv
    if executable:
        runtime["executable"] = executable

    integ_files = dict(integrity_files or {})
    if forge_json:
        integ_files.setdefault("forge.json", source_digest(forge_json))
    if agentic:
        integ_files.setdefault("forge.agentic.json", source_digest(agentic))

    doc: dict[str, Any] = {
        "schema": SCHEMA_MANIFEST,
        "forge_id": forge_id,
        "name": name,
        "version": version,
        "protocol_version": protocol_version,
        "domains": sorted(set(domains)),
        "capabilities": capabilities,
        "skills": skill_ids,
        "agents": agent_ids,
        "coordinators": coord_ids,
        "knowledge_providers": kp_list,
        "eval_suites": eval_list,
        "protocols": proto_list,
        "rule_areas": sorted(set(rule_areas)),
        "discovery": {"commands": commands},
        "interfaces": interfaces,
        "resources": res,
        "runtime": runtime,
        "security": {
            "read_only_default": read_only_default,
            "mutating_verbs": sorted(set(mutating_verbs)),
            "requires_approval": sorted(set(requires_approval)),
        },
        "installed": {
            "scope": scope,
            "profile": profile,
            "hosts": host_list,
        },
        "install_modes": sorted(set(install_modes), key=list(SCOPES).index),
        "state": state,
        "degraded_reasons": sorted(set(degraded_reasons)),
        "health": dict(health or {"status": "unverified", "checks": []}),
        "integrity": {
            "algorithm": "sha256",
            "files": integ_files,
            "attestation": (f"forge_context/{_FORGECONTEXT_VERSION} source:{_SOURCE_SHA256}"),
        },
        "recorded_at": recorded_at or _utc_now(),
        "recorded_by": {
            "agent": recorded_by or cli,
            "version": version,
        },
    }
    if components:
        doc["installed"]["components"] = dict(components)
    if security_notes:
        doc["security"]["notes"] = security_notes
    if agentic:
        doc["discovery"]["manifest"] = "forge.agentic.json"
    problems = validate_manifest(doc)
    if problems:
        raise ContextError(E_SCHEMA, f"built manifest is invalid: {problems[:5]}")
    return doc


# --------------------------------------------------------------------------
# registry internals
# --------------------------------------------------------------------------


def _empty_registry(root: Path) -> dict[str, Any]:
    return {
        "schema": SCHEMA_REGISTRY,
        "version": REGISTRY_FORMAT_VERSION,
        "workspace_root": str(Path(root).resolve()),
        "forges": [],
        "domains_index": {},
        "ownership": {
            "policy": (
                "registry.json and ROUTING.md are shared documents regenerated "
                "deterministically from per-forge entries. "
                "capabilities/<forge-id>.json is fully-managed by <forge-id> "
                "alone — a forge never creates, overwrites or deletes another "
                "forge's manifest or registry entry."
            ),
            "files": {
                REGISTRY_NAME: "shared",
                ROUTING_NAME: "shared",
                f"{CAPABILITIES_DIR}/<forge-id>.json": "fully-managed",
            },
            "kinds": list(OWNERSHIP_KINDS),
        },
        "updated_at": _utc_now(),
    }


def _load_registry_for_write(ctx: Path, root: Path) -> tuple[dict[str, Any], list[str]]:
    """Registry doc for mutation; a corrupt file is quarantined and the
    registry rebuilt empty (repair-by-redo)."""
    notes: list[str] = []
    path = ctx / REGISTRY_NAME
    if path.exists():
        doc = _load_json(path)
        problems = validate_registry(doc)
        if doc is None or problems:
            _quarantine(path, _utc_now().replace(":", ""))
            notes.append(f"registry.json corrupt — quarantined ({len(problems) or '?'} problems)")
        else:
            return doc, notes
    return _empty_registry(root), notes


def _domains_index(forges: list[dict[str, Any]]) -> dict[str, list[str]]:
    idx: dict[str, list[str]] = {}
    for entry in forges:
        for domain in entry.get("domains") or []:
            idx.setdefault(domain, []).append(entry["forge_id"])
    return {d: sorted(set(fids)) for d, fids in sorted(idx.items())}


def _entry_from_manifest(
    manifest: dict[str, Any], cap_sha: str, prev: dict[str, Any] | None, now: str
) -> dict[str, Any]:
    inst = manifest["installed"]
    return {
        "forge_id": manifest["forge_id"],
        "owner": manifest["forge_id"],
        "name": manifest["name"],
        "version": manifest["version"],
        "state": manifest["state"],
        "scope": inst["scope"],
        "profile": inst["profile"],
        "hosts": sorted(inst.get("hosts") or []),
        "domains": sorted(manifest.get("domains") or []),
        "manifest": {
            "path": _capability_rel(manifest["forge_id"]),
            "sha256": f"sha256:{cap_sha}",
        },
        "installed_by": dict(manifest["recorded_by"]),
        "installed_at": (prev or {}).get("installed_at") or now,
        "updated_at": now,
    }


def _same_entry(prev: dict[str, Any], new: dict[str, Any]) -> bool:
    return all(prev.get(k) == new.get(k) for k in _REGISTRY_ENTRY_KEYS if k != "updated_at")


def _manifest_changed(old: dict[str, Any] | None, new: dict[str, Any]) -> bool:
    """Deep compare ignoring ``recorded_at`` — the only volatile field."""
    if old is None:
        return True

    def strip(d: dict[str, Any]) -> dict[str, Any]:
        return {k: v for k, v in d.items() if k != "recorded_at"}

    return strip(old) != strip(new)


def _load_manifests(ctx: Path) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    cap_dir = ctx / CAPABILITIES_DIR
    if not cap_dir.is_dir():
        return out
    for path in sorted(cap_dir.glob("*.json")):
        doc = _load_json(path)
        if isinstance(doc, dict) and doc.get("forge_id") == path.stem:
            out[path.stem] = doc
    return out


def _write_registry_and_routing(ctx: Path, reg: dict[str, Any], written: list[str]) -> None:
    _atomic_write(ctx / REGISTRY_NAME, _json_bytes(reg))
    written.append(REGISTRY_NAME)
    routing = routing_document(reg, _load_manifests(ctx))
    _atomic_write(ctx / ROUTING_NAME, routing.encode("utf-8"))
    written.append(ROUTING_NAME)


def _apply_register(ctx: Path, root: Path, manifest: dict[str, Any], now: str) -> list[str]:
    fid = manifest["forge_id"]
    written: list[str] = []
    cap = ctx / CAPABILITIES_DIR / f"{fid}.json"
    new_bytes = _json_bytes(manifest)
    old_doc = _load_json(cap) if cap.exists() else None
    if _manifest_changed(old_doc if isinstance(old_doc, dict) else None, manifest):
        _atomic_write(cap, new_bytes)
        written.append(_capability_rel(fid))
    cap_sha = _sha_file(cap)

    reg, notes = _load_registry_for_write(ctx, root)
    forges = {e["forge_id"]: e for e in reg["forges"]}
    prev = forges.get(fid)
    new_entry = _entry_from_manifest(manifest, cap_sha, prev, now)
    changed = prev is None or not _same_entry(prev, new_entry)
    if changed:
        forges[fid] = new_entry
    reg["forges"] = [forges[k] for k in sorted(forges)]
    reg["domains_index"] = _domains_index(reg["forges"])
    reg["updated_at"] = now
    if changed or notes or not (ctx / ROUTING_NAME).exists():
        _write_registry_and_routing(ctx, reg, written)
    return written


def _apply_unregister(ctx: Path, root: Path, forge_id: str, now: str) -> list[str]:
    """Remove our own capability file + registry entry. Callers have
    already proven ownership — this function trusts the journal."""
    removed: list[str] = []
    cap = ctx / CAPABILITIES_DIR / f"{forge_id}.json"
    if cap.exists():
        cap.unlink()
        removed.append(_capability_rel(forge_id))
    reg, notes = _load_registry_for_write(ctx, root)
    forges = {e["forge_id"]: e for e in reg["forges"]}
    had_entry = forges.pop(forge_id, None) is not None
    if had_entry:
        removed.append(REGISTRY_NAME)
    reg["forges"] = [forges[k] for k in sorted(forges)]
    reg["domains_index"] = _domains_index(reg["forges"])
    reg["updated_at"] = now
    if had_entry or notes or not (ctx / ROUTING_NAME).exists():
        written: list[str] = []
        _write_registry_and_routing(ctx, reg, written)
    return removed


def _recover_journal(ctx: Path, root: Path) -> dict[str, Any] | None:
    """Redo an interrupted op. Journaled ops were authorized before the
    journal was written, so redo does not re-check ownership."""
    jpath = ctx / JOURNAL_NAME
    if not jpath.exists():
        return None
    journal = _load_json(jpath)
    recovered: dict[str, Any] | None = None
    now = _utc_now()
    if isinstance(journal, dict):
        op = journal.get("op")
        if op == "register" and isinstance(journal.get("manifest"), dict):
            if not validate_manifest(journal["manifest"]):
                _apply_register(ctx, root, journal["manifest"], now)
                recovered = {"op": "register", "forge_id": journal["manifest"]["forge_id"]}
        elif op == "unregister" and isinstance(journal.get("forge_id"), str):
            _apply_unregister(ctx, root, journal["forge_id"], now)
            recovered = {"op": "unregister", "forge_id": journal["forge_id"]}
        if recovered is None:
            _quarantine(jpath, now.replace(":", ""))
            return {"op": "unknown", "quarantined": True}
    else:
        _quarantine(jpath, now.replace(":", ""))
        return {"op": "unparseable", "quarantined": True}
    with contextlib.suppress(OSError):
        jpath.unlink()
    return recovered


def _check_foreign_manifest(ctx: Path, forge_id: str) -> None:
    """A manifest at ``capabilities/<fid>.json`` whose ``forge_id`` is not
    ``fid`` belongs to someone else — refuse, never overwrite."""
    cap = ctx / CAPABILITIES_DIR / f"{forge_id}.json"
    if not cap.exists():
        return
    doc = _load_json(cap)
    if doc is None:
        _quarantine(cap, _utc_now().replace(":", ""))
        return
    if isinstance(doc, dict) and doc.get("forge_id") not in (None, forge_id):
        raise ContextError(
            E_OWNERSHIP,
            f"{_capability_rel(forge_id)} is owned by {doc['forge_id']!r} "
            f"(foreign-installer) — refusing to overwrite",
        )


def _check_registry_owner(ctx: Path, root: Path, forge_id: str) -> None:
    reg_path = ctx / REGISTRY_NAME
    if not reg_path.exists():
        return
    reg = _load_json(reg_path)
    if not isinstance(reg, dict):
        return
    for entry in reg.get("forges") or []:
        if (
            isinstance(entry, dict)
            and entry.get("forge_id") == forge_id
            and entry.get("owner") not in (None, forge_id)
        ):
            raise ContextError(
                E_OWNERSHIP,
                f"registry entry for {forge_id!r} is owned by {entry['owner']!r} — "
                "a forge never deletes or replaces another forge's entry",
            )


# --------------------------------------------------------------------------
# public ops
# --------------------------------------------------------------------------


def register_forge(root: Path | str, manifest: dict[str, Any], *, owner: str) -> dict[str, Any]:
    """Write ``capabilities/<fid>.json`` + upsert the registry entry +
    regenerate ``ROUTING.md``. ``owner`` is the calling forge's id — it must
    equal ``manifest["forge_id"]`` (a forge may only register itself).
    Idempotent: re-registering an unchanged manifest writes nothing."""
    problems = validate_manifest(manifest)
    if problems:
        raise ContextError(E_SCHEMA, f"manifest invalid: {'; '.join(problems[:8])}")
    fid = manifest["forge_id"]
    if owner != fid:
        raise ContextError(E_OWNERSHIP, f"{owner!r} may not register a manifest for {fid!r}")
    root = Path(root).resolve()
    ctx = context_dir(root)
    with acquire_lock(ctx) as lock:
        recovered = _recover_journal(ctx, root)
        _check_foreign_manifest(ctx, fid)
        _check_registry_owner(ctx, root, fid)
        _atomic_write(ctx / JOURNAL_NAME, _json_bytes({"op": "register", "manifest": manifest}))
        written = _apply_register(ctx, root, manifest, _utc_now())
        with contextlib.suppress(OSError):
            (ctx / JOURNAL_NAME).unlink()
    return {
        "forge_id": fid,
        "status": "registered" if written else "unchanged",
        "written": written,
        "recovered": recovered,
        "lock_recovered": bool(getattr(lock, "recovered", False)),
        "registry": str(ctx / REGISTRY_NAME),
    }


def unregister_forge(root: Path | str, forge_id: str, *, owner: str) -> dict[str, Any]:
    """Remove our own manifest + registry entry. Refuses when the caller is
    not ``forge_id`` or when the on-disk objects belong to another forge."""
    if owner != forge_id:
        raise ContextError(E_OWNERSHIP, f"{owner!r} may not unregister {forge_id!r}")
    root = Path(root).resolve()
    ctx = context_dir(root)
    with acquire_lock(ctx) as lock:
        recovered = _recover_journal(ctx, root)
        _check_foreign_manifest(ctx, forge_id)
        _check_registry_owner(ctx, root, forge_id)
        _atomic_write(ctx / JOURNAL_NAME, _json_bytes({"op": "unregister", "forge_id": forge_id}))
        removed = _apply_unregister(ctx, root, forge_id, _utc_now())
        with contextlib.suppress(OSError):
            (ctx / JOURNAL_NAME).unlink()
    return {
        "forge_id": forge_id,
        "status": "unregistered" if removed else "absent",
        "removed": removed,
        "recovered": recovered,
        "lock_recovered": bool(getattr(lock, "recovered", False)),
    }


def repair_context(root: Path | str) -> dict[str, Any]:
    """Converge the context dir: redo any journaled op, then rebuild the
    registry + ROUTING.md from the capability manifests on disk. Preserves
    ``installed_at``/``installed_by`` of surviving entries."""
    root = Path(root).resolve()
    ctx = context_dir(root)
    with acquire_lock(ctx) as lock:
        recovered = _recover_journal(ctx, root)
        reg, notes = _load_registry_for_write(ctx, root)
        manifests = _load_manifests(ctx)
        now = _utc_now()
        previous = {e["forge_id"]: e for e in reg["forges"]}
        entries = []
        for fid in sorted(manifests):
            doc = manifests[fid]
            cap_sha = _sha_file(ctx / CAPABILITIES_DIR / f"{fid}.json")
            entries.append(_entry_from_manifest(doc, cap_sha, previous.get(fid), now))
        reg["forges"] = entries
        reg["domains_index"] = _domains_index(entries)
        reg["updated_at"] = now
        written: list[str] = []
        _write_registry_and_routing(ctx, reg, written)
        # Orphaned capability files (forge_id != filename) are left alone —
        # foreign-installer content is never ours to remove.
    return {
        "status": "repaired",
        "forges": sorted(manifests),
        "recovered": recovered,
        "notes": notes,
        "written": written,
        "lock_recovered": bool(getattr(lock, "recovered", False)),
    }


def load_registry(root: Path | str) -> dict[str, Any] | None:
    """Validated registry doc, or None when absent/corrupt (read path is
    honest — it never repairs; that is ``repair_context``'s job)."""
    doc = _load_json(registry_path(root))
    if isinstance(doc, dict) and not validate_registry(doc):
        return doc
    return None


def list_capabilities(root: Path | str) -> dict[str, dict[str, Any]]:
    """All parseable, self-consistent capability manifests on disk."""
    return _load_manifests(context_dir(root))


# --------------------------------------------------------------------------
# ROUTING.md — deterministic human routing doc
# --------------------------------------------------------------------------


def routing_document(
    registry: dict[str, Any], manifests: Mapping[str, dict[str, Any]] | None = None
) -> str:
    """``ROUTING.md`` from a validated registry. Deterministic: sorted
    everywhere, no timestamps — same registry in, same bytes out."""
    manifests = dict(manifests or {})
    lines: list[str] = [
        "# Forge Context — Routing",
        "",
        "Regenerated deterministically from `.forge/context/registry.json`",
        f"(`{SCHEMA_REGISTRY}`). Managed document — manual edits are lost.",
        "",
        "## Domains",
        "",
    ]
    index = registry.get("domains_index") or {}
    entries = {e["forge_id"]: e for e in registry.get("forges") or []}
    if index:
        lines += ["| Domain | Forge | State | Scope |", "|---|---|---|---|"]
        for domain in sorted(index):
            for fid in index[domain]:
                e = entries.get(fid, {})
                lines.append(
                    f"| {domain} | {fid} | {e.get('state', '?')} | {e.get('scope', '?')} |"
                )
    else:
        lines.append("_No domains registered._")
    lines += ["", "## Ambiguity", ""]
    ambiguous = {d: fids for d, fids in index.items() if len(fids) > 1}
    if ambiguous:
        lines += [
            "Domains claimed by more than one forge — route by task scope",
            "and verify availability before dispatch:",
            "",
            "| Domain | Forges |",
            "|---|---|",
        ]
        for domain in sorted(ambiguous):
            lines.append(f"| {domain} | {', '.join(ambiguous[domain])} |")
    else:
        lines.append("_No domain is claimed by more than one forge._")
    lines += ["", "## Forges", ""]
    forges = sorted(registry.get("forges") or [], key=lambda e: e["forge_id"])
    if not forges:
        lines.append("_No forges registered in this workspace._")
    for e in forges:
        fid = e["forge_id"]
        manifest = manifests.get(fid) or {}
        lines.append(f"### {fid} — {e.get('name', fid)} {e.get('version', '')}".rstrip())
        lines.append("")
        lines.append(
            f"- state: {e.get('state', '?')} · scope: {e.get('scope', '?')} · "
            f"profile: {e.get('profile', '?')}"
        )
        if e.get("hosts"):
            lines.append(f"- hosts: {', '.join(e['hosts'])}")
        if e.get("domains"):
            lines.append(f"- domains: {', '.join(e['domains'])}")
        caps = manifest.get("capabilities") or {}
        if caps:
            kinds = ", ".join(
                f"{k}({'on' if c.get('available') else 'off'})" for k, c in sorted(caps.items())
            )
            lines.append(f"- capabilities: {kinds}")
        iface = manifest.get("interfaces") or {}
        cli = (iface.get("cli") or {}).get("name")
        if cli:
            lines.append(f"- cli: `{cli}`")
        mcp = (iface.get("mcp") or {}).get("server_name")
        if mcp:
            lines.append(f"- mcp: `{mcp}`")
        lines.append(f"- manifest: `{(e.get('manifest') or {}).get('path', '?')}`")
        lines.append("")
    lines += [
        "## Contract",
        "",
        "- Capability manifest: `forge/context/v1` — `.forge/context/capabilities/<forge-id>.json`",
        "- Workspace registry: `forge/context-registry/v1` — `.forge/context/registry.json`",
        "- Ownership: shared docs regenerate from per-forge entries; a forge",
        "  never deletes another forge's resources.",
        "",
    ]
    return "\n".join(lines)


__all__ = [
    "CAPABILITY_DISCOVERY",
    "CAPABILITIES_DIR",
    "CHECK_STATUSES",
    "COMMAND_MODES",
    "CONTEXT_DIR",
    "ContextError",
    "E_LOCKED",
    "E_OWNERSHIP",
    "E_PATH",
    "E_SCHEMA",
    "EVAL_KINDS",
    "HEALTH_STATUSES",
    "HOSTS",
    "JOURNAL_NAME",
    "LOCK_NAME",
    "LockError",
    "MANIFEST_STATES",
    "OWNERSHIP_KINDS",
    "PROFILES",
    "REGISTRY_FORMAT_VERSION",
    "REGISTRY_NAME",
    "RESOURCE_KINDS",
    "ROUTING_NAME",
    "SCHEMA_MANIFEST",
    "SCHEMA_REGISTRY",
    "SCOPES",
    "acquire_lock",
    "build_manifest",
    "capability_path",
    "context_dir",
    "list_capabilities",
    "load_registry",
    "register_forge",
    "registry_path",
    "repair_context",
    "routing_document",
    "routing_path",
    "source_digest",
    "unregister_forge",
    "validate_manifest",
    "validate_registry",
]
