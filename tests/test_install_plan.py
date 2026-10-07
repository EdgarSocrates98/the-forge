"""Cycle 4 Wave F — InstallationPlan/v2: deterministic, approval-gated,
plan-only provisioning of a remote candidate.

Gate: no side effect without approval — `install plan` emits a document;
nothing is downloaded, installed, or trusted (§27-30). 'latest' is never
installable.
"""

import json
from pathlib import Path

import pytest

from theforge.cli.main import main
from theforge.contracts import ContractError, from_dict, to_dict
from theforge.contracts.installation import (
    INSTALL_STAGES,
    InstallationPlanV2,
    InstallStep,
)
from theforge.contracts.registry import (
    DistributionRef,
    ForgeRegistryEntry,
    PublisherIdentity,
    RegistryDocument,
    RegistryIdentity,
    RuntimeRequirements,
    SignatureRef,
)
from theforge.errors import UsageError
from theforge.meta import PRODUCER
from theforge.registry.install_plan import build_install_plan, plan_installation


def dist(**kw: object) -> DistributionRef:
    kw.setdefault("kind", "pip-package")
    kw.setdefault("package", "acme-forge")
    kw.setdefault("version", "1.2.3")
    return DistributionRef(**kw)


def entry(provider: str = "acme-forge", version: str = "1.2.3",
          **kw: object) -> ForgeRegistryEntry:
    kw.setdefault("distribution", dist())
    return ForgeRegistryEntry(provider=provider, version=version,
                              capabilities=["security.scan"], **kw)


def source_with(user_dir: Path, *entries: ForgeRegistryEntry,
                source_id: str = "feed", enabled: bool = True) -> None:
    """Writes a local-file source into the isolated THEFORGE_CONFIG_DIR."""
    doc = RegistryDocument(registry=RegistryIdentity(id="reg-feed"),
                           produced_at="t", entries=list(entries))
    (user_dir / "feed.json").write_text(
        json.dumps(to_dict(doc)), encoding="utf-8")
    (user_dir / "registries.toml").write_text(
        f'[[sources]]\nid = "{source_id}"\nkind = "local-file"\n'
        f'path = "feed.json"\nenabled = {"true" if enabled else "false"}\n',
        encoding="utf-8")


def build(tmp_path: Path, provider="acme-forge", version="1.2.3",
          source="feed", approve=False):
    return build_install_plan(provider, version, source,
                              forge_dir=tmp_path / ".forge", approve=approve)


# ── contract validation ─────────────────────────────────────────────────────

def test_plan_rejects_unpinned_version() -> None:
    # ForgeRegistryEntry already rejects non-SemVer at construction; the v2
    # contract is a second line of defense (a plan built from raw data must
    # refuse 'latest' too).
    for bad in ("latest", "", "1.0", "v1.2.3"):
        with pytest.raises(ContractError, match="pinned|latest|SemVer"):
            InstallationPlanV2(
                producer=PRODUCER, created_at="t", provider="acme-forge",
                version=bad, source="s", distribution=dist(),
                environment="venv:x")


def test_plan_requires_full_stage_order() -> None:
    e = entry()
    base = plan_installation(e, source_id="s", registry_id=None)
    shuffled = [InstallStep(stage=s, description="d")
                for s in reversed(INSTALL_STAGES)]
    with pytest.raises(ContractError, match="stage order"):
        InstallationPlanV2(
            producer=PRODUCER, created_at="t", provider="p", version="1.0.0",
            source="s", distribution=dist(), environment="venv:x",
            steps=shuffled)
    with pytest.raises(ContractError, match="unknown stages"):
        InstallationPlanV2(
            producer=PRODUCER, created_at="t", provider="p", version="1.0.0",
            source="s", distribution=dist(), environment="venv:x",
            steps=[InstallStep(stage="arbitrary-code", description="d")])
    assert [s.stage for s in base.steps] == list(INSTALL_STAGES)


def test_plan_needs_pip_distribution_pins() -> None:
    with pytest.raises(ContractError, match="pinned"):
        InstallationPlanV2(
            producer=PRODUCER, created_at="t", provider="p", version="1.0.0",
            source="s", distribution=DistributionRef(kind="pip-package"),
            environment="venv:x")


# ── plan_installation (pure) ────────────────────────────────────────────────

def test_plan_collects_hashes_and_signature() -> None:
    e = entry(manifest_sha256="a" * 64, hashes={"wheel": "b" * 64},
              signatures=[SignatureRef(key_id="k", algorithm="ed25519",
                                       signature="s")],
              distribution=dist(sha256="c" * 64))
    plan = plan_installation(e, source_id="feed", registry_id="reg")
    assert plan.expected_hashes == {"wheel": "b" * 64, "manifest": "a" * 64,
                                    "distribution": "c" * 64}
    assert plan.signature is not None and plan.signature.key_id == "k"
    assert plan.approval.required and not plan.approval.granted
    assert all(s.status == "pending" for s in plan.steps)
    assert plan.planning_only is True
    assert plan.rollback.action == "remove-new"  # nothing installed before


