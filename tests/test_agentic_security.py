"""Agentic adversarial suite (agentic prompt §75-79, §17, §97).

Threat classes exercised at unit level — the end-to-end variants live in the
A-series (``scripts/bench/run_agentic.py`` A08/A09/A12):

- §75 injection: provider/knowledge data can never carry authority — the
  closed schema rejects injected fields, and UNIVERSAL_FORBIDDEN walls the
  actions a manifest could try to smuggle in.
- §76 fake providers: ``load_package`` refuses unknown keys, missing required
  fields and non-conforming ids; a canonical skill claiming a specialist that
  has no knowledge package fails the audit.
- §77 authority escalation: ``authority`` is a closed literal; ``approve``,
  ``grant-trust``, ``waive-verification`` and ``modify-registry`` are
  forbidden for every agent by construction — omitting them fails the spec.
- §78 stale skills: a canonical ``[freshness]`` claim that disagrees with the
  knowledge package's ``tested_version`` is a failing finding; dead skill
  invocations are too.
- §79 fake installations / verification bypass: ``plan_installation`` refuses
  entries without a verifiable distribution and unversioned (``latest``)
  entries never reach it.
"""

import importlib.util
import json
import re
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO = Path(__file__).resolve().parents[1]
AUDIT_SCRIPT = REPO / "scripts" / "agentic" / "audit_assets.py"


