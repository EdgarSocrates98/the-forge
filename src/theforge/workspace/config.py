"""Declarative workspace configuration — ``forge.workspace.yaml`` (cycle 16.1, §6.7).

The file stays optional and backward compatible: the ``forge_workspace: true``
marker written by ``theforge init`` and the ``kind: forge/Workspace/v1`` form
from the workspace guide both parse. A versioned, optional ``forge:`` block
stores durable setup choices::

    kind: forge/Workspace/v1
    members:
      - path: backend-api
      - path: data-pipelines
    forge:
      installation_profile: full
      gateway_profile: deep
      hosts: [claude, codex]
      specialists:
        mode: all          # all | recommended | manual
        include: []        # forge ids when mode == manual

Core is stdlib-only — there is no PyYAML — so the reader parses a strict
YAML *subset* (block mappings, block sequences, ``[a, b]`` flow lists,
quoted/plain scalars, comments). Anything outside the subset (anchors,
block scalars, flow mappings, multiple documents, tabs) makes the file
unparseable and is reported as a warning, never misparsed.

Two honesty rules: unknown fields are ignored with a warning (forward
compatibility), and anything that looks like a secret — a sensitive key
name or a value matching the redaction patterns — is rejected with a
warning; declarative configuration must never carry credentials.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Final

from theforge.host_detect import KNOWN_HOSTS
from theforge.security.redact import redact_text
from theforge.state import WORKSPACE_MARKER

__all__ = [
    "MAX_CONFIG_BYTES",
    "WORKSPACE_KIND",
    "WorkspaceConfig",
    "load_workspace_config",
]

WORKSPACE_KIND: Final = "forge/Workspace/v1"
MAX_CONFIG_BYTES: Final = 64 * 1024
INSTALLATION_PROFILES: Final = frozenset({"minimal", "recommended", "full"})
GATEWAY_PROFILES: Final = frozenset({"economy", "balanced", "deep"})
SPECIALIST_MODES: Final = frozenset({"all", "recommended", "manual"})
_FORGE_ID: Final = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
_MAP_KEY: Final = re.compile(r"^[A-Za-z0-9_.-]+$")
_SENSITIVE_KEY: Final = re.compile(
    r"(?i)(api[_-]?key|secret|token|password|passwd|credential|"
    r"private[_-]?key|access[_-]?key|authorization|client[_-]?secret)"
)
_INT: Final = re.compile(r"^-?\d+$")


class _YamlError(ValueError):
    """Input outside the supported YAML subset — the file is ignored, never guessed."""


@dataclass(frozen=True)
class WorkspaceConfig:  # noqa: D101 — fields documented inline above
    """Parsed, validated view of ``forge.workspace.yaml``."""

    path: str
    kind: str | None = None
    members: tuple[str, ...] = ()
    installation_profile: str | None = None
    gateway_profile: str | None = None
    hosts: tuple[str, ...] | None = None  # None = not declared; () = explicit no-host
    specialists_mode: str | None = None
    specialists_include: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    declared: bool = False  # a ``forge:`` block was present

    def setup_doc(self) -> dict[str, Any]:
        """Receipt-facing summary: what the file declared, what was applied."""
        declared_forge: dict[str, Any] = {}
        if self.installation_profile:
            declared_forge["installation_profile"] = self.installation_profile
        if self.gateway_profile:
            declared_forge["gateway_profile"] = self.gateway_profile
        if self.hosts is not None:
            declared_forge["hosts"] = list(self.hosts)
        if self.specialists_mode:
            declared_forge["specialists"] = {
                "mode": self.specialists_mode,
                "include": list(self.specialists_include),
            }
        return {
            "path": self.path,
            "kind": self.kind,
            "members": list(self.members),
            "forge": declared_forge,
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class _Line:
    indent: int
    content: str


def load_workspace_config(root: Path) -> WorkspaceConfig | None:
    """Read ``forge.workspace.yaml`` at ``root``; ``None`` when the file is absent.

    Unreadable, oversized or unparseable files yield a config carrying only
    warnings — callers surface them, setup falls back to its defaults.
    """
    path = Path(root) / WORKSPACE_MARKER
    warnings: list[str] = []
    try:
        if path.is_symlink():
            warnings.append(f"{WORKSPACE_MARKER}: is a symlink — ignored")
            return WorkspaceConfig(path=str(path), warnings=tuple(warnings))
        if not path.is_file():
            return None
        raw = path.read_bytes()
    except OSError as exc:
        return WorkspaceConfig(
            path=str(path), warnings=(f"{WORKSPACE_MARKER}: unreadable ({type(exc).__name__})",)
        )
    if len(raw) > MAX_CONFIG_BYTES:
        return WorkspaceConfig(
            path=str(path),
            warnings=(f"{WORKSPACE_MARKER}: larger than {MAX_CONFIG_BYTES} bytes — ignored",),
        )
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return WorkspaceConfig(
            path=str(path), warnings=(f"{WORKSPACE_MARKER}: not utf-8 — ignored",)
        )
    try:
        data = _parse_document(text)
    except _YamlError as exc:
        return WorkspaceConfig(
            path=str(path),
            warnings=(f"{WORKSPACE_MARKER}: outside the supported yaml subset ({exc}) — ignored",),
        )
    if data is None:
        return WorkspaceConfig(path=str(path))
    if not isinstance(data, dict):
        return WorkspaceConfig(
            path=str(path), warnings=(f"{WORKSPACE_MARKER}: root is not a mapping — ignored",)
        )
    _drop_secrets(data, warnings)
    return _validate(str(path), data, warnings)


# --------------------------------------------------------------------------
# YAML subset parser — deterministic, total (every line is consumed or errors)
# --------------------------------------------------------------------------


def _strip_comment(text: str) -> str:
    in_single = in_double = False
    for i, ch in enumerate(text):
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif ch == "#" and not in_single and not in_double and (i == 0 or text[i - 1] in " \t"):
            return text[:i].rstrip()
    return text


def _tokenize(text: str) -> list[_Line]:
    out: list[_Line] = []
    for raw in text.splitlines():
        stripped = raw.lstrip(" ")
        if stripped.startswith("\t") or "\t" in raw[: len(raw) - len(stripped)]:
            raise _YamlError("tab indentation is not supported")
        if not stripped or stripped.startswith("#"):
            continue
        if stripped in ("---", "..."):  # document markers — tolerated, ignored
            continue
        content = _strip_comment(stripped)
        if content:
            out.append(_Line(len(raw) - len(stripped), content))
    return out


def _scalar(token: str) -> Any:
    token = token.strip()
    if not token:
        return None
    if token.startswith("[") and token.endswith("]"):
        inner = token[1:-1].strip()
        return [_scalar(part) for part in inner.split(",")] if inner else []
    if token[0] in "{}&*!|>":
        raise _YamlError(f"unsupported construct at {token[:24]!r}")
    if len(token) >= 2 and token[0] == token[-1] and token[0] in "\"'":
        body = token[1:-1]
        if token[0] == '"':
            body = body.replace('\\"', '"').replace("\\\\", "\\")
        else:
            body = body.replace("''", "'")
        return body
    low = token.lower()
    if low in ("true", "false"):
        return low == "true"
    if low in ("null", "~"):
        return None
    if _INT.match(token):
        return int(token)
    return token


def _parse(lines: list[_Line], i: int, indent: int) -> tuple[Any, int]:
    if i >= len(lines) or lines[i].indent < indent:
        return None, i
    if lines[i].content == "-" or lines[i].content.startswith("- "):
        return _parse_seq(lines, i, indent)
    return _parse_map(lines, i, indent)


def _parse_map(lines: list[_Line], i: int, indent: int) -> tuple[dict[str, Any], int]:
    out: dict[str, Any] = {}
    while i < len(lines):
        line = lines[i]
        if line.indent != indent or line.content.startswith("-"):
            break
        key, sep, rest = line.content.partition(":")
        if not sep:
            raise _YamlError(f"expected 'key:' at {line.content[:32]!r}")
        key = key.strip()
        if not _MAP_KEY.match(key):
            raise _YamlError(f"unsupported key {key[:32]!r}")
        rest = rest.strip()
        i += 1
        if rest:
            out[key] = _scalar(rest)
        elif i < len(lines) and lines[i].indent > indent:
            out[key], i = _parse(lines, i, lines[i].indent)
        else:
            out[key] = None
    return out, i


def _parse_seq(lines: list[_Line], i: int, indent: int) -> tuple[list[Any], int]:
    out: list[Any] = []
    while i < len(lines):
        line = lines[i]
        if line.indent != indent or not (line.content == "-" or line.content.startswith("- ")):
            break
        if line.content == "-":
            i += 1
            if i < len(lines) and lines[i].indent > indent:
                value, i = _parse(lines, i, lines[i].indent)
                out.append(value)
            else:
                out.append(None)
            continue
        rest = line.content[2:].strip()
        key, sep, value = rest.partition(":")
        # ``- key: value`` opens a mapping item — but only when the colon is
        # followed by a space or ends the line (``- https://x`` is a scalar,
        # never a key). ``- key:value`` without the space is invalid YAML and
        # stays a scalar string.
        is_map_item = sep and _MAP_KEY.match(key.strip()) and (not value or value.startswith(" "))
        if is_map_item:
            item: dict[str, Any] = {key.strip(): _scalar(value) if value.strip() else None}
            i += 1
            if i < len(lines) and lines[i].indent > indent:
                more, i = _parse(lines, i, lines[i].indent)
                if not isinstance(more, dict):
                    raise _YamlError("a sequence item cannot mix a mapping and a block")
                item.update(more)
            out.append(item)
            continue
        out.append(_scalar(rest))
        i += 1
    return out, i


def _parse_document(text: str) -> Any:
    lines = _tokenize(text)
    if not lines:
        return None
    if lines[0].indent != 0:
        raise _YamlError("document does not start at column 0")
    value, i = _parse(lines, 0, 0)
    if i != len(lines):
        raise _YamlError(f"unconsumed line {lines[i].content[:32]!r}")
    return value


# --------------------------------------------------------------------------
# secrets scan + validation
# --------------------------------------------------------------------------


def _drop_secrets(node: Any, warnings: list[str], trail: str = "") -> None:
    """Remove sensitive-looking keys/values in place; every drop is a warning."""
    if isinstance(node, dict):
        for key in list(node):
            if _SENSITIVE_KEY.search(str(key)):
                del node[key]
                warnings.append(f"{trail}{key}: sensitive key — value ignored")
                continue
            value = node[key]
            if isinstance(value, str) and redact_text(value) != value:
                node[key] = None
                warnings.append(f"{trail}{key}: secrets-looking value — ignored")
            else:
                _drop_secrets(value, warnings, f"{trail}{key}.")
    elif isinstance(node, list):
        for item in node:
            _drop_secrets(item, warnings, trail)


def _str_list(value: Any) -> tuple[str, ...] | None:
    if isinstance(value, str):
        return (value,)
    if isinstance(value, list) and all(isinstance(v, str) for v in value):
        return tuple(value)
    return None


def _member_path(value: Any, warnings: list[str]) -> str | None:
    if isinstance(value, str):
        raw_path: Any = value
    elif isinstance(value, dict):
        raw_path = value.get("path")
    else:
        raw_path = None
    if not isinstance(raw_path, str) or not raw_path.strip():
        warnings.append(f"members: entry {str(value)[:40]!r} has no path — ignored")
        return None
    path = raw_path.strip()
    posix = PurePosixPath(path)
    if (
        len(path) > 200
        or posix.is_absolute()
        or ".." in posix.parts
        or path.startswith("~")
        or "\\" in path
    ):
        warnings.append(f"members: unsafe path {path[:40]!r} — ignored")
        return None
    return path


def _validate(path: str, data: dict[str, Any], warnings: list[str]) -> WorkspaceConfig:
    kind = data.get("kind")
    if kind is not None:
        if not isinstance(kind, str):
            warnings.append("kind: not a string — ignored")
            kind = None
        elif kind != WORKSPACE_KIND:
            warnings.append(f"kind {kind!r}: expected {WORKSPACE_KIND!r}; known fields still read")

    members: list[str] = []
    raw_members = data.get("members")
    if raw_members is not None:
        if not isinstance(raw_members, list):
            warnings.append("members: not a list — ignored")
        else:
            if len(raw_members) > 256:
                warnings.append("members: truncated at 256 entries")
            for item in raw_members[:256]:
                rel = _member_path(item, warnings)
                if rel:
                    members.append(rel)

    forge = data.get("forge")
    declared = forge is not None
    installation_profile = gateway_profile = specialists_mode = None
    hosts: tuple[str, ...] | None = None
    include: tuple[str, ...] = ()
    if forge is not None:
        if not isinstance(forge, dict):
            warnings.append("forge: not a mapping — ignored")
            declared = False
        else:
            for key in forge:
                if key not in {
                    "installation_profile",
                    "gateway_profile",
                    "hosts",
                    "specialists",
                }:
                    warnings.append(f"forge.{key}: unknown field — ignored")
            ip = forge.get("installation_profile")
            if ip is not None:
                if ip in INSTALLATION_PROFILES:
                    installation_profile = str(ip)
                else:
                    warnings.append(f"forge.installation_profile {ip!r}: unknown — ignored")
            gp = forge.get("gateway_profile")
            if gp is not None:
                if gp in GATEWAY_PROFILES:
                    gateway_profile = str(gp)
                else:
                    warnings.append(f"forge.gateway_profile {gp!r}: unknown — ignored")
            raw_hosts = forge.get("hosts")
            if raw_hosts is not None:
                parsed = _str_list(raw_hosts)
                if parsed is None:
                    warnings.append("forge.hosts: expected a string or string list — ignored")
                else:
                    bad = [h for h in parsed if h not in KNOWN_HOSTS]
                    for h in bad:
                        warnings.append(f"forge.hosts {h!r}: unknown host — ignored")
                    hosts = tuple(dict.fromkeys(h for h in parsed if h in KNOWN_HOSTS))
            spec = forge.get("specialists")
            if spec is not None:
                if not isinstance(spec, dict):
                    warnings.append("forge.specialists: not a mapping — ignored")
                else:
                    for key in spec:
                        if key not in {"mode", "include"}:
                            warnings.append(f"forge.specialists.{key}: unknown field — ignored")
                    mode = spec.get("mode")
                    if mode is not None:
                        if mode in SPECIALIST_MODES:
                            specialists_mode = str(mode)
                        else:
                            warnings.append(
                                f"forge.specialists.mode {mode!r}: "
                                "expected all|recommended|manual — ignored"
                            )
                    raw_include = spec.get("include")
                    if raw_include is not None:
                        parsed_include = _str_list(raw_include)
                        if parsed_include is None:
                            warnings.append(
                                "forge.specialists.include: expected a string list — ignored"
                            )
                        else:
                            good = []
                            for fid in parsed_include:
                                if _FORGE_ID.match(fid):
                                    good.append(fid)
                                else:
                                    warnings.append(
                                        f"forge.specialists.include {fid!r}: "
                                        "invalid forge id — ignored"
                                    )
                            include = tuple(dict.fromkeys(good))
    return WorkspaceConfig(
        path=path,
        kind=kind,
        members=tuple(dict.fromkeys(members)),
        installation_profile=installation_profile,
        gateway_profile=gateway_profile,
        hosts=hosts,
        specialists_mode=specialists_mode,
        specialists_include=include,
        warnings=tuple(warnings),
        declared=declared,
    )