def test_plan_permissions_from_runtime_claims() -> None:
    e = entry(runtime=RuntimeRequirements(requires_network=True,
                                          requires_credentials=True))
    plan = plan_installation(e, source_id="s", registry_id=None)
    assert plan.permissions == ["network", "credentials"]


def test_plan_flags_missing_hashes_and_unpinned_deps() -> None:
    e = entry(dependencies=["good==1.0", "floating>=2"])
    plan = plan_installation(e, source_id="s", registry_id=None)
    assert any("no expected hashes" in lim for lim in plan.limitations)
    assert any("unpinned" in lim for lim in plan.limitations)


def test_plan_without_distribution_fails() -> None:
    bare = ForgeRegistryEntry(provider="x-forge", version="1.0.0")
    with pytest.raises(UsageError, match="distribution"):
        plan_installation(bare, source_id="s", registry_id=None)


def test_plan_rollback_with_existing(tmp_path: Path) -> None:
    from theforge.contracts.manifest import Capability, ForgeManifest, Signals
    from theforge.registry import ProviderEntry, RegistryRecord
    existing = RegistryRecord(
        entry=ProviderEntry(id="acme-forge", argv=["x"]), state="ready",
        manifest=ForgeManifest(id="acme-forge", version="1.0.0",
                               protocols=["forge/v1"], ops=["describe", "health"],
                               capabilities=[Capability(
                                   id="security.scan", actions=["run"],
                                   default_action="run", state="supported",
                                   operation_class="read_only",
                                   signals=Signals())]),
        manifest_sha256="d" * 64, protocol="forge/v1")
    plan = plan_installation(entry(), source_id="s", registry_id=None,
                             existing=existing)
    assert plan.rollback.action == "restore-previous"
    assert plan.rollback.previous_version == "1.0.0"
    assert plan.rollback.previous_manifest_sha256 == "d" * 64


# ── build_install_plan (source resolution) ──────────────────────────────────

def test_build_resolves_entry(tmp_path: Path, user_config_dir: Path) -> None:
    source_with(user_config_dir, entry())
    result = build(tmp_path)
    assert result.plan.provider == "acme-forge"
    assert result.plan.registry == "reg-feed"


def test_build_unknown_source(tmp_path: Path, user_config_dir: Path) -> None:
    with pytest.raises(UsageError, match="unknown registry source"):
        build(tmp_path)


def test_build_disabled_source_refused(tmp_path: Path, user_config_dir: Path) -> None:
    source_with(user_config_dir, entry(), enabled=False)
    with pytest.raises(UsageError, match="disabled"):
        build(tmp_path)


def test_build_version_not_listed(tmp_path: Path, user_config_dir: Path) -> None:
    source_with(user_config_dir, entry(version="1.0.0"), entry(version="2.0.0"))
    with pytest.raises(UsageError, match="available: 1.0.0, 2.0.0"):
        build(tmp_path, version="9.9.9")


def test_build_approve_marks_gate(tmp_path: Path, user_config_dir: Path) -> None:
    source_with(user_config_dir, entry())
    plan = build(tmp_path, approve=True).plan
    assert plan.approval.granted and plan.approval.granted_by == "cli-user"
    # Even approved, every stage stays pending — the plan never executes.
    assert all(s.status == "pending" for s in plan.steps)


# ── CLI ─────────────────────────────────────────────────────────────────────

def test_cli_install_plan(tmp_path: Path, user_config_dir: Path,
                          capsys: pytest.CaptureFixture[str]) -> None:
    source_with(user_config_dir, entry(publisher=PublisherIdentity(id="acme")))
    code = main(["install", "plan", "--provider", "acme-forge",
                 "--version", "1.2.3", "--source", "feed",
                 "--root", str(tmp_path)])
    out = capsys.readouterr().out
    assert code == 0
    assert "install plan (v2" in out
    assert "No action was taken" in out
    assert "approval: required=True granted=False" in out


def test_cli_install_plan_json(tmp_path: Path, user_config_dir: Path,
                               capsys: pytest.CaptureFixture[str]) -> None:
    source_with(user_config_dir, entry())
    code = main(["install", "plan", "--provider", "acme-forge",
                 "--version", "1.2.3", "--source", "feed",
                 "--root", str(tmp_path), "--json"])
    data = json.loads(capsys.readouterr().out)
    assert code == 0
    plan = data["plan"]
    assert plan["schema"] == "theforge/InstallationPlan/v2"
    assert plan["planning_only"] is True
    # Round-trips through the contract.
    from_dict(InstallationPlanV2, plan, "$")