def _load_audit() -> ModuleType:
    spec = importlib.util.spec_from_file_location("audit_assets", AUDIT_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


audit = _load_audit()

from theforge.agents import check_authority, load_all  # noqa: E402
from theforge.contracts import ContractError, from_dict  # noqa: E402
from theforge.contracts.agent import AGENT_SPEC_SCHEMA, UNIVERSAL_FORBIDDEN, AgentSpec  # noqa: E402
from theforge.contracts.registry import ForgeRegistryEntry  # noqa: E402
from theforge.errors import UsageError  # noqa: E402
from theforge.knowledge import load_package  # noqa: E402
from theforge.registry.install_plan import plan_installation  # noqa: E402

MINIMAL_CONFIG = """\
[hosts.claude]
skills_dir = ".claude/skills"
instructions = ["CLAUDE.md"]
"""


def _write_config(tmp_path: Path) -> Path:
    cfg = tmp_path / "agentic.toml"
    cfg.write_text(MINIMAL_CONFIG, encoding="utf-8")
    return cfg


def _canonical(
    name: str,
    *,
    description: str = "Trigger text.",
    freshness: str = "",
    body: str = "## Overview\n\nBody.\n\n## Boundaries\n\n- Never installs.\n",
) -> str:
    return (
        "+++\n"
        f'name = "{name}"\n'
        f'description = "{description}"\n'
        f"{freshness}"
        "+++\n\n"
        f"# {name}\n\n{body}"
    )


def _audit(tmp_path: Path, files: dict[str, str]):
    for rel, text in files.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    config = audit.load_config(_write_config(tmp_path))
    return audit.audit(tmp_path, config, frozenset(files))


def _quality_findings(report) -> list:
    return [f for f in report.findings if f.kind == audit.FindingKind.SKILL_QUALITY]


# --- §78 stale skills / dead references ------------------------------------------------------


def test_stale_freshness_claim_fails(tmp_path: Path) -> None:
    report = _audit(
        tmp_path,
        {
            "agentic/skills/forge-x.md": _canonical(
                "forge-x",
                freshness='[freshness]\nspecialists = ["fake-spec"]\n'
                'tested_version = "9.9.9"\n',
            ),
            "forge-knowledge/fake-spec.json": json.dumps(
                {"provider_id": "fake-spec", "tested_version": "0.1.0"}
            ),
        },
    )
    assert any(
        f.element == "freshness" and "stale" in f.detail
        for f in _quality_findings(report)
    )


def test_dead_invocation_ref_fails(tmp_path: Path) -> None:
    report = _audit(
        tmp_path,
        {
            "agentic/skills/forge-x.md": _canonical(
                "forge-x",
                body="## Overview\n\nRun `$forge-nonexistent` first.\n\n"
                "## Boundaries\n\n- Never installs.\n",
            ),
        },
    )
    assert any(
        f.element == "references" and "forge-nonexistent" in f.detail
        for f in _quality_findings(report)
    )


def test_missing_description_fails(tmp_path: Path) -> None:
    report = _audit(
        tmp_path,
        {"agentic/skills/forge-x.md": _canonical("forge-x", description="")},
    )
    assert any(f.element == "description" for f in _quality_findings(report))


# --- §78 dead CLI commands ---------------------------------------------------------------
#
# Skills quote `theforge ...` invocations; a dead verb sends the agent down a
# dead path. The check resolves every backticked verb chain against the real
# argparse parser — it lives in the test suite (not the audit script) because
# the audit stays stdlib-only with no theforge import.

_CLI_CMD = re.compile(r"`(?:theforge|forge)\s+([^`]{1,140}?)`")
_CLI_TOKEN = re.compile(r"[a-z][a-z0-9-]*")
_CLI_PLACEHOLDER = re.compile(r"<[^>]*>|\"[^\"]*\"|'[^']*'|\[[^\]]*\]")


def _cli_verb_paths() -> frozenset[tuple[str, ...]]:
    import argparse

    from theforge.cli.main import build_parser

    paths: set[tuple[str, ...]] = set()

    def walk(parser: argparse.ArgumentParser, prefix: tuple[str, ...]) -> None:
        for action in parser._actions:
            if isinstance(action, argparse._SubParsersAction):
                for name, sub_parser in action.choices.items():
                    paths.add(prefix + (name,))
                    walk(sub_parser, prefix + (name,))

    walk(build_parser(), ())
    return frozenset(paths)


def _cli_command_problem(command: str, paths: frozenset[tuple[str, ...]]) -> str | None:
    cleaned = _CLI_PLACEHOLDER.sub(" ", command)
    tokens = _CLI_TOKEN.findall(cleaned)
    if not tokens:
        return "empty command"
    if (tokens[0],) not in paths:
        return f"unknown verb {tokens[0]!r}"
    depth = 0
    while depth < len(tokens) and tuple(tokens[: depth + 1]) in paths:
        depth += 1
    if depth == len(tokens):
        return None
    prefix = tuple(tokens[:depth])
    children = sorted({p[depth] for p in paths if len(p) > depth and p[:depth] == prefix})
    if children:
        return (
            f"{tokens[depth]!r} is not a subcommand of `{' '.join(prefix)}`"
            f" (valid: {', '.join(children)})"
        )
    return None  # trailing tokens are arguments, not subcommands


def test_dead_cli_command_detected() -> None:
    paths = _cli_verb_paths()
    assert _cli_command_problem("providers add <id>", paths) is not None
    assert _cli_command_problem("knowledge frobnicate", paths) is not None


def test_valid_cli_commands_and_args_pass() -> None:
    """Real verbs plus placeholder/quoted arguments are fine — the check only
    flags tokens where a subcommand was expected."""
    paths = _cli_verb_paths()
    for cmd in (
        "knowledge show <id>",
        "knowledge check",
        "registry list",
        "registry refresh",
        'ask "<task>"',
        "plan <task>",
        "resume <id>",
    ):
        assert _cli_command_problem(cmd, paths) is None, cmd


def test_all_skills_quote_only_real_cli_verbs() -> None:
    """Every backticked `theforge`/`forge` invocation in every skill —
    canonical sources and host mirrors — resolves against the live parser."""
    paths = _cli_verb_paths()
    skill_mds = sorted(REPO.glob("agentic/skills/*.md")) + sorted(
        REPO.glob(".claude/skills/**/SKILL.md")
    )
    assert skill_mds, "no skills found"
    problems: list[str] = []
    for md in skill_mds:
        for m in _CLI_CMD.finditer(md.read_text(encoding="utf-8")):
            bad = _cli_command_problem(m.group(1), paths)
            if bad is not None:
                problems.append(f"{md.relative_to(REPO)}: `theforge {m.group(1)}` — {bad}")
    assert not problems, "\n".join(problems)


def test_prose_family_mention_is_not_a_reference(tmp_path: Path) -> None:
    """`forge-aws` in prose is a family shorthand, not a skill invocation."""
    report = _audit(
        tmp_path,
        {
            "agentic/skills/forge-x.md": _canonical(
                "forge-x",
                body="## Overview\n\nThe forge-aws family covers Spark.\n\n"
                "## Boundaries\n\n- Never installs.\n",
            ),
        },
    )
    assert not _quality_findings(report)


def test_unknown_freshness_specialist_fails(tmp_path: Path) -> None:
    report = _audit(
        tmp_path,
        {
            "agentic/skills/forge-x.md": (
                "+++\n"
                'name = "forge-x"\n'
                'description = "d"\n'
                "[freshness]\n"
                'specialists = ["ghost-provider"]\n'
                "+++\n\n# forge-x\n\n## Overview\n\no\n\n## Boundaries\n\n- n\n"
            ),
        },
    )
    assert any(
        f.element == "freshness" and "ghost-provider" in f.detail
        for f in _quality_findings(report)
    )


# --- §76 fake providers ------------------------------------------------------------------------


def _real_package() -> dict:
    """A genuine knowledge package, mutated per test — fixtures never invent schema."""
    return json.loads((REPO / "forge-knowledge" / "api-forge.json").read_text("utf-8"))


def test_fake_provider_unknown_field_rejected(tmp_path: Path) -> None:
    """A package smuggling an authority field fails closed-schema validation."""
    pkg = _real_package()
    pkg["trust_level"] = "admin"  # injected: not part of the contract
    pkg["priority_multiplier"] = 99
    path = tmp_path / "api-forge.json"
    path.write_text(json.dumps(pkg), encoding="utf-8")
    with pytest.raises(ContractError, match="unknown field"):
        load_package(path)


def test_fake_provider_missing_required_field_rejected(tmp_path: Path) -> None:
    pkg = _real_package()
    del pkg["package"]
    del pkg["install"]
    path = tmp_path / "api-forge.json"
    path.write_text(json.dumps(pkg), encoding="utf-8")
    with pytest.raises(ContractError, match="required|missing"):
        load_package(path)


def test_fake_provider_wrong_schema_rejected(tmp_path: Path) -> None:
    pkg = _real_package()
    pkg["schema"] = "theforge/ForgeRegistryEntry/v1"  # schema spoof
    path = tmp_path / "api-forge.json"
    path.write_text(json.dumps(pkg), encoding="utf-8")
    with pytest.raises(ContractError):
        load_package(path)


# --- §77 authority escalation / §78 verification bypass -----------------------------------------


def _agent_spec(**kw):
    base = {
        "schema": AGENT_SPEC_SCHEMA,
        "id": "evil-agent",
        "name": "Evil",
        "role": "r",
        "authority": "propose",
        "purpose": "p",
        "output_contracts": ["theforge/RoutingProposal/v1"],
        "forbidden_actions": sorted(UNIVERSAL_FORBIDDEN),
    }
    base.update(kw)
    return base


def test_authority_is_a_closed_literal() -> None:
    """``approve`` can never be an authority level — it is a forbidden action."""
    with pytest.raises(ContractError, match="authority"):
        from_dict(AgentSpec, _agent_spec(authority="approve"), "$")


def test_spec_without_verification_wall_fails() -> None:
    """Dropping ``waive-verification`` from forbidden_actions breaks the spec."""
    with pytest.raises(ContractError, match="waive-verification"):
        from_dict(
            AgentSpec,
            _agent_spec(forbidden_actions=["grant-trust", "approve"]),
            "$",
        )


def test_spec_without_registry_wall_fails() -> None:
    with pytest.raises(ContractError, match="modify-registry"):
        from_dict(
            AgentSpec,
            _agent_spec(
                forbidden_actions=["grant-trust", "approve", "waive-verification"]
            ),
            "$",
        )


def test_every_real_spec_fails_the_escalation_wall() -> None:
    """All eight canonical specs deny every universally-forbidden action."""
    specs = load_all()
    assert len(specs) == 8
    for spec in specs.values():
        for action in UNIVERSAL_FORBIDDEN:
            allowed, reason = check_authority(spec, action)
            assert not allowed, f"{spec.id} unexpectedly allowed {action}"
            assert reason


def test_execute_approved_cannot_verify_or_approve() -> None:
    """The installer ceiling: it plans and runs the approved install — it can
    never verify its own work, route, execute provider ops or approve."""
    installer = load_all()["bootstrap-installation"]
    for action in ("approve", "verify", "grant-trust", "modify-registry",
                   "route", "execute", "waive-verification"):
        allowed, _ = check_authority(installer, action)
        assert not allowed, f"installer unexpectedly allowed {action}"
    for action in ("install", "plan"):
        assert check_authority(installer, action)[0]


# --- §79 fake installations ----------------------------------------------------------------------


def test_install_plan_refuses_undistributable_entry() -> None:
    entry = ForgeRegistryEntry(provider="fake-forge", version="1.0.0")
    assert entry.distribution is None
    with pytest.raises(UsageError, match="distribution"):
        plan_installation(entry, source_id="s", registry_id="r")


def test_unversioned_entry_never_reaches_planning() -> None:
    """``latest`` is not a version: the entry itself fails validation."""
    with pytest.raises(ContractError):
        ForgeRegistryEntry(provider="fake-forge", version="latest")
