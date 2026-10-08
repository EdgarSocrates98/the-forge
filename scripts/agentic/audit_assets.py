"""Agentic asset audit: drift between the skill mirrors of each host and host instructions.

Equivalent skills are the directories under each host's ``skills_dir`` whose names start with a
``[skills].prefixes`` prefix (``kiro-*`` hand-edited mirrors and ``forge-*`` ecosystem skills
rendered from ``agentic/skills/`` by ``render_skills.py``).


Maintenance tool (agentic-maintainability), never part of the ``theforge`` package: stdlib only,
it never imports ``theforge`` and ``theforge`` never imports it. It only reads: no network, no
writes, and only files tracked by git (local untracked assets never change the result).

- ``load_config``: reads and validates ``agentic.toml`` (declarative and versioned next to this
  file), rejecting unknown keys, wrong types and empty reasons with an error naming the key;
- ``tracked_files``: the inventory, taken only from files tracked by git (``git ls-files``),
  read-only, with fsmonitor disabled and a minimal environment;
- ``normalize_text`` / ``read_text``: every text is compared with LF line endings, so a
  Windows checkout (CRLF) and a Linux checkout produce the same result;
- ``profile_skill``: the semantic profile of a skill (frontmatter name, repository paths,
  referenced skills, ``spec.json`` phases, support files), tolerant to host syntax;
- ``audit``: equivalent skills, support files (between hosts and against the reference copies),
  host-only assets, accepted divergences and instruction checks (invariants block, budgets,
  pointers, moved rules) into a totally ordered ``AuditReport``;
- ``main``: command line, exit 0 without failing findings, 1 with failing findings, 2 for a
  configuration or git error (never a traceback).

Usage::

    python scripts/agentic/audit_assets.py [--root DIR] [--config FILE] [--json]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tomllib
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

__all__ = [
    "DEFAULT_CONFIG",
    "DEFAULT_ROOT",
    "FAILING",
    "GIT_TIMEOUT_S",
    "Accepted",
    "AgenticConfig",
    "AgenticConfigError",
    "AgenticGitError",
    "AuditReport",
    "Finding",
    "FindingKind",
    "HostConfig",
    "HostOnly",
    "InstallPlaceholder",
    "Invariants",
    "MovedRule",
    "SkillProfile",
    "audit",
    "load_config",
    "main",
    "normalize_text",
    "profile_skill",
    "read_text",
    "tracked_files",
]

DEFAULT_CONFIG = Path(__file__).resolve().with_name("agentic.toml")
DEFAULT_ROOT = Path(__file__).resolve().parents[2]
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
    # Directories holding this host's agentic assets; every tracked file under them must belong
    # to an equivalent skill or be declared in [[host_only]]. Default: top of ``skills_dir``.
    asset_dirs: tuple[str, ...] = ()


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
    # Directory prefixes that count as skills under each skills_dir (e.g. "kiro-",
    # "forge-"); everything else there must be [[host_only]].
    skill_prefixes: tuple[str, ...]


_TOP_KEYS = frozenset(
    {
        "hosts",
        "reference",
        "install_placeholders",
        "host_only",
        "accepted",
        "invariants",
        "budgets",
        "pointers",
        "moved_rules",
        "skills",
    }
)


def _fail(key: str, problem: str) -> AgenticConfigError:
    return AgenticConfigError(f"invalid key '{key}': {problem}")


def _table(value: object, key: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise _fail(key, "expected a table")
    return value


def _check_keys(
    table: Mapping[str, object],
    key: str,
    *,
    required: frozenset[str],
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
        _check_keys(
            host,
            key,
            required=frozenset({"skills_dir", "instructions"}),
            optional=frozenset({"host_metadata", "asset_dirs"}),
        )
        skills_dir = _text(host["skills_dir"], f"{key}.skills_dir").strip("/")
        asset_dirs = _texts(host.get("asset_dirs", [skills_dir.split("/")[0]]), f"{key}.asset_dirs")
        hosts.append(
            HostConfig(
                name=name,
                skills_dir=skills_dir,
                instructions=_texts(host["instructions"], f"{key}.instructions"),
                host_metadata=_texts(host.get("host_metadata", []), f"{key}.host_metadata"),
                asset_dirs=tuple(sorted({d.strip("/") for d in asset_dirs})),
            )
        )
    return tuple(hosts)


MAX_PLACEHOLDER_PATTERN = 200
# A quantified group that itself contains a quantifier, e.g. "(a+)+" or "(?:x*)*".
_NESTED_QUANTIFIER = re.compile(r"\((?:[^()\\]|\\.)*[*+}](?:[^()\\]|\\.)*\)\s*[*+{?]")


def _parse_placeholders(raw: object) -> tuple[InstallPlaceholder, ...]:
    placeholders: list[InstallPlaceholder] = []
    for index, entry in enumerate(_entries(raw, "install_placeholders")):
        key = f"install_placeholders[{index}]"
        _check_keys(entry, key, required=frozenset({"pattern", "replacement"}))
        pattern = _text(entry["pattern"], f"{key}.pattern")
        # The config is versioned, but --config may point anywhere: bound the pattern and refuse
        # nested quantifiers, the shape behind catastrophic backtracking (ReDoS).
        if len(pattern) > MAX_PLACEHOLDER_PATTERN:
            raise _fail(f"{key}.pattern", f"longer than {MAX_PLACEHOLDER_PATTERN} characters")
        if _NESTED_QUANTIFIER.search(pattern):
            raise _fail(f"{key}.pattern", "nested quantifiers are not allowed")
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
        items.append(
            HostOnly(
                path=_text(entry["path"], f"{key}.path"),
                host=_host_name(entry["host"], f"{key}.host", hosts),
                reason=_text(entry["reason"], f"{key}.reason", reason=True),
            )
        )
    return tuple(items)


def _parse_accepted(raw: object, hosts: frozenset[str]) -> tuple[Accepted, ...]:
    items: list[Accepted] = []
    for index, entry in enumerate(_entries(raw, "accepted")):
        key = f"accepted[{index}]"
        _check_keys(
            entry, key, required=frozenset({"skill", "element", "hosts", "value", "reason"})
        )
        names = _texts(entry["hosts"], f"{key}.hosts")
        if not names:
            raise _fail(f"{key}.hosts", "must name at least one host")
        items.append(
            Accepted(
                skill=_text(entry["skill"], f"{key}.skill"),
                element=_text(entry["element"], f"{key}.element"),
                hosts=tuple(sorted(_host_name(n, f"{key}.hosts", hosts) for n in names)),
                value=_text(entry["value"], f"{key}.value"),
                reason=_text(entry["reason"], f"{key}.reason", reason=True),
            )
        )
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
    return {
        path: _texts(value, f"pointers.{path}")
        for path, value in sorted(_table(raw, "pointers").items())
    }


def _parse_moved_rules(raw: object) -> tuple[MovedRule, ...]:
    rules: list[MovedRule] = []
    for index, entry in enumerate(_entries(raw, "moved_rules")):
        key = f"moved_rules[{index}]"
        _check_keys(entry, key, required=frozenset({"anchor", "from", "to"}))
        rules.append(
            MovedRule(
                anchor=_text(entry["anchor"], f"{key}.anchor"),
                source=_text(entry["from"], f"{key}.from"),
                target=_text(entry["to"], f"{key}.to"),
            )
        )
    return tuple(rules)


def _parse_skill_prefixes(raw: dict[str, Any]) -> tuple[str, ...]:
    """``[skills] prefixes``: directory prefixes audited as equivalent skills.
    Defaults to the historical kiro-* set so an undeclared section keeps working."""
    if "skills" not in raw:
        return ("kiro-",)
    skills = _table(raw["skills"], "skills")
    _check_keys(skills, "skills", required=frozenset({"prefixes"}))
    prefixes = _texts(skills["prefixes"], "skills.prefixes")
    for prefix in prefixes:
        if not prefix.endswith("-"):
            raise _fail("skills.prefixes", f"prefix {prefix!r} must end with '-'")
    return tuple(prefixes)


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
        skill_prefixes=_parse_skill_prefixes(raw),
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
    env.update(
        {
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_TERMINAL_PROMPT": "0",
            "LC_ALL": "C",
            # Never discover a repository above ``repo``: the inventory is the checkout's own.
            "GIT_CEILING_DIRECTORIES": str(repo.resolve().parent),
        }
    )
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
            argv,
            cwd=repo,
            env=_git_env(repo),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=GIT_TIMEOUT_S,
            check=False,
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


# --- findings and report -------------------------------------------------------------------


class FindingKind(StrEnum):
    HOST_SYNTAX = "host-syntax"  # text differs, semantic profile equal (tolerated)
    ACCEPTED = "accepted"  # divergence registered with a reason
    DRIFT = "drift"  # an element of the semantic profile diverges
    MISSING_SKILL = "missing-skill"  # an equivalent skill is missing in a host
    SUPPORT_DRIFT = "support-drift"  # support file diverges (between hosts or reference)
    HOST_ONLY = "host-only"  # declared host-only asset (informative)
    HOST_ONLY_UNDECLARED = "host-only-undeclared"
    STALE_ACCEPTED = "stale-accepted"  # accepted entry without a matching divergence
    INVARIANTS = "invariants"  # invariants block missing, divergent or w/o anchor
    BUDGET = "budget"  # instruction file above its size budget
    MOVED_RULE = "moved-rule"  # moved rule absent from its declared target
    POINTER = "pointer"  # mandatory pointer absent from an instruction file


FAILING: frozenset[FindingKind] = frozenset(FindingKind) - {
    FindingKind.HOST_SYNTAX,
    FindingKind.ACCEPTED,
    FindingKind.HOST_ONLY,
}


@dataclass(frozen=True, order=True)
class Finding:
    kind: FindingKind
    subject: str  # skill (kiro-x) or repository path
    hosts: tuple[str, ...]  # sorted
    element: str  # "name" | "paths" | "skills" | "phases" | "support" | ...
    detail: str

    @property
    def failing(self) -> bool:
        return self.kind in FAILING

    def format(self) -> str:
        hosts = ",".join(self.hosts) or "-"
        return f"{self.kind} {self.subject} [{hosts}] {self.element}: {self.detail}"


@dataclass(frozen=True)
class AuditReport:
    findings: tuple[Finding, ...]  # totally ordered
    skills: tuple[tuple[str, tuple[str, ...]], ...]  # (skill, hosts where it exists), sorted
    hosts: tuple[str, ...]  # every declared host, sorted

    def failing(self) -> tuple[Finding, ...]:
        return tuple(f for f in self.findings if f.failing)

    def of_kind(self, *kinds: FindingKind) -> tuple[Finding, ...]:
        return tuple(f for f in self.findings if f.kind in kinds)

    def to_text(self) -> str:
        lines = ["Agentic asset audit", "", f"Skills per host ({len(self.skills)}):"]
        width = max([len("skill"), *(len(name) for name, _ in self.skills)])
        lines.append("  " + "  ".join(["skill".ljust(width), *self.hosts]))
        for name, present in self.skills:
            marks = [("x" if h in present else "-").center(len(h)) for h in self.hosts]
            lines.append(("  " + "  ".join([name.ljust(width), *marks])).rstrip())
        for kind in FindingKind:
            group = self.of_kind(kind)
            if not group:
                continue
            label = "FAIL" if kind in FAILING else "info"
            lines += ["", f"{kind} ({len(group)}, {label}):"]
            lines += [
                f"  {f.subject} [{','.join(f.hosts) or '-'}] {f.element}: {f.detail}" for f in group
            ]
        failing = len(self.failing())
        lines += ["", f"{failing} failing finding(s)" if failing else "no failing findings"]
        return "\n".join(lines) + "\n"

    def to_json(self) -> str:
        payload = {
            "hosts": list(self.hosts),
            "skills": [{"name": name, "hosts": list(present)} for name, present in self.skills],
            "findings": [
                {
                    "kind": str(f.kind),
                    "subject": f.subject,
                    "hosts": list(f.hosts),
                    "element": f.element,
                    "detail": f.detail,
                    "failing": f.failing,
                }
                for f in self.findings
            ],
            "failing": len(self.failing()),
        }
        return json.dumps(payload, sort_keys=True, indent=2) + "\n"


# --- semantic profile ----------------------------------------------------------------------


@dataclass(frozen=True)
class SkillProfile:
    name: str
    paths: frozenset[str]  # .kiro/..., rules/..., templates/... normalized
    skill_refs: frozenset[str]  # other kiro-* skills referenced, without invocation prefix
    phases: frozenset[str]  # spec.json phase values cited
    support_files: frozenset[str]  # paths relative to the skill dir, without host metadata


_FRONTMATTER = re.compile(r"\A---\n(.*?)\n---(?:\n|\Z)", re.DOTALL)
_NAME = re.compile(r"^name:\s*(\S+)", re.MULTILINE)
_PATH = re.compile(
    r"\.kiro/[A-Za-z0-9_./{}$-]+"
    r"|(?<![A-Za-z0-9_./-])(?:rules|templates)/[a-z0-9-]+\.md"
)
# Feature argument forms per host: $ARGUMENTS / $1 (Claude, Codex), {feature-name} / {feature}.
_FEATURE_ARG = re.compile(r"\$ARGUMENTS|\$1(?![0-9])|\{feature(?:[-_]name)?\}")
# Invocation prefixes per host: /skill-x (Claude, Devin), $skill-x (Codex), /skill:x
# (legacy). Both skill families are followed: kiro-* and the forge-* ecosystem set.
_SKILL_REF = re.compile(r"(?<![A-Za-z0-9_.])[/$]?(kiro|forge)[-:]([a-z][a-z-]*)")
_PHASE = re.compile(r"\bphase\"?\s*:\s*\"([a-z][a-z-]*)\"")


def _normalize_path(raw: str) -> str:
    return _FEATURE_ARG.sub("{feature}", raw).rstrip("./")


def profile_skill(skill_md: str, support_files: frozenset[str]) -> SkillProfile:
    """Semantic profile of a SKILL.md: only what changes what the agent reads, writes or invokes.

    Host syntax (frontmatter besides ``name``, envelopes, headings, invocation prefixes, feature
    argument forms, delegation wording) never enters the profile; a skill naming itself is not a
    reference to another skill.
    """
    text = normalize_text(skill_md)
    frontmatter = _FRONTMATTER.match(text)
    name_match = _NAME.search(frontmatter.group(1)) if frontmatter else None
    name = name_match.group(1) if name_match else ""
    body = text[frontmatter.end() :] if frontmatter else text
    paths = frozenset(p for p in (_normalize_path(m.group(0)) for m in _PATH.finditer(body)) if p)
    refs = frozenset(
        f"{m.group(1)}-{m.group(2).rstrip('-')}" for m in _SKILL_REF.finditer(body)
    )
    return SkillProfile(
        name=name,
        paths=paths,
        skill_refs=refs - {name},
        phases=frozenset(m.group(1) for m in _PHASE.finditer(body)),
        support_files=support_files,
    )


def _profile_elements(profile: SkillProfile) -> dict[str, frozenset[str]]:
    return {
        "name": frozenset({profile.name}),
        "paths": profile.paths,
        "skills": profile.skill_refs,
        "phases": profile.phases,
        "support": profile.support_files,
    }


_PROFILE_ELEMENTS = ("name", "paths", "skills", "phases", "support")


# --- audit ---------------------------------------------------------------------------------


@dataclass(frozen=True)
class _Divergence:
    skill: str
    element: str
    hosts: tuple[str, ...]  # hosts holding ``value``
    value: str
    absent: tuple[str, ...]  # hosts of the skill without ``value``


_SkillFiles = dict[str, dict[str, frozenset[str]]]  # skill -> host -> paths in the skill dir


def _ws(text: str) -> str:
    return " ".join(text.split())


def _under(path: str, prefix: str) -> bool:
    prefix = prefix.strip("/")
    return path == prefix or path.startswith(prefix + "/")


class _Auditor:
    def __init__(self, repo: Path, config: AgenticConfig, files: frozenset[str]) -> None:
        self.repo = repo
        self.config = config
        self.files = files
        self.hosts = {host.name: host for host in config.hosts}
        self.findings: set[Finding] = set()
        self._cache: dict[str, str] = {}

    def read(self, path: str) -> str:
        if path not in self._cache:
            self._cache[path] = read_text(self.repo, path)
        return self._cache[path]

    def placeholders(self, text: str) -> str:
        for placeholder in self.config.install_placeholders:
            text = placeholder.pattern.sub(placeholder.replacement, text)
        return text

    def add(
        self, kind: FindingKind, subject: str, hosts: Iterable[str], element: str, detail: str
    ) -> None:
        self.findings.add(Finding(kind, subject, tuple(sorted(set(hosts))), element, detail))

    # skills and host directories ------------------------------------------------------------

    def host_only_entry(self, path: str) -> HostOnly | None:
        return next((e for e in self.config.host_only if _under(path, e.path)), None)

    def skill_files(self) -> _SkillFiles:
        """Equivalent skills: ``kiro-*`` directories of each skills_dir, minus host-only paths."""
        found: dict[str, dict[str, set[str]]] = {}
        for host in self.config.hosts:
            prefix = host.skills_dir + "/"
            for path in self.files:
                if not path.startswith(prefix) or self.host_only_entry(path) is not None:
                    continue
                skill, sep, rel = path[len(prefix) :].partition("/")
                if sep and rel and skill.startswith(self.config.skill_prefixes):
                    found.setdefault(skill, {}).setdefault(host.name, set()).add(rel)
        return {
            skill: {h: frozenset(rels) for h, rels in by_host.items()}
            for skill, by_host in found.items()
        }

    def check_host_dirs(self, skills: _SkillFiles) -> None:
        owned = {
            f"{self.hosts[h].skills_dir}/{skill}/{rel}"
            for skill, by_host in skills.items()
            for h, rels in by_host.items()
            for rel in rels
        }
        for entry in self.config.host_only:
            if any(_under(path, entry.path) for path in self.files):
                self.add(FindingKind.HOST_ONLY, entry.path, [entry.host], "host-only", entry.reason)
        for path in sorted(self.files - owned):
            # The skills_dir is always a host directory, even if asset_dirs omits it.
            hosts = [
                h.name
                for h in self.config.hosts
                if any(_under(path, d) for d in (*h.asset_dirs, h.skills_dir))
            ]
            if hosts and self.host_only_entry(path) is None:
                self.add(
                    FindingKind.HOST_ONLY_UNDECLARED,
                    path,
                    hosts,
                    "host-only",
                    "not part of an equivalent skill and not declared in [[host_only]]",
                )

    # equivalent skills ----------------------------------------------------------------------

    def support_rels(self, host: str, rels: frozenset[str]) -> frozenset[str]:
        return frozenset(rels - set(self.hosts[host].host_metadata) - {"SKILL.md"})

    def compare_skills(self, skills: _SkillFiles) -> list[_Divergence]:
        divergences: list[_Divergence] = []
        for skill in sorted(skills):
            by_host = skills[skill]
            missing = [h for h in self.hosts if h not in by_host]
            if missing:
                self.add(
                    FindingKind.MISSING_SKILL,
                    skill,
                    missing,
                    "skill",
                    f"missing in {', '.join(missing)}; present in {', '.join(sorted(by_host))}",
                )
            texts: dict[str, str] = {}
            elements: dict[str, dict[str, frozenset[str]]] = {}
            for host in sorted(by_host):
                rels = by_host[host]
                for rel in sorted(rels & set(self.hosts[host].host_metadata)):
                    self.add(FindingKind.HOST_SYNTAX, skill, [host], "host-metadata", rel)
                skill_md = f"{self.hosts[host].skills_dir}/{skill}/SKILL.md"
                texts[host] = self.read(skill_md) if "SKILL.md" in rels else ""
                profile = profile_skill(texts[host], self.support_rels(host, rels))
                elements[host] = _profile_elements(profile)
            found = self.divergences(skill, elements)
            divergences += found
            if not found and len(set(texts.values())) > 1:
                self.add(
                    FindingKind.HOST_SYNTAX,
                    skill,
                    by_host,
                    "SKILL.md",
                    "text differs between hosts; semantic profile is equal",
                )
        return divergences

    @staticmethod
    def divergences(
        skill: str, elements: dict[str, dict[str, frozenset[str]]]
    ) -> list[_Divergence]:
        found: list[_Divergence] = []
        hosts = sorted(elements)
        for element in _PROFILE_ELEMENTS:
            values = {h: elements[h][element] for h in hosts}
            for value in sorted(frozenset[str]().union(*values.values())):
                holders = tuple(h for h in hosts if value in values[h])
                if len(holders) < len(hosts):
                    absent = tuple(h for h in hosts if h not in holders)
                    found.append(_Divergence(skill, element, holders, value, absent))
        return found

    def classify(self, divergences: list[_Divergence]) -> None:
        accepted = {(a.skill, a.element, a.hosts, a.value): a for a in self.config.accepted}
        matched: set[tuple[str, str, tuple[str, ...], str]] = set()
        for d in divergences:
            key = (d.skill, d.element, d.hosts, d.value)
            entry = accepted.get(key)
            if entry is not None:
                matched.add(key)
                self.add(
                    FindingKind.ACCEPTED,
                    d.skill,
                    d.hosts,
                    d.element,
                    f"{d.value!r}: {entry.reason}",
                )
            else:
                self.add(
                    FindingKind.DRIFT,
                    d.skill,
                    d.hosts,
                    d.element,
                    f"{d.value!r} only in {', '.join(d.hosts)}; absent in {', '.join(d.absent)}",
                )
        for key, entry in accepted.items():
            if key not in matched:
                self.add(
                    FindingKind.STALE_ACCEPTED,
                    entry.skill,
                    entry.hosts,
                    entry.element,
                    f"{entry.value!r} matches no current divergence; remove this "
                    "[[accepted]] entry",
                )

    # support files --------------------------------------------------------------------------

    def compare_support(self, skills: _SkillFiles) -> None:
        for skill in sorted(skills):
            by_host = skills[skill]
            rels = frozenset[str]().union(*(self.support_rels(h, r) for h, r in by_host.items()))
            for rel in sorted(rels):
                contents = {
                    h: self.placeholders(self.read(f"{self.hosts[h].skills_dir}/{skill}/{rel}"))
                    for h in sorted(by_host)
                    if rel in by_host[h]
                }
                self.compare_support_file(f"{skill}/{rel}", rel, contents)

    def compare_support_file(self, subject: str, rel: str, contents: dict[str, str]) -> None:
        if len(set(contents.values())) > 1:
            groups: dict[str, list[str]] = {}
            for host, content in contents.items():
                groups.setdefault(content, []).append(host)
            detail = " | ".join(sorted("+".join(g) for g in groups.values()))
            self.add(
                FindingKind.SUPPORT_DRIFT,
                subject,
                contents,
                "hosts",
                f"content differs between hosts: {detail}",
            )
        head, _, filename = rel.partition("/")
        reference_dir = self.config.reference_rules_dir
        if reference_dir is None or head != "rules" or "/" in filename:
            return
        reference = f"{reference_dir.strip('/')}/{filename}"
        if reference not in self.files:
            return  # no reference copy: compared between hosts only
        expected = self.placeholders(self.read(reference))
        differing = [h for h, content in contents.items() if content != expected]
        if differing:
            self.add(
                FindingKind.SUPPORT_DRIFT,
                subject,
                differing,
                "reference",
                f"differs from {reference} beyond install placeholders",
            )

    # instruction files ----------------------------------------------------------------------

    def readers(self, path: str) -> list[str]:
        return [h.name for h in self.config.hosts if path in h.instructions]

    def check_instructions(self) -> None:
        if self.config.invariants is not None:
            self.check_invariants(self.config.invariants)
        for path, budget in sorted((self.config.budgets or {}).items()):
            if path not in self.files:
                self.add(FindingKind.BUDGET, path, self.readers(path), "size", "file not found")
                continue
            size = len(self.read(path).encode("utf-8"))
            if size > budget:
                self.add(
                    FindingKind.BUDGET,
                    path,
                    self.readers(path),
                    "size",
                    f"{size} bytes > budget {budget} bytes",
                )
        for path, anchors in sorted((self.config.pointers or {}).items()):
            if path not in self.files:
                self.add(FindingKind.POINTER, path, self.readers(path), "pointer", "file not found")
                continue
            text = _ws(self.read(path))
            for anchor in anchors:
                if _ws(anchor) not in text:
                    self.add(
                        FindingKind.POINTER,
                        path,
                        self.readers(path),
                        "pointer",
                        f"missing pointer {anchor!r}",
                    )
        for rule in self.config.moved_rules or ():
            moved = f"{rule.anchor!r} (moved from {rule.source})"
            if rule.target not in self.files:
                self.add(
                    FindingKind.MOVED_RULE,
                    rule.target,
                    self.readers(rule.source),
                    "moved-rule",
                    f"{moved}: target not found",
                )
            elif _ws(rule.anchor) not in _ws(self.read(rule.target)):
                self.add(
                    FindingKind.MOVED_RULE,
                    rule.target,
                    self.readers(rule.source),
                    "moved-rule",
                    f"{moved} is absent from {rule.target}",
                )

    def check_invariants(self, invariants: Invariants) -> None:
        blocks: dict[str, str] = {}
        for path in sorted({p for h in self.config.hosts for p in h.instructions}):
            if path not in self.files:
                self.add(
                    FindingKind.INVARIANTS, path, self.readers(path), "block", "file not found"
                )
                continue
            text = self.read(path)
            start = text.find(invariants.begin)
            end = text.find(invariants.end, start + len(invariants.begin)) if start >= 0 else -1
            if end < 0:
                self.add(
                    FindingKind.INVARIANTS,
                    path,
                    self.readers(path),
                    "block",
                    f"missing block delimited by {invariants.begin!r} and {invariants.end!r}",
                )
                continue
            block = text[start + len(invariants.begin) : end].strip("\n")
            blocks[path] = block
            for anchor in invariants.required:
                if _ws(anchor) not in _ws(block):
                    self.add(
                        FindingKind.INVARIANTS,
                        path,
                        self.readers(path),
                        "anchor",
                        f"missing invariant {anchor!r}",
                    )
        for path, block in blocks.items():
            other = next((o for o in sorted(blocks) if blocks[o] != block), None)
            if other is None:
                continue
            mine, theirs = block.split("\n"), blocks[other].split("\n")
            index = next(
                (i for i, (a, b) in enumerate(zip(mine, theirs, strict=False)) if a != b),
                min(len(mine), len(theirs)),
            )
            line = mine[index] if index < len(mine) else "<end of block>"
            self.add(
                FindingKind.INVARIANTS,
                path,
                self.readers(path),
                "divergent",
                f"block differs from {other} at line {index + 1}: {line!r}",
            )

    def run(self) -> AuditReport:
        skills = self.skill_files()
        self.check_host_dirs(skills)
        self.classify(self.compare_skills(skills))
        self.compare_support(skills)
        self.check_instructions()
        return AuditReport(
            findings=tuple(sorted(self.findings)),
            skills=tuple((skill, tuple(sorted(skills[skill]))) for skill in sorted(skills)),
            hosts=tuple(self.hosts),
        )


def audit(repo: Path, config: AgenticConfig, files: frozenset[str] | None = None) -> AuditReport:
    """Audit the agentic assets of ``repo``; pure in (repository content, config, files).

    ``files=None`` takes the inventory from git (``tracked_files``); tests pass it explicitly.
    Tracked files missing from the working tree (deleted, not yet staged) count as absent.
    """
    inventory = tracked_files(repo) if files is None else files
    present = frozenset(path for path in inventory if (repo / path).is_file())
    return _Auditor(repo, config, present).run()


# --- command line --------------------------------------------------------------------------


def _write(stream: Any, text: str) -> None:
    """UTF-8 and LF on every platform, whatever the console encoding (deterministic output)."""
    stream.flush()
    stream.buffer.write(text.encode("utf-8"))
    stream.buffer.flush()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="audit_assets",
        description="Audit drift between the agentic assets (Kiro skills, host instructions) "
        "of each host.",
    )
    parser.add_argument(
        "--root", type=Path, default=DEFAULT_ROOT, help="repository root (default: this repository)"
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help="audit configuration (default: the versioned agentic.toml)",
    )
    parser.add_argument("--json", action="store_true", help="emit the report as JSON")
    args = parser.parse_args(argv)
    try:
        report = audit(args.root, load_config(args.config))
    except (AgenticConfigError, AgenticGitError) as exc:
        _write(sys.stderr, f"audit_assets: error: {exc}\n")
        return 2
    except (OSError, UnicodeDecodeError) as exc:
        _write(sys.stderr, f"audit_assets: error: cannot read a tracked file: {exc}\n")
        return 2
    _write(sys.stdout, report.to_json() if args.json else report.to_text())
    return 1 if report.failing() else 0


if __name__ == "__main__":
    raise SystemExit(main())
