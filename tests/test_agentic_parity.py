"""Agentic asset audit: configuration, tracked inventory and text normalization.

Requirements 1.6 (no network, no writes, no local assets), 2.6 (same offline run, no new
dependency), 10.2 (deterministic, same result on Linux and Windows) and 10.3 (local untracked
assets do not change the result).

The audit logic lives only in ``scripts/agentic/audit_assets.py``; these tests load that file
by path (the ``scripts/ci`` pattern) instead of re-implementing it.
"""

import importlib.util
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
