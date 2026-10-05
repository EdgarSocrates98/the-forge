"""Agentic asset audit: configuration, inventory, semantic parity, instructions and report.

Requirements 1.1-1.6 (audit and deterministic report), 2.2-2.5 (host syntax tolerated, missing
skills, support files, stale accepted entries), 2.6 (same offline run, no new dependency),
3.2-3.3 and 4.4-4.7 (invariants block, budgets, pointers, moved rules), 10.2 (deterministic,
same result on Linux and Windows) and 10.3 (local untracked assets do not change the result).
Behaviour is exercised on temporary trees; the real repository is a gate (one test per failing
category, task 4.7).

The audit logic lives only in ``scripts/agentic/audit_assets.py``; these tests load that file
by path (the ``scripts/ci`` pattern) instead of re-implementing it.
"""

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[1]
AUDIT_SCRIPT = REPO / "scripts" / "agentic" / "audit_assets.py"
CONFIG_FILE = REPO / "scripts" / "agentic" / "agentic.toml"

GIT = shutil.which("git")
requires_git = pytest.mark.skipif(GIT is None, reason="git executable not found on PATH")


def _load_audit() -> ModuleType:
    spec = importlib.util.spec_from_file_location("audit_assets", AUDIT_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses resolve their module through sys.modules
    spec.loader.exec_module(module)
    return module


audit = _load_audit()


# --- helpers -------------------------------------------------------------------------------

MINIMAL_CONFIG = """\
[hosts.claude]
skills_dir = ".claude/skills"
instructions = ["CLAUDE.md"]

[hosts.codex]
skills_dir = ".agents/skills"
instructions = ["AGENTS.md"]
host_metadata = ["agents/openai.yaml"]
"""

FULL_CONFIG = MINIMAL_CONFIG + """\

[hosts.devin]
skills_dir = ".devin/skills"
instructions = ["AGENTS.md"]

[reference]
rules_dir = ".kiro/settings/rules"

[[install_placeholders]]
pattern = '`spec\\.json\\.language` / `[a-z]{2}`'
replacement = '`spec.json.language` / <lang>'

[[host_only]]
path = ".codex/agents/spec-reviewer.toml"
host = "codex"
reason = "cross-spec reviewer used by kiro-spec-batch on Codex"

[[accepted]]
skill = "kiro-spec-quick"
element = "paths"
hosts = ["codex", "devin"]
value = ".kiro/specs/{feature}/design.md"
reason = "output wording"

[invariants]
begin = "<!-- theforge:invariants:begin -->"
end = "<!-- theforge:invariants:end -->"
required = ["stdlib", "Forge Protocol"]

[budgets]
"CLAUDE.md" = 2500
"AGENTS.md" = 6000

[pointers]
"CLAUDE.md" = ["docs/agentic.md"]
"AGENTS.md" = ["docs/agentic.md", ".agents/skills/"]

[[moved_rules]]
anchor = "3-phase approval workflow"
from = "CLAUDE.md"
to = "docs/agentic.md"
"""


def _write_config(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "agentic.toml"
    path.write_text(text, encoding="utf-8")
    return path


def _git(repo: Path, *args: str) -> str:
    assert GIT is not None
    out = subprocess.run(
        [GIT, "-c", "core.fsmonitor=false", *args],
        cwd=repo, capture_output=True, check=True, env={**os.environ, "LC_ALL": "C"},
    )
    return out.stdout.decode("utf-8", "replace")


def _snapshot(root: Path) -> dict[str, tuple[int, bytes]]:
    return {
        p.relative_to(root).as_posix(): (p.stat().st_mtime_ns, p.read_bytes())
        for p in sorted(root.rglob("*")) if p.is_file()
    }


# --- loading the tool ----------------------------------------------------------------------

def test_tool_lives_outside_the_package_and_is_stdlib_only() -> None:
    assert AUDIT_SCRIPT.is_file()
    assert CONFIG_FILE.is_file()
    source = AUDIT_SCRIPT.read_text(encoding="utf-8")
    assert "import theforge" not in source and "from theforge" not in source
    assert not (REPO / "src" / "theforge" / "agentic").exists()


def test_versioned_config_loads() -> None:
    config = audit.load_config(CONFIG_FILE)
    names = [host.name for host in config.hosts]
    assert names == sorted(names)
    assert {"claude", "codex", "devin"} <= set(names)
    assert all(host.skills_dir and host.instructions for host in config.hosts)


# --- configuration validation --------------------------------------------------------------

def test_full_config_is_parsed(tmp_path: Path) -> None:
    config = audit.load_config(_write_config(tmp_path, FULL_CONFIG))
    assert [h.name for h in config.hosts] == ["claude", "codex", "devin"]
    codex = config.hosts[1]
    assert codex.skills_dir == ".agents/skills"
    assert codex.instructions == ("AGENTS.md",)
    assert codex.host_metadata == ("agents/openai.yaml",)
    assert config.hosts[0].host_metadata == ()
    assert config.reference_rules_dir == ".kiro/settings/rules"
    (placeholder,) = config.install_placeholders
    assert placeholder.pattern.sub(placeholder.replacement, "`spec.json.language` / `pt`") == (
        "`spec.json.language` / <lang>"
    )
    (host_only,) = config.host_only
    assert (host_only.path, host_only.host) == (".codex/agents/spec-reviewer.toml", "codex")
    (accepted,) = config.accepted
    assert accepted.hosts == ("codex", "devin")
    assert accepted.element == "paths"
    assert config.invariants is not None
    assert config.invariants.required == ("stdlib", "Forge Protocol")
    assert config.budgets == {"CLAUDE.md": 2500, "AGENTS.md": 6000}
    assert config.pointers == {"CLAUDE.md": ("docs/agentic.md",),
                               "AGENTS.md": ("docs/agentic.md", ".agents/skills/")}
    (moved,) = config.moved_rules or ()
    assert (moved.anchor, moved.source, moved.target) == (
        "3-phase approval workflow", "CLAUDE.md", "docs/agentic.md")


def test_optional_sections_default_to_absent(tmp_path: Path) -> None:
    config = audit.load_config(_write_config(tmp_path, MINIMAL_CONFIG))
    assert config.reference_rules_dir is None
    assert config.install_placeholders == ()
    assert config.host_only == ()
    assert config.accepted == ()
    assert config.invariants is None
    assert config.budgets is None
    assert config.pointers is None
    assert config.moved_rules is None


@pytest.mark.parametrize(("text", "key"), [
    ("unknown = 1\n" + MINIMAL_CONFIG, "unknown"),
    (MINIMAL_CONFIG.replace('instructions = ["CLAUDE.md"]',
                            'instructions = ["CLAUDE.md"]\nextra = "x"'), "hosts.claude.extra"),
    (MINIMAL_CONFIG.replace('skills_dir = ".claude/skills"', "skills_dir = 3"),
     "hosts.claude.skills_dir"),
    (MINIMAL_CONFIG.replace('skills_dir = ".claude/skills"\n', ""), "hosts.claude.skills_dir"),
    (MINIMAL_CONFIG.replace('instructions = ["AGENTS.md"]', 'instructions = "AGENTS.md"'),
     "hosts.codex.instructions"),
    (MINIMAL_CONFIG.replace('instructions = ["AGENTS.md"]', "instructions = [1]"),
     "hosts.codex.instructions"),
    ("", "hosts"),
    (MINIMAL_CONFIG + '\n[[host_only]]\npath = "x"\nhost = "codex"\nreason = ""\n',
     "host_only[0].reason"),
    (MINIMAL_CONFIG + '\n[[host_only]]\npath = "x"\nhost = "codex"\nreason = "   "\n',
     "host_only[0].reason"),
    (MINIMAL_CONFIG + '\n[[host_only]]\npath = "x"\nhost = "nobody"\nreason = "r"\n',
     "host_only[0].host"),
    (MINIMAL_CONFIG + '\n[[accepted]]\nskill = "kiro-a"\nelement = "paths"\n'
     'hosts = ["codex"]\nvalue = "v"\nreason = ""\n', "accepted[0].reason"),
    (MINIMAL_CONFIG + '\n[[accepted]]\nskill = "kiro-a"\nelement = "paths"\n'
     'hosts = ["codex"]\nvalue = "v"\n', "accepted[0].reason"),
    (MINIMAL_CONFIG + '\n[[accepted]]\nskill = "kiro-a"\nelement = "paths"\n'
     'hosts = "codex"\nvalue = "v"\nreason = "r"\n', "accepted[0].hosts"),
    (MINIMAL_CONFIG + '\n[[install_placeholders]]\npattern = "("\nreplacement = "x"\n',
     "install_placeholders[0].pattern"),
    (MINIMAL_CONFIG + '\n[budgets]\n"CLAUDE.md" = "big"\n', "budgets.CLAUDE.md"),
    (MINIMAL_CONFIG + '\n[budgets]\n"CLAUDE.md" = true\n', "budgets.CLAUDE.md"),
    (MINIMAL_CONFIG + '\n[budgets]\n"CLAUDE.md" = 0\n', "budgets.CLAUDE.md"),
    (MINIMAL_CONFIG + '\n[pointers]\n"CLAUDE.md" = "docs/agentic.md"\n', "pointers.CLAUDE.md"),
    (MINIMAL_CONFIG + '\n[invariants]\nbegin = "a"\nend = "b"\n', "invariants.required"),
    (MINIMAL_CONFIG + '\n[invariants]\nbegin = "a"\nend = "b"\nrequired = []\nx = 1\n',
     "invariants.x"),
    (MINIMAL_CONFIG + '\n[[moved_rules]]\nanchor = "a"\nfrom = "CLAUDE.md"\n', "moved_rules[0].to"),
    (MINIMAL_CONFIG + '\n[reference]\nrules_dir = 1\n', "reference.rules_dir"),
    ("host_only = 3\n" + MINIMAL_CONFIG, "host_only"),
])
def test_invalid_config_names_the_key(tmp_path: Path, text: str, key: str) -> None:
    with pytest.raises(audit.AgenticConfigError) as info:
        audit.load_config(_write_config(tmp_path, text))
    assert f"'{key}'" in str(info.value)


def test_unparseable_or_missing_config_is_a_config_error(tmp_path: Path) -> None:
    with pytest.raises(audit.AgenticConfigError, match="agentic.toml"):
        audit.load_config(_write_config(tmp_path, "[hosts\n"))
    with pytest.raises(audit.AgenticConfigError, match="missing.toml"):
        audit.load_config(tmp_path / "missing.toml")


# --- text normalization --------------------------------------------------------------------

def test_crlf_and_lf_normalize_to_the_same_text(tmp_path: Path) -> None:
    lf = "---\nname: kiro-x\n---\n# Title\n\nbody\n"
    crlf = lf.replace("\n", "\r\n")
    assert audit.normalize_text(crlf) == audit.normalize_text(lf) == lf
    (tmp_path / "lf.md").write_bytes(lf.encode("utf-8"))
    (tmp_path / "crlf.md").write_bytes(crlf.encode("utf-8"))
    assert audit.read_text(tmp_path, "crlf.md") == audit.read_text(tmp_path, "lf.md") == lf


# --- tracked inventory ---------------------------------------------------------------------

@requires_git
def test_inventory_lists_only_tracked_files_without_writing(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / ".claude" / "skills" / "kiro-a").mkdir(parents=True)
    _git(repo, "init", "-q", ".")
    (repo / ".claude" / "skills" / "kiro-a" / "SKILL.md").write_text("a\n", encoding="utf-8")
    (repo / "CLAUDE.md").write_text("c\n", encoding="utf-8")
    _git(repo, "add", ".")
    local = repo / ".agents" / "skills" / "source-command-x"
    local.mkdir(parents=True)
    (local / "SKILL.md").write_text("local\n", encoding="utf-8")
    (repo / "notes.md").write_text("untracked\n", encoding="utf-8")
    before = _snapshot(repo)

    files = audit.tracked_files(repo)

    assert files == frozenset({".claude/skills/kiro-a/SKILL.md", "CLAUDE.md"})
    assert _snapshot(repo) == before


@requires_git
def test_inventory_ignores_inherited_git_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", ".")
    (repo / "a.md").write_text("a\n", encoding="utf-8")
    _git(repo, "add", "a.md")
    other = tmp_path / "other"
    other.mkdir()
    _git(other, "init", "-q", ".")
    monkeypatch.setenv("GIT_DIR", str(other / ".git"))
    monkeypatch.setenv("GIT_INDEX_FILE", str(other / ".git" / "index"))
    assert audit.tracked_files(repo) == frozenset({"a.md"})


@requires_git
def test_inventory_outside_a_repository_is_a_git_error(tmp_path: Path) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    with pytest.raises(audit.AgenticGitError):
        audit.tracked_files(plain)


def test_inventory_without_git_is_a_git_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def no_git(name: str, *args: Any, **kwargs: Any) -> None:
        return None

    monkeypatch.setattr(audit.shutil, "which", no_git)
    with pytest.raises(audit.AgenticGitError, match="git"):
        audit.tracked_files(tmp_path)


@requires_git
def test_inventory_of_the_real_repository_excludes_local_assets() -> None:
    files = audit.tracked_files(REPO)
    assert "CLAUDE.md" in files
    assert not any(path.startswith((".kiro/specs/", ".kiro/steering/")) for path in files)
    assert not any("/source-command-" in path for path in files)


def test_host_asset_dirs_default_to_the_top_of_the_skills_dir(tmp_path: Path) -> None:
    config = audit.load_config(_write_config(tmp_path, TREE_CONFIG))
    by_name = {host.name: host for host in config.hosts}
    assert by_name["claude"].asset_dirs == (".claude",)
    assert by_name["codex"].asset_dirs == (".agents", ".codex")
    bad = TREE_CONFIG.replace('asset_dirs = [".agents", ".codex"]', 'asset_dirs = ".codex"')
    with pytest.raises(audit.AgenticConfigError, match="'hosts.codex.asset_dirs'"):
        audit.load_config(_write_config(tmp_path, bad))


# --- audit fixtures ------------------------------------------------------------------------

TREE_CONFIG = """\
[hosts.claude]
skills_dir = ".claude/skills"
instructions = ["CLAUDE.md"]

[hosts.codex]
skills_dir = ".agents/skills"
instructions = ["AGENTS.md"]
host_metadata = ["agents/openai.yaml"]
asset_dirs = [".agents", ".codex"]

[hosts.devin]
skills_dir = ".devin/skills"
instructions = ["AGENTS.md"]

[reference]
rules_dir = ".kiro/settings/rules"

[[install_placeholders]]
pattern = '`spec\\.json\\.language` / `[a-z]{2}`'
replacement = '`spec.json.language` / <lang>'
"""

HOSTS = ("claude", "codex", "devin")
SKILLS_DIR = {"claude": ".claude/skills", "codex": ".agents/skills", "devin": ".devin/skills"}
# Host syntax: feature argument form and invocation prefix (Devin keeps the legacy /kiro:).
ARG = {"claude": "$ARGUMENTS", "codex": "$1", "devin": "{feature}"}
INVOKE = {"claude": "/kiro-", "codex": "$kiro-", "devin": "/kiro:"}

BODY = """\
- Read `.kiro/specs/{arg}/spec.json` and `.kiro/specs/{arg}/requirements.md`.
- Next step: run `{invoke}spec-tasks {arg}` after `{invoke}validate-design {arg}`.
- Update spec.json: set `phase: "design-generated"`.
- Apply `rules/design-review.md` before writing.
"""

RULE = "# Design review\n\nWrite in `spec.json.language` / `pt`.\nCheck every boundary.\n"
REFERENCE_RULE = RULE.replace("/ `pt`", "/ `en`")
TEMPLATE = "# Reviewer prompt\n\nReview the task.\n"


def _skill_md(host: str, name: str, body: str) -> str:
    text = body.format(arg=ARG[host], invoke=INVOKE[host])
    if host == "claude":
        return (f"---\nname: {name}\ndescription: Design\nallowed-tools: Read, Write\n"
                f"argument-hint: <feature-name>\n---\n\n# {name} Skill\n\n## Core Mission\n"
                f"{text}")
    return (f"---\nname: {name}\ndescription: Design\n---\n\n\n# Technical Design\n\n"
            f"<background_information>\nYou are a spec agent ({name}).\n"
            f"</background_information>\n\n<instructions>\n{text}</instructions>\n")


def _mirror(
    name: str = "kiro-a", *, body: str = BODY, hosts: tuple[str, ...] = HOSTS,
    support: dict[str, str] | None = None,
) -> dict[str, str]:
    support = {"rules/design-review.md": RULE} if support is None else support
    files: dict[str, str] = {}
    for host in hosts:
        base = f"{SKILLS_DIR[host]}/{name}"
        files[f"{base}/SKILL.md"] = _skill_md(host, name, body)
        for rel, content in support.items():
            files[f"{base}/{rel}"] = content
        if host == "codex":
            files[f"{base}/agents/openai.yaml"] = f"interface:\n  display_name: {name}\n"
    return files


def _base_tree() -> dict[str, str]:
    return {**_mirror(), ".kiro/settings/rules/design-review.md": REFERENCE_RULE}


def _materialize(root: Path, tree: dict[str, str | bytes]) -> frozenset[str]:
    for rel, content in tree.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_bytes(content.encode("utf-8"))
    return frozenset(tree)


def _run_audit(tmp_path: Path, tree: dict[str, Any], config: str = TREE_CONFIG) -> Any:
    root = tmp_path / "tree"
    files = _materialize(root, tree)
    return audit.audit(root, audit.load_config(_write_config(tmp_path, config)), files=files)


def _kinds(report: Any) -> set[str]:
    return {str(f.kind) for f in report.findings}


def _failing(report: Any) -> list[str]:
    return [f.format() for f in report.failing()]


# --- 2.1 equivalent skills by semantic profile ---------------------------------------------

def test_profiles_ignore_host_syntax() -> None:
    profiles = {host: audit.profile_skill(_skill_md(host, "kiro-a", BODY),
                                          frozenset({"rules/design-review.md"}))
                for host in HOSTS}
    assert profiles["claude"] == profiles["codex"] == profiles["devin"]
    profile = profiles["claude"]
    assert profile.name == "kiro-a"
    assert profile.paths == frozenset({
        ".kiro/specs/{feature}/spec.json", ".kiro/specs/{feature}/requirements.md",
        "rules/design-review.md",
    })
    assert profile.skill_refs == frozenset({"kiro-spec-tasks", "kiro-validate-design"})
    assert profile.phases == frozenset({"design-generated"})
    assert profile.support_files == frozenset({"rules/design-review.md"})


def test_profile_normalizes_feature_placeholders_and_crlf() -> None:
    lf = "---\nname: kiro-x\n---\nRead `.kiro/specs/{feature-name}/tasks.md`.\n"
    crlf = lf.replace("{feature-name}", "$ARGUMENTS").replace("\n", "\r\n")
    assert audit.profile_skill(lf, frozenset()) == audit.profile_skill(crlf, frozenset())
    assert audit.profile_skill(lf, frozenset()).paths == frozenset(
        {".kiro/specs/{feature}/tasks.md"})


def test_syntax_only_differences_are_tolerated(tmp_path: Path) -> None:
    report = _run_audit(tmp_path, _base_tree())
    assert _failing(report) == []
    assert report.skills == (("kiro-a", HOSTS),)
    syntax = report.of_kind(audit.FindingKind.HOST_SYNTAX)
    assert {(f.subject, f.element) for f in syntax} == {
        ("kiro-a", "SKILL.md"), ("kiro-a", "host-metadata")}


def test_path_referenced_in_one_host_only_is_drift(tmp_path: Path) -> None:
    tree = _base_tree()
    claude_md = f"{SKILLS_DIR['claude']}/kiro-a/SKILL.md"
    tree[claude_md] += "- Also read `.kiro/steering/`.\n"
    report = _run_audit(tmp_path, tree)
    (drift,) = report.failing()
    assert (drift.kind, drift.subject, drift.hosts, drift.element) == (
        audit.FindingKind.DRIFT, "kiro-a", ("claude",), "paths")
    assert ".kiro/steering" in drift.detail and "codex, devin" in drift.detail
    assert not report.of_kind(audit.FindingKind.HOST_SYNTAX) or all(
        f.element == "host-metadata" for f in report.of_kind(audit.FindingKind.HOST_SYNTAX))


@pytest.mark.parametrize(("addition", "element", "value"), [
    ("- Then run `{invoke}impl {arg}`.\n", "skills", "kiro-impl"),
    ('- Or set `phase: "tasks-generated"`.\n', "phases", "tasks-generated"),
])
def test_skill_and_phase_divergences_are_drift(
    tmp_path: Path, addition: str, element: str, value: str
) -> None:
    tree = _base_tree()
    devin_md = f"{SKILLS_DIR['devin']}/kiro-a/SKILL.md"
    tree[devin_md] = _skill_md("devin", "kiro-a", BODY + addition)
    (drift,) = _run_audit(tmp_path, tree).failing()
    assert (drift.kind, drift.hosts, drift.element) == (
        audit.FindingKind.DRIFT, ("devin",), element)
    assert repr(value) in drift.detail


def test_frontmatter_name_divergence_is_drift(tmp_path: Path) -> None:
    tree = _base_tree()
    codex_md = f"{SKILLS_DIR['codex']}/kiro-a/SKILL.md"
    tree[codex_md] = tree[codex_md].replace("name: kiro-a", "name: kiro-b", 1)
    drifts = {(f.hosts, f.element, f.detail.split(" ")[0])
              for f in _run_audit(tmp_path, tree).failing()}
    assert (("codex",), "name", "'kiro-b'") in drifts
    assert (("claude", "devin"), "name", "'kiro-a'") in drifts


def test_support_file_set_divergence_is_drift(tmp_path: Path) -> None:
    tree = _base_tree()
    tree[f"{SKILLS_DIR['claude']}/kiro-a/templates/reviewer-prompt.md"] = TEMPLATE
    (drift,) = _run_audit(tmp_path, tree).failing()
    assert (drift.kind, drift.hosts, drift.element) == (
        audit.FindingKind.DRIFT, ("claude",), "support")
    assert "templates/reviewer-prompt.md" in drift.detail


def test_missing_skill_names_the_missing_host(tmp_path: Path) -> None:
    tree = {**_base_tree(), **_mirror("kiro-b", hosts=("claude", "codex"))}
    report = _run_audit(tmp_path, tree)
    (missing,) = report.failing()
    assert (missing.kind, missing.subject, missing.hosts) == (
        audit.FindingKind.MISSING_SKILL, "kiro-b", ("devin",))
    assert ("kiro-b", ("claude", "codex")) in report.skills


# --- 2.2 support files between hosts and against the reference copies ----------------------

def test_install_language_difference_is_not_a_finding(tmp_path: Path) -> None:
    tree = _base_tree()
    tree[f"{SKILLS_DIR['devin']}/kiro-a/rules/design-review.md"] = REFERENCE_RULE
    report = _run_audit(tmp_path, tree)
    assert _failing(report) == []
    assert audit.FindingKind.SUPPORT_DRIFT not in {f.kind for f in report.findings}


def test_support_file_diverging_between_hosts_is_reported(tmp_path: Path) -> None:
    tree = _base_tree()
    tree[f"{SKILLS_DIR['codex']}/kiro-a/rules/design-review.md"] = RULE + "Extra rule.\n"
    findings = {(f.kind, f.subject, f.hosts, f.element) for f in _run_audit(tmp_path, tree)
                .failing()}
    assert findings == {
        (audit.FindingKind.SUPPORT_DRIFT, "kiro-a/rules/design-review.md", HOSTS, "hosts"),
        (audit.FindingKind.SUPPORT_DRIFT, "kiro-a/rules/design-review.md", ("codex",),
         "reference"),
    }


def test_support_file_diverging_from_the_reference_is_reported(tmp_path: Path) -> None:
    tree = _base_tree()
    tree[".kiro/settings/rules/design-review.md"] = REFERENCE_RULE + "Upstream rule.\n"
    (finding,) = _run_audit(tmp_path, tree).failing()
    assert (finding.kind, finding.subject, finding.hosts, finding.element) == (
        audit.FindingKind.SUPPORT_DRIFT, "kiro-a/rules/design-review.md", HOSTS, "reference")
    assert ".kiro/settings/rules/design-review.md" in finding.detail


def test_template_without_reference_is_compared_between_hosts(tmp_path: Path) -> None:
    support = {"rules/design-review.md": RULE, "templates/reviewer-prompt.md": TEMPLATE}
    tree = {**_mirror(support=support),
            ".kiro/settings/rules/design-review.md": REFERENCE_RULE}
    assert _failing(_run_audit(tmp_path, tree)) == []
    tree[f"{SKILLS_DIR['devin']}/kiro-a/templates/reviewer-prompt.md"] = TEMPLATE + "More.\n"
    (finding,) = _run_audit(tmp_path / "second", tree).failing()
    assert (finding.kind, finding.subject, finding.element) == (
        audit.FindingKind.SUPPORT_DRIFT, "kiro-a/templates/reviewer-prompt.md", "hosts")
    assert "claude+codex | devin" in finding.detail


def test_support_files_compare_equal_across_line_endings(tmp_path: Path) -> None:
    tree: dict[str, Any] = _base_tree()
    rule = f"{SKILLS_DIR['claude']}/kiro-a/rules/design-review.md"
    tree[rule] = RULE.replace("\n", "\r\n").encode("utf-8")
    assert _failing(_run_audit(tmp_path, tree)) == []


# --- 2.3 host-only assets and accepted divergences -----------------------------------------

HOST_ONLY_ENTRY = """
[[host_only]]
path = ".codex/agents/spec-reviewer.toml"
host = "codex"
reason = "cross-spec reviewer used by kiro-spec-batch on Codex"
"""


@pytest.mark.parametrize("path", [
    ".codex/agents/spec-reviewer.toml",
    ".claude/commands/kiro/spec-init.md",
    ".agents/skills/other-skill/SKILL.md",
    ".devin/skills/README.md",
])
def test_undeclared_host_only_asset_fails(tmp_path: Path, path: str) -> None:
    tree = {**_base_tree(), path: "x\n"}
    (finding,) = _run_audit(tmp_path, tree).failing()
    assert (finding.kind, finding.subject) == (audit.FindingKind.HOST_ONLY_UNDECLARED, path)
    assert finding.hosts == ({".claude": ("claude",), ".agents": ("codex",),
                              ".codex": ("codex",), ".devin": ("devin",)}[path.split("/")[0]])


def test_declared_host_only_asset_is_informative(tmp_path: Path) -> None:
    tree = {**_base_tree(), ".codex/agents/spec-reviewer.toml": "x\n"}
    report = _run_audit(tmp_path, tree, TREE_CONFIG + HOST_ONLY_ENTRY)
    assert _failing(report) == []
    (info,) = report.of_kind(audit.FindingKind.HOST_ONLY)
    assert (info.subject, info.hosts) == (".codex/agents/spec-reviewer.toml", ("codex",))
    assert "kiro-spec-batch" in info.detail


def test_host_only_directory_entry_covers_a_skill(tmp_path: Path) -> None:
    tree = {**_base_tree(), **_mirror("kiro-only", hosts=("codex",))}
    entry = ('\n[[host_only]]\npath = ".agents/skills/kiro-only"\nhost = "codex"\n'
             'reason = "Codex-only skill"\n')
    report = _run_audit(tmp_path, tree, TREE_CONFIG + entry)
    assert _failing(report) == []
    assert report.skills == (("kiro-a", HOSTS),)


def test_skills_dir_is_a_host_dir_even_when_asset_dirs_omit_it(tmp_path: Path) -> None:
    config = TREE_CONFIG.replace('asset_dirs = [".agents", ".codex"]', 'asset_dirs = [".codex"]')
    tree = {**_base_tree(), ".agents/skills/other-skill/SKILL.md": "x\n"}
    (finding,) = _run_audit(tmp_path, tree, config).failing()
    assert (finding.kind, finding.subject, finding.hosts) == (
        audit.FindingKind.HOST_ONLY_UNDECLARED, ".agents/skills/other-skill/SKILL.md", ("codex",))


def test_files_outside_host_dirs_are_not_host_assets(tmp_path: Path) -> None:
    tree = {**_base_tree(), "docs/agentic.md": "x\n", ".github/workflows/ci.yml": "x\n"}
    assert _failing(_run_audit(tmp_path, tree)) == []


ACCEPTED_ENTRY = """
[[accepted]]
skill = "kiro-a"
element = "paths"
hosts = ["codex", "devin"]
value = ".kiro/specs/{feature}/design.md"
reason = "output wording; Claude cites specs/{feature}/design.md"
"""


def _wording_drift_tree() -> dict[str, str]:
    tree = _base_tree()
    for host in ("codex", "devin"):
        tree[f"{SKILLS_DIR[host]}/kiro-a/SKILL.md"] = _skill_md(
            host, "kiro-a", BODY + "- Output: `.kiro/specs/{arg}/design.md` written.\n")
    return tree


def test_registered_divergence_is_accepted_with_its_reason(tmp_path: Path) -> None:
    tree = _wording_drift_tree()
    assert [f.kind for f in _run_audit(tmp_path / "a", tree).failing()] == [
        audit.FindingKind.DRIFT]
    report = _run_audit(tmp_path / "b", tree, TREE_CONFIG + ACCEPTED_ENTRY)
    assert _failing(report) == []
    (accepted,) = report.of_kind(audit.FindingKind.ACCEPTED)
    assert (accepted.subject, accepted.hosts, accepted.element) == (
        "kiro-a", ("codex", "devin"), "paths")
    assert "output wording" in accepted.detail


def test_accepted_entry_must_match_hosts_and_value(tmp_path: Path) -> None:
    other_hosts = ACCEPTED_ENTRY.replace('["codex", "devin"]', '["codex"]')
    report = _run_audit(tmp_path, _wording_drift_tree(), TREE_CONFIG + other_hosts)
    assert {f.kind for f in report.failing()} == {
        audit.FindingKind.DRIFT, audit.FindingKind.STALE_ACCEPTED}


def test_accepted_entry_without_drift_fails_asking_for_removal(tmp_path: Path) -> None:
    report = _run_audit(tmp_path, _base_tree(), TREE_CONFIG + ACCEPTED_ENTRY)
    (stale,) = report.failing()
    assert (stale.kind, stale.subject, stale.hosts, stale.element) == (
        audit.FindingKind.STALE_ACCEPTED, "kiro-a", ("codex", "devin"), "paths")
    assert "remove" in stale.detail


def test_untracked_local_assets_do_not_change_the_report(tmp_path: Path) -> None:
    tree = _base_tree()
    clean = _run_audit(tmp_path / "clean", tree)
    root = tmp_path / "dirty" / "tree"
    files = _materialize(root, tree)
    _materialize(root, {".agents/skills/source-command-x/SKILL.md": "local\n",
                        ".claude/agents/local.md": "local\n"})
    config = audit.load_config(_write_config(tmp_path, TREE_CONFIG))
    assert audit.audit(root, config, files=files) == clean


# --- 2.4 host instructions -----------------------------------------------------------------

BEGIN = "<!-- theforge:invariants:begin -->"
END = "<!-- theforge:invariants:end -->"
INVARIANTS_BLOCK = (f"{BEGIN}\n## Invariantes\n- Core stdlib-only.\n"
                    f"- Integração só via Forge Protocol.\n{END}\n")
INSTRUCTION_CONFIG = TREE_CONFIG + f"""
[invariants]
begin = "{BEGIN}"
end = "{END}"
required = ["stdlib", "Forge Protocol"]

[budgets]
"CLAUDE.md" = 400
"AGENTS.md" = 600

[pointers]
"CLAUDE.md" = ["docs/agentic.md", ".claude/skills/"]
"AGENTS.md" = ["docs/agentic.md", ".agents/skills/", ".devin/skills/"]

[[moved_rules]]
anchor = "3-phase approval workflow"
from = "CLAUDE.md"
to = "docs/agentic.md"
"""


def _instruction_tree() -> dict[str, Any]:
    claude = f"# The Forge\n\n{INVARIANTS_BLOCK}\nSkills: `.claude/skills/`. Ver docs/agentic.md.\n"
    agents = (f"# The Forge\n\n{INVARIANTS_BLOCK}\nCodex: `.agents/skills/`.\n"
              "Devin: `.devin/skills/`.\nWorkflow: docs/agentic.md.\n")
    return {
        **_base_tree(),
        "CLAUDE.md": claude,
        "AGENTS.md": agents.replace("\n", "\r\n").encode("utf-8"),  # CRLF checkout
        "docs/agentic.md": "# Agentic\n\n- 3-phase approval\n  workflow: requirements first.\n",
    }


def _instruction_findings(report: Any) -> set[tuple[str, str, str]]:
    kinds = {audit.FindingKind.INVARIANTS, audit.FindingKind.BUDGET,
             audit.FindingKind.POINTER, audit.FindingKind.MOVED_RULE}
    return {(str(f.kind), f.subject, f.element) for f in report.findings if f.kind in kinds}


def test_consistent_instructions_have_no_findings_even_with_crlf(tmp_path: Path) -> None:
    report = _run_audit(tmp_path, _instruction_tree(), INSTRUCTION_CONFIG)
    assert _failing(report) == []


def test_instruction_checks_only_run_when_declared(tmp_path: Path) -> None:
    tree = {**_base_tree(), "CLAUDE.md": "x" * 5000 + "\n", "AGENTS.md": "no block\n"}
    assert _instruction_findings(_run_audit(tmp_path, tree)) == set()


@pytest.mark.parametrize(("mutate", "expected"), [
    (lambda t: t.update({"CLAUDE.md": t["CLAUDE.md"].replace(END, "")}),
     {("invariants", "CLAUDE.md", "block")}),
    (lambda t: t.update({"CLAUDE.md": t["CLAUDE.md"].replace("Core stdlib-only", "Core puro")}),
     {("invariants", "CLAUDE.md", "anchor"), ("invariants", "CLAUDE.md", "divergent"),
      ("invariants", "AGENTS.md", "divergent")}),
    (lambda t: t.update({"CLAUDE.md": t["CLAUDE.md"].replace(
        "- Core stdlib-only.\n", "- Core stdlib-only (Python >= 3.11).\n")}),
     {("invariants", "CLAUDE.md", "divergent"), ("invariants", "AGENTS.md", "divergent")}),
    (lambda t: t.update({"CLAUDE.md": t["CLAUDE.md"] + "x" * 400}),
     {("budget", "CLAUDE.md", "size")}),
    (lambda t: t.update({"CLAUDE.md": t["CLAUDE.md"].replace("`.claude/skills/`", "skills")}),
     {("pointer", "CLAUDE.md", "pointer")}),
    (lambda t: t.update({"docs/agentic.md": "# Agentic\n"}),
     {("moved-rule", "docs/agentic.md", "moved-rule")}),
    (lambda t: t.pop("docs/agentic.md"),
     {("moved-rule", "docs/agentic.md", "moved-rule")}),
    (lambda t: t.pop("AGENTS.md"),
     {("invariants", "AGENTS.md", "block"), ("budget", "AGENTS.md", "size"),
      ("pointer", "AGENTS.md", "pointer")}),
])
def test_instruction_defects_fail(tmp_path: Path, mutate: Any,
                                  expected: set[tuple[str, str, str]]) -> None:
    tree = _instruction_tree()
    mutate(tree)
    report = _run_audit(tmp_path, tree, INSTRUCTION_CONFIG)
    assert _instruction_findings(report) == expected
    assert all(f.failing for f in report.findings
               if (str(f.kind), f.subject, f.element) in expected)


def test_instruction_findings_name_file_hosts_and_detail(tmp_path: Path) -> None:
    tree = _instruction_tree()
    tree["AGENTS.md"] = tree["AGENTS.md"].replace(b"Forge Protocol", b"protocolo")
    tree["CLAUDE.md"] += "x" * 400
    report = _run_audit(tmp_path, tree, INSTRUCTION_CONFIG)
    anchor = next(f for f in report.findings if f.element == "anchor")
    assert (anchor.subject, anchor.hosts) == ("AGENTS.md", ("codex", "devin"))
    assert "'Forge Protocol'" in anchor.detail
    budget = next(f for f in report.findings if f.kind == audit.FindingKind.BUDGET)
    assert (budget.subject, budget.hosts) == ("CLAUDE.md", ("claude",))
    assert "> budget 400 bytes" in budget.detail


def test_budget_is_measured_in_utf8_bytes_with_lf(tmp_path: Path) -> None:
    text = "ç" * 100 + "\n" * 50  # 200 + 50 bytes with LF, 300 with CRLF
    config = TREE_CONFIG + '\n[budgets]\n"CLAUDE.md" = 250\n'
    tree: dict[str, Any] = {**_base_tree(),
                            "CLAUDE.md": text.replace("\n", "\r\n").encode("utf-8")}
    assert _failing(_run_audit(tmp_path / "ok", tree, config)) == []
    config = config.replace("= 250", "= 249")
    (finding,) = _run_audit(tmp_path / "over", tree, config).failing()
    assert "250 bytes > budget 249 bytes" in finding.detail


# --- 2.5 deterministic report and command line ---------------------------------------------

def _drifty_tree() -> dict[str, Any]:
    tree = {**_wording_drift_tree(), **_mirror("kiro-b", hosts=("claude",)),
            ".codex/agents/spec-reviewer.toml": "x\n"}
    tree[".kiro/settings/rules/design-review.md"] = REFERENCE_RULE + "Upstream.\n"
    return tree


def test_findings_are_totally_ordered_and_reproducible(tmp_path: Path) -> None:
    first = _run_audit(tmp_path / "a", _drifty_tree(), TREE_CONFIG + HOST_ONLY_ENTRY)
    second = _run_audit(tmp_path / "b", _drifty_tree(), TREE_CONFIG + HOST_ONLY_ENTRY)
    assert first == second
    assert list(first.findings) == sorted(first.findings)
    assert len(set(first.findings)) == len(first.findings)
    assert first.to_text() == second.to_text() and first.to_json() == second.to_json()


def test_text_report_has_skill_table_and_categories(tmp_path: Path) -> None:
    text = _run_audit(tmp_path, _drifty_tree(), TREE_CONFIG + HOST_ONLY_ENTRY).to_text()
    lines = text.splitlines()
    header = next(line for line in lines if line.strip().startswith("skill"))
    assert header.split() == ["skill", *HOSTS]
    assert next(line for line in lines if line.strip().startswith("kiro-b")).split() == [
        "kiro-b", "x", "-", "-"]
    for heading in ("drift (", "missing-skill (", "support-drift (", "host-only ("):
        assert any(line.startswith(heading) for line in lines), heading
    assert lines[-1].endswith("failing finding(s)")


def test_json_report_is_parseable_with_sorted_keys(tmp_path: Path) -> None:
    report = _run_audit(tmp_path, _drifty_tree(), TREE_CONFIG + HOST_ONLY_ENTRY)
    payload = json.loads(report.to_json())
    assert report.to_json() == json.dumps(payload, sort_keys=True, indent=2) + "\n"
    assert payload["hosts"] == list(HOSTS)
    assert {"name": "kiro-b", "hosts": ["claude"]} in payload["skills"]
    assert payload["failing"] == len(report.failing()) > 0
    assert {f["kind"] for f in payload["findings"]} >= {"drift", "missing-skill", "host-only"}


def _git_tree(root: Path, tree: dict[str, Any]) -> Path:
    root.mkdir(parents=True)
    _git(root, "init", "-q", ".")
    _materialize(root, tree)
    _git(root, "add", ".")
    return root


def _cli(*args: str | Path) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        [sys.executable, str(AUDIT_SCRIPT), *map(str, args)],
        capture_output=True, timeout=60, check=False,
    )


@requires_git
def test_cli_is_reproducible_and_exits_zero_without_failures(tmp_path: Path) -> None:
    repo = _git_tree(tmp_path / "repo", _instruction_tree())
    config = _write_config(tmp_path, INSTRUCTION_CONFIG)
    first = _cli("--root", repo, "--config", config)
    second = _cli("--root", repo, "--config", config)
    assert first.returncode == 0, first.stdout.decode() + first.stderr.decode()
    assert first.stdout == second.stdout
    assert b"no failing findings" in first.stdout
    as_json = _cli("--root", repo, "--config", config, "--json")
    assert as_json.returncode == 0
    assert json.loads(as_json.stdout)["failing"] == 0
    assert as_json.stdout == _cli("--root", repo, "--config", config, "--json").stdout


@requires_git
def test_cli_exits_one_and_lists_the_drift(tmp_path: Path) -> None:
    tree = _wording_drift_tree()
    tree[".agents/skills/source-command-x/SKILL.md"] = "untracked\n"
    repo = _git_tree(tmp_path / "repo", {k: v for k, v in tree.items()
                                         if "source-command" not in k})
    _materialize(repo, {".agents/skills/source-command-x/SKILL.md": "local\n"})  # untracked
    result = _cli("--root", repo, "--config", _write_config(tmp_path, TREE_CONFIG))
    assert result.returncode == 1
    out = result.stdout.decode("utf-8")
    assert "drift (1, FAIL):" in out
    assert "kiro-a [codex,devin] paths: '.kiro/specs/{feature}/design.md'" in out
    assert "source-command" not in out
    payload = json.loads(_cli("--root", repo, "--config", _write_config(tmp_path, TREE_CONFIG),
                              "--json").stdout)
    assert [f["kind"] for f in payload["findings"] if f["failing"]] == ["drift"]


@requires_git
def test_cli_config_or_git_error_exits_two_without_traceback(tmp_path: Path) -> None:
    repo = _git_tree(tmp_path / "repo", _base_tree())
    bad = _write_config(tmp_path, "unknown = 1\n" + TREE_CONFIG)
    result = _cli("--root", repo, "--config", bad)
    assert result.returncode == 2
    assert result.stdout == b""
    err = result.stderr.decode("utf-8")
    assert err.startswith("audit_assets: error: ") and "'unknown'" in err
    assert "Traceback" not in err
    plain = tmp_path / "plain"
    plain.mkdir()
    no_repo = _cli("--root", plain, "--config", _write_config(tmp_path, TREE_CONFIG))
    assert no_repo.returncode == 2
    assert b"Traceback" not in no_repo.stderr and b"git ls-files failed" in no_repo.stderr


def test_main_defaults_to_this_repository_and_the_versioned_config() -> None:
    assert audit.DEFAULT_ROOT == REPO
    assert audit.DEFAULT_CONFIG == CONFIG_FILE


# --- 4.7 the real repository is a gate -----------------------------------------------------

# Anchors the scoped invariants block must keep (req 3.1): core/adapters scope, the redaction
# boundary of the provider work dir and the development setup with editable adapters.
REQUIRED_ANCHORS = {
    "src/theforge", "adapters/", "stdlib", "Forge Protocol", "ambiguous", "ExecutionResult",
    "security.redact", ".forge/runs/<id>/work/", "domínio", "theforge/<Name>/v1",
    "python -m theforge.contracts.schema schemas",
    "-e ./adapters/sparkforge -e ./adapters/apiforge", "python -m pytest", "ruff check .", "mypy",
}


@pytest.fixture(scope="module")
def real_report() -> Any:
    if GIT is None:
        pytest.skip("git executable not found on PATH: the audit inventory comes from git")
    return audit.audit(REPO, audit.load_config(CONFIG_FILE))


def test_versioned_config_declares_every_instruction_check() -> None:
    config = audit.load_config(CONFIG_FILE)
    assert config.invariants is not None
    missing = {a for a in REQUIRED_ANCHORS
               if not any(a in declared for declared in config.invariants.required)}
    assert missing == set()
    assert config.budgets == {"AGENTS.md": 6000, "CLAUDE.md": 2500}
    assert config.pointers is not None
    assert set(config.pointers) == {"AGENTS.md", "CLAUDE.md"}
    assert {".claude/skills/", "docs/agentic.md", "spec.json.language"} <= set(
        config.pointers["CLAUDE.md"])
    assert {".agents/skills/", ".devin/skills/", "docs/agentic.md", "spec.json.language"} <= set(
        config.pointers["AGENTS.md"])
    assert config.moved_rules
    assert "3-phase approval workflow" in {rule.anchor for rule in config.moved_rules}
    assert {rule.target for rule in config.moved_rules} == {"docs/agentic.md"}


@pytest.mark.parametrize("kind", sorted(audit.FAILING))
def test_real_repository_has_no_failing_findings(real_report: Any, kind: Any) -> None:
    found = real_report.of_kind(kind)
    assert found == (), "\n".join(finding.format() for finding in found)


def test_real_repository_lists_the_17_skills_in_the_three_hosts(real_report: Any) -> None:
    skills = dict(real_report.skills)
    assert len(skills) == 17 and all(name.startswith("kiro-") for name in skills)
    assert all(tuple(hosts) == ("claude", "codex", "devin") for hosts in skills.values()), skills


@pytest.mark.parametrize("path", ["CLAUDE.md", "AGENTS.md"])
def test_changing_an_invariant_line_in_one_file_fails(tmp_path: Path, path: str) -> None:
    config = audit.load_config(CONFIG_FILE)
    assert config.invariants is not None
    tree: dict[str, Any] = {p: (REPO / p).read_bytes() for p in ("CLAUDE.md", "AGENTS.md")}
    lines = tree[path].decode("utf-8").splitlines(keepends=True)
    begin = next(i for i, line in enumerate(lines) if config.invariants.begin in line)
    lines[begin + 2] = lines[begin + 2].rstrip("\r\n") + " (alterado)\n"
    tree[path] = "".join(lines).encode("utf-8")
    report = audit.audit(tmp_path, config, _materialize(tmp_path, tree))
    divergent = {f.subject for f in report.of_kind(audit.FindingKind.INVARIANTS)
                 if f.element == "divergent"}
    assert divergent == {"CLAUDE.md", "AGENTS.md"}


@pytest.mark.parametrize("pattern, problem", [
    ("(a+)+b", "nested quantifiers"),
    ("(?:x*)*", "nested quantifiers"),
    ("a" * 201, "longer than 200"),
])
def test_placeholder_pattern_that_could_backtrack_catastrophically_is_refused(
        tmp_path: Path, pattern: str, problem: str) -> None:
    text = MINIMAL_CONFIG + (
        f"\n[[install_placeholders]]\npattern = '{pattern}'\nreplacement = 'x'\n")
    with pytest.raises(audit.AgenticConfigError, match=problem):
        audit.load_config(_write_config(tmp_path, text))
