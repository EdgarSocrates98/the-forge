"""Agentic asset audit: drift between the Kiro skill mirrors of each host and host instructions.

Maintenance tool (agentic-maintainability), never part of the ``theforge`` package: stdlib only,
it never imports ``theforge`` and ``theforge`` never imports it.

This module holds the foundation shared by the audit and the parity tests:

- ``load_config``: reads and validates ``agentic.toml`` (declarative and versioned next to this
  file), rejecting unknown keys, wrong types and empty reasons with an error naming the key;
- ``tracked_files``: the inventory, taken only from files tracked by git (``git ls-files``),
  read-only, with fsmonitor disabled and a minimal environment, so local untracked assets
  never change the result;
- ``normalize_text`` / ``read_text``: every text is compared with LF line endings, so a
  Windows checkout (CRLF) and a Linux checkout produce the same result.

Usage (the report and exit codes arrive with the audit itself)::

    python scripts/agentic/audit_assets.py [--root DIR] [--config FILE] [--json]
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

__all__ = [
    "DEFAULT_CONFIG", "GIT_TIMEOUT_S", "Accepted", "AgenticConfig", "AgenticConfigError",
    "AgenticGitError", "HostConfig", "HostOnly", "InstallPlaceholder", "Invariants", "MovedRule",
    "load_config", "normalize_text", "read_text", "tracked_files",
]

DEFAULT_CONFIG = Path(__file__).resolve().with_name("agentic.toml")
GIT_TIMEOUT_S = 30.0


class AgenticConfigError(Exception):
    """``agentic.toml`` is unreadable or invalid; the message names the offending key."""


class AgenticGitError(Exception):
    """The tracked-file inventory could not be obtained (git missing, failing or no repo)."""


# --- configuration -------------------------------------------------------------------------

@dataclass(frozen=True)
class HostConfig:
    name: str
    skills_dir: str
    instructions: tuple[str, ...]
    host_metadata: tuple[str, ...]  # per-skill host metadata files (e.g. agents/openai.yaml)


@dataclass(frozen=True)
class InstallPlaceholder:
    pattern: re.Pattern[str]
    replacement: str


@dataclass(frozen=True)
class HostOnly:
    path: str
    host: str
    reason: str


@dataclass(frozen=True)
class Accepted:
    skill: str
    element: str
    hosts: tuple[str, ...]  # sorted
    value: str
    reason: str


@dataclass(frozen=True)
class Invariants:
    begin: str
    end: str
    required: tuple[str, ...]


@dataclass(frozen=True)
class MovedRule:
    anchor: str
    source: str  # TOML key ``from``
    target: str  # TOML key ``to``


@dataclass(frozen=True)
class AgenticConfig:
    hosts: tuple[HostConfig, ...]  # sorted by name
    reference_rules_dir: str | None
    install_placeholders: tuple[InstallPlaceholder, ...]
    host_only: tuple[HostOnly, ...]
    accepted: tuple[Accepted, ...]
    # Optional instruction checks: ``None`` means the section is not declared and the
    # corresponding check does not run.
    invariants: Invariants | None
    budgets: dict[str, int] | None
    pointers: dict[str, tuple[str, ...]] | None
    moved_rules: tuple[MovedRule, ...] | None


_TOP_KEYS = frozenset({
    "hosts", "reference", "install_placeholders", "host_only", "accepted", "invariants",
    "budgets", "pointers", "moved_rules",
})


def _fail(key: str, problem: str) -> AgenticConfigError:
    return AgenticConfigError(f"invalid key '{key}': {problem}")


def _table(value: object, key: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise _fail(key, "expected a table")
    return value


def _check_keys(
    table: Mapping[str, object], key: str, *, required: frozenset[str],
    optional: frozenset[str] = frozenset(),
) -> None:
    for name in sorted(table):
        if name not in required | optional:
            raise _fail(_join(key, name), "unknown key")
    for name in sorted(required):
        if name not in table:
            raise _fail(_join(key, name), "missing required key")


def _join(prefix: str, name: str) -> str:
    return f"{prefix}.{name}" if prefix else name


def _text(value: object, key: str, *, reason: bool = False) -> str:
    if not isinstance(value, str):
        raise _fail(key, "expected a string")
    if not value.strip():
        raise _fail(key, "must not be empty" + (" (every entry needs a reason)" if reason else ""))
    return value


def _texts(value: object, key: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise _fail(key, "expected a list of strings")
    return tuple(_text(item, key) for item in value)


def _entries(value: object, key: str) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise _fail(key, "expected an array of tables")
    return [_table(item, f"{key}[{index}]") for index, item in enumerate(value)]


def _host_name(value: object, key: str, hosts: frozenset[str]) -> str:
    name = _text(value, key)
    if name not in hosts:
        raise _fail(key, f"unknown host {name!r} (declared: {', '.join(sorted(hosts))})")
    return name


def _parse_hosts(raw: object) -> tuple[HostConfig, ...]:
    table = _table(raw, "hosts")
    if not table:
        raise _fail("hosts", "at least one host must be declared")
    hosts: list[HostConfig] = []
    for name in sorted(table):
        key = f"hosts.{name}"
        host = _table(table[name], key)
        _check_keys(host, key, required=frozenset({"skills_dir", "instructions"}),
                    optional=frozenset({"host_metadata"}))
        hosts.append(HostConfig(
            name=name,
            skills_dir=_text(host["skills_dir"], f"{key}.skills_dir"),
            instructions=_texts(host["instructions"], f"{key}.instructions"),
            host_metadata=_texts(host.get("host_metadata", []), f"{key}.host_metadata"),
        ))
    return tuple(hosts)


def _parse_placeholders(raw: object) -> tuple[InstallPlaceholder, ...]:
    placeholders: list[InstallPlaceholder] = []
    for index, entry in enumerate(_entries(raw, "install_placeholders")):
        key = f"install_placeholders[{index}]"
        _check_keys(entry, key, required=frozenset({"pattern", "replacement"}))
        pattern = _text(entry["pattern"], f"{key}.pattern")
        try:
            compiled = re.compile(pattern)
        except re.error as exc:
            raise _fail(f"{key}.pattern", f"invalid regular expression: {exc}") from None
        replacement = entry["replacement"]
        if not isinstance(replacement, str):
            raise _fail(f"{key}.replacement", "expected a string")
        placeholders.append(InstallPlaceholder(pattern=compiled, replacement=replacement))
    return tuple(placeholders)


def _parse_host_only(raw: object, hosts: frozenset[str]) -> tuple[HostOnly, ...]:
    items: list[HostOnly] = []
    for index, entry in enumerate(_entries(raw, "host_only")):
        key = f"host_only[{index}]"
        _check_keys(entry, key, required=frozenset({"path", "host", "reason"}))
        items.append(HostOnly(
            path=_text(entry["path"], f"{key}.path"),
            host=_host_name(entry["host"], f"{key}.host", hosts),
            reason=_text(entry["reason"], f"{key}.reason", reason=True),
        ))
    return tuple(items)


def _parse_accepted(raw: object, hosts: frozenset[str]) -> tuple[Accepted, ...]:
    items: list[Accepted] = []
    for index, entry in enumerate(_entries(raw, "accepted")):
        key = f"accepted[{index}]"
        _check_keys(entry, key,
                    required=frozenset({"skill", "element", "hosts", "value", "reason"}))
        names = _texts(entry["hosts"], f"{key}.hosts")
        if not names:
            raise _fail(f"{key}.hosts", "must name at least one host")
        items.append(Accepted(
            skill=_text(entry["skill"], f"{key}.skill"),
            element=_text(entry["element"], f"{key}.element"),
            hosts=tuple(sorted(_host_name(n, f"{key}.hosts", hosts) for n in names)),
            value=_text(entry["value"], f"{key}.value"),
            reason=_text(entry["reason"], f"{key}.reason", reason=True),
        ))
    return tuple(items)


def _parse_invariants(raw: object) -> Invariants:
    table = _table(raw, "invariants")
    _check_keys(table, "invariants", required=frozenset({"begin", "end", "required"}))
    return Invariants(
        begin=_text(table["begin"], "invariants.begin"),
        end=_text(table["end"], "invariants.end"),
        required=_texts(table["required"], "invariants.required"),
    )


def _parse_budgets(raw: object) -> dict[str, int]:
    budgets: dict[str, int] = {}
    for path, value in sorted(_table(raw, "budgets").items()):
        key = f"budgets.{path}"
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise _fail(key, "expected a positive integer (bytes)")
        budgets[path] = value
    return budgets


def _parse_pointers(raw: object) -> dict[str, tuple[str, ...]]:
    return {path: _texts(value, f"pointers.{path}")
            for path, value in sorted(_table(raw, "pointers").items())}


def _parse_moved_rules(raw: object) -> tuple[MovedRule, ...]:
    rules: list[MovedRule] = []
    for index, entry in enumerate(_entries(raw, "moved_rules")):
        key = f"moved_rules[{index}]"
        _check_keys(entry, key, required=frozenset({"anchor", "from", "to"}))
        rules.append(MovedRule(
            anchor=_text(entry["anchor"], f"{key}.anchor"),
            source=_text(entry["from"], f"{key}.from"),
            target=_text(entry["to"], f"{key}.to"),
        ))
    return tuple(rules)


def load_config(path: Path) -> AgenticConfig:
    """Read and validate ``agentic.toml``; any problem raises ``AgenticConfigError``."""
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise AgenticConfigError(f"cannot read {path}: {exc.strerror or exc}") from None
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise AgenticConfigError(f"invalid TOML in {path}: {exc}") from None
    _check_keys(raw, "", required=frozenset({"hosts"}), optional=_TOP_KEYS)
    hosts = _parse_hosts(raw["hosts"])
    names = frozenset(host.name for host in hosts)
    reference_rules_dir: str | None = None
    if "reference" in raw:
        reference = _table(raw["reference"], "reference")
        _check_keys(reference, "reference", required=frozenset({"rules_dir"}))
        reference_rules_dir = _text(reference["rules_dir"], "reference.rules_dir")
    return AgenticConfig(
        hosts=hosts,
        reference_rules_dir=reference_rules_dir,
        install_placeholders=_parse_placeholders(raw.get("install_placeholders", [])),
        host_only=_parse_host_only(raw.get("host_only", []), names),
        accepted=_parse_accepted(raw.get("accepted", []), names),
        invariants=_parse_invariants(raw["invariants"]) if "invariants" in raw else None,
        budgets=_parse_budgets(raw["budgets"]) if "budgets" in raw else None,
        pointers=_parse_pointers(raw["pointers"]) if "pointers" in raw else None,
        moved_rules=_parse_moved_rules(raw["moved_rules"]) if "moved_rules" in raw else None,
    )


# --- text ----------------------------------------------------------------------------------

def normalize_text(text: str) -> str:
    """Normalize line endings to LF (Windows CRLF checkouts compare equal to Linux ones)."""
    return text.replace("\r\n", "\n")


def read_text(repo: Path, relpath: str) -> str:
    """Read a repository file (POSIX path relative to ``repo``) as UTF-8 with LF endings."""
    return normalize_text((repo / relpath).read_text(encoding="utf-8"))


# --- tracked inventory ---------------------------------------------------------------------

def _git_env(repo: Path) -> dict[str, str]:
    """Minimal environment: no inherited ``GIT_*``, no system config, never prompt or lock."""
    env = {"PATH": os.environ.get("PATH", os.defpath)}
    if os.name == "nt":
        for name in ("SYSTEMROOT", "SYSTEMDRIVE"):
            value = os.environ.get(name)
            if value:
                env[name] = value
    env.update({
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_TERMINAL_PROMPT": "0",
        "LC_ALL": "C",
        # Never discover a repository above ``repo``: the inventory is the checkout's own.
        "GIT_CEILING_DIRECTORIES": str(repo.resolve().parent),
    })
    return env


def tracked_files(repo: Path) -> frozenset[str]:
    """POSIX paths (relative to ``repo``) of the files tracked by git; never writes.

    Raises ``AgenticGitError`` when git is missing, fails or ``repo`` is not a checkout.
    """
    git = shutil.which("git")
    if git is None:
        raise AgenticGitError("git executable not found on PATH")
    argv = [git, "-c", "core.fsmonitor=false", "ls-files", "-z", "--cached"]
    try:
        proc = subprocess.run(
            argv, cwd=repo, env=_git_env(repo), stdin=subprocess.DEVNULL,
            capture_output=True, timeout=GIT_TIMEOUT_S, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise AgenticGitError(f"git ls-files failed in {repo}: {exc}") from None
    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", "replace").strip().splitlines()
        raise AgenticGitError(
            f"git ls-files failed in {repo} (exit {proc.returncode})"
            + (f": {detail[-1]}" if detail else "")
        )
    entries = proc.stdout.decode("utf-8", "surrogateescape").split("\0")
    return frozenset(entry for entry in entries if entry)
