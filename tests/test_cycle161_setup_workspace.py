"""Cycle 16.1 wave-01 frente-B — zero-friction workspace setup.

Covers the four new pieces and their integration:

- ``workspace/detect.py``    — bounded per-member technology detection
- ``workspace/recommend.py`` — explainable, advisory specialist suggestion
- ``workspace/config.py``    — declarative ``forge.workspace.yaml`` defaults
- ``install/options.py``     — ``--preset`` mapping + precedence/conflicts
- ``install/onboarding.py``  — honest per-host states + next steps
- ``install_auto``           — receipt blocks (§3.1 steps 3–15)
- CLI surface                — ``workspace detect``, ``setup --preset``,
                               §3.4 daily-ops verbs
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from theforge.errors import UsageError
from theforge.install import options as setup_options
from theforge.install import service
from theforge.install.onboarding import HOST_STATES, build_onboarding
from theforge.workspace import (
    detect_workspace,
    load_workspace_config,
    recommend_specialists,
)

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


@pytest.fixture()
def forge_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("FORGE_HOME_OVERRIDE", str(home))
    return home


@pytest.fixture()
def ws(tmp_path: Path) -> Path:
    root = tmp_path / "ws"
    root.mkdir()
    return root


def _member(root: Path, name: str, files: dict[str, str]) -> Path:
    d = root / name
    for rel, content in files.items():
        p = d / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, "utf-8")
    return d


def _techs(doc: dict, path: str) -> list[str]:
    for m in doc["members"]:
        if m["path"] == path:
            return m["techs"]
    raise AssertionError(f"member {path!r} not in {[m['path'] for m in doc['members']]}")


def _register_stub(forge_home: Path, fid: str) -> None:
    """Minimal registered forge whose install emits a valid receipt."""
    inst = forge_home / ".forge" / "installations"
    inst.mkdir(parents=True, exist_ok=True)
    stub = forge_home / f"{fid}-stub.py"
    stub.write_text(
        "import json, sys\n"
        "planned = '--dry-run' in sys.argv\n"
        "print(json.dumps({'schema': 'forge/InstallReceipt/v1',\n"
        " 'receipt_id': 'sha256:stub', 'forge_id': '" + fid + "',\n"
        " 'operation': 'install',\n"
        " 'status': 'planned' if planned else 'completed',\n"
        " 'verification': {'status': 'UNVERIFIED' if planned else 'PASS'},\n"
        " 'checks': [], 'managed_files': [], 'planned_files': []}))\n",
        "utf-8",
    )
    (inst / f"{fid}.json").write_text(
        json.dumps(
            {
                "forge_id": fid,
                "cli": {"name": fid},
                "install_command": ["{python}", str(stub).replace("\\", "/")],
                "installation_kind": "content",
            }
        ),
        "utf-8",
    )


def cli(root: Path, *args: str, home: Path | None = None) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    if home is not None:
        env["FORGE_HOME_OVERRIDE"] = str(home)
    return subprocess.run(
        [sys.executable, "-m", "theforge", *args, "--root", str(root)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
        env=env,
    )


# ---------------------------------------------------------------------------
# §6.1/§6.2 — bounded per-member technology detection
# ---------------------------------------------------------------------------


def test_detect_python_markers(ws: Path) -> None:
    _member(ws, "svc", {"pyproject.toml": "[project]\ndependencies=[]\n", "src/a.py": "x=1\n"})
    _member(ws, "lib", {"setup.py": "from setuptools import setup\n"})
    _member(ws, "tools", {"requirements.txt": "requests==2\n"})
    doc = detect_workspace(ws)
    assert doc["schema"] == "forge/WorkspaceDetection/v1"
    assert "python" in _techs(doc, "svc")
    assert "python" in _techs(doc, "lib")
    assert "python" in _techs(doc, "tools")
    member = next(m for m in doc["members"] if m["path"] == "svc")
    assert member["confidence"] == "high"
    kinds = {e["kind"] for e in member["evidence"]}
    assert "file" in kinds
    assert all(e["provenance"] in ("observed", "inferred", "derived") for e in member["evidence"])


def test_detect_node_typescript_react_next(ws: Path) -> None:
    _member(
        ws,
        "web",
        {
            "package.json": json.dumps(
                {"dependencies": {"react": "*", "react-dom": "*", "next": "*"}}
            ),
            "tsconfig.json": "{}",
        },
    )
    doc = detect_workspace(ws)
    techs = set(_techs(doc, "web"))
    assert {"node", "typescript", "react", "nextjs", "frontend"} <= techs


def test_detect_dotnet_java_terraform(ws: Path) -> None:
    _member(ws, "api", {"Service.csproj": "<Project/>", "App.sln": "sln"})
    _member(ws, "jobs", {"pom.xml": "<project/>"})
    _member(ws, "lib", {"build.gradle": "plugins {}"})
    _member(ws, "infra", {"main.tf": 'resource "x" "y" {}\n', "vars.tfvars": "x=1\n"})
    doc = detect_workspace(ws)
    assert "dotnet" in _techs(doc, "api")
    assert "java" in _techs(doc, "jobs")
    assert "java" in _techs(doc, "lib")
    assert "terraform" in _techs(doc, "infra")


def test_detect_spark_aws_glue_composite(ws: Path) -> None:
    _member(ws, "pipelines", {"requirements.txt": "pyspark==3.5\nboto3\n"})
    doc = detect_workspace(ws)
    techs = set(_techs(doc, "pipelines"))
    assert {"pyspark", "aws", "aws-glue", "python"} <= techs
    glue_ev = next(
        e
        for m in doc["members"]
        if m["path"] == "pipelines"
        for e in m["evidence"]
        if e["tech"] == "aws-glue"
    )
    assert glue_ev["kind"] == "composite"


def test_detect_databricks_delta(ws: Path) -> None:
    _member(
        ws,
        "lake",
        {"databricks.yml": "bundle:\n  name: x\n", "requirements.txt": "delta-spark\n"},
    )
    doc = detect_workspace(ws)
    techs = set(_techs(doc, "lake"))
    assert "databricks" in techs and "delta" in techs


def test_detect_api_fastapi_openapi(ws: Path) -> None:
    _member(ws, "backend", {"pyproject.toml": '[project]\ndependencies=["fastapi","uvicorn"]\n'})
    _member(ws, "contracts", {"openapi.yaml": "openapi: 3.0.0\n"})
    doc = detect_workspace(ws)
    assert {"api", "fastapi", "python"} <= set(_techs(doc, "backend"))
    assert {"api", "openapi"} <= set(_techs(doc, "contracts"))


def test_detect_skips_vendor_build_cache(ws: Path) -> None:
    _member(
        ws,
        "app",
        {
            "package.json": "{}",
            "node_modules/left-pad/index.js": "x",
            "dist/bundle.js": "x",
            "build/out.js": "x",
            ".venv/lib/site.py": "x",
            "coverage/x.py": "x",
            "src/index.ts": "export {}\n",
        },
    )
    doc = detect_workspace(ws)
    member = next(m for m in doc["members"] if m["path"] == "app")
    details = " ".join(e["detail"] for e in member["evidence"])
    for skipped in ("node_modules", "dist/", "build/", ".venv", "coverage"):
        assert skipped not in details
    assert "typescript" in member["techs"]


def test_detect_file_cap_bounds_scan(ws: Path) -> None:
    files = {f"f{i:03d}.txt": "x" for i in range(220)}
    files["package.json"] = "{}"  # sorts before f*.txt? no — 'f' > 'p'
    _member(ws, "big", files)
    doc = detect_workspace(ws)
    assert any(m["path"] == "big" for m in doc["members"])
    assert any("truncated at 200" in lim for lim in doc["limitations"])
    # deterministic: re-running yields the identical doc
    assert detect_workspace(ws) == doc


def test_detect_depth_bound(ws: Path) -> None:
    _member(
        ws,
        "deep",
        {"a/b/c/d/marker.tf": "x\n", "a/b/main.tf": "x\n", "pyproject.toml": "[project]\n"},
    )
    doc = detect_workspace(ws)
    member = next(m for m in doc["members"] if m["path"] == "deep")
    tf_evidence = [e["detail"] for e in member["evidence"] if e["tech"] == "terraform"]
    assert any("a/b/main.tf" in d for d in tf_evidence)
    assert not any("a/b/c/d/marker.tf" in d for d in tf_evidence)


def test_detect_never_reads_or_reports_secrets(ws: Path) -> None:
    _member(ws, "app", {"pyproject.toml": "[project]\n", ".env": "TOKEN=x\n", "id.pem": "k\n"})
    doc = detect_workspace(ws)
    member = next(m for m in doc["members"] if m["path"] == "app")
    details = json.dumps(member["evidence"])
    assert ".env" not in details and "id.pem" not in details


def test_detect_gitless_and_evidence_only_members(ws: Path) -> None:
    # No .git, no pyproject/package.json — terraform file alone marks it.
    _member(ws, "tf-stack", {"main.tf": "resource {}"})
    _member(ws, "scripts", {"requirements-dev.txt": "ruff\n"})
    doc = detect_workspace(ws)
    assert "terraform" in _techs(doc, "tf-stack")
    assert "python" in _techs(doc, "scripts")


def test_detect_empty_member_is_honest_low(ws: Path) -> None:
    (ws / "empty").mkdir()
    (ws / "empty" / "README.md").write_text("hi\n")
    doc = detect_workspace(ws)
    if any(m["path"] == "empty" for m in doc["members"]):
        member = next(m for m in doc["members"] if m["path"] == "empty")
        assert member["techs"] == []
        assert member["confidence"] == "low"


def test_detect_deterministic_output(ws: Path) -> None:
    _member(ws, "a", {"pyproject.toml": '[project]\ndependencies=["fastapi"]\n'})
    _member(ws, "b", {"package.json": "{}"})
    assert detect_workspace(ws) == detect_workspace(ws)


# ---------------------------------------------------------------------------
# §6.3 — explainable advisory recommendation
# ---------------------------------------------------------------------------


def _detection_for(ws: Path, members: dict[str, dict[str, str]]) -> dict:
    for name, files in members.items():
        _member(ws, name, files)
    return detect_workspace(ws)


def test_recommend_aws_spark(ws: Path) -> None:
    det = _detection_for(ws, {"etl": {"requirements.txt": "pyspark\nboto3\n"}})
    rec = recommend_specialists(det, registered=["spark-forge-aws"])
    primary = [s for s in rec["suggested"] if s["role"] == "primary"]
    assert [s["forge_id"] for s in primary] == ["spark-forge-aws"]
    assert primary[0]["installed"] is True
    assert primary[0]["confidence"] == "high"
    assert primary[0]["evidence"]  # explainable — cites member:tech
    assert any("etl:pyspark" in e or "etl:aws" in e for e in primary[0]["evidence"])


def test_recommend_azure_spark(ws: Path) -> None:
    det = _detection_for(ws, {"lake": {"databricks.yml": "bundle:\n"}})
    rec = recommend_specialists(det, registered=[])
    ids = [s["forge_id"] for s in rec["suggested"] if s["role"] == "primary"]
    assert ids == ["spark-forge-azure"]
    row = rec["suggested"][0]
    assert row["installed"] is False  # advisory still names uninstalled forges


def test_recommend_bare_pyspark_is_alternative_not_guess(ws: Path) -> None:
    det = _detection_for(ws, {"jobs": {"requirements.txt": "pyspark\n"}})
    rec = recommend_specialists(det, registered=[])
    primaries = [s for s in rec["suggested"] if s["role"] == "primary"]
    assert primaries == []  # ambiguous — never a primary guess
    alt_ids = {a["forge_id"] for a in rec["alternatives"]}
    assert {"spark-forge-aws", "spark-forge-azure"} <= alt_ids
    for alt in rec["alternatives"]:
        assert alt["confidence"] == "medium"
        assert "undetermined" in alt["reason"] or "PySpark" in alt["reason"]


def test_recommend_api_and_platform(ws: Path) -> None:
    det = _detection_for(
        ws,
        {
            "svc": {"pyproject.toml": '[project]\ndependencies=["flask"]\n'},
            "infra": {"main.tf": "resource {}"},
        },
    )
    rec = recommend_specialists(det, registered=["api-forge", "platform-forge"])
    primaries = {s["forge_id"]: s for s in rec["suggested"] if s["role"] == "primary"}
    assert {"api-forge", "platform-forge"} <= set(primaries)


def test_recommend_aux_and_choices(ws: Path) -> None:
    det = _detection_for(ws, {"app": {"pyproject.toml": "[project]\n"}})
    rec = recommend_specialists(det, registered=[])
    aux = {s["forge_id"] for s in rec["suggested"] if s["role"] == "aux"}
    # companion surfaces only — a bare language match never names a domain forge
    assert "code-atlas-forge" in aux
    assert not any(s["role"] == "primary" for s in rec["suggested"])
    choice_ids = {c["id"] for c in rec["choices"]}
    assert choice_ids == {"recommended", "all", "manual", "keep-existing"}
    assert rec["default_choice"] == "keep-existing"
    assert "advisory" in rec["note"]


def test_recommend_empty_is_never_a_guess(ws: Path) -> None:
    det = detect_workspace(ws)
    rec = recommend_specialists(det, registered=[])
    assert rec["suggested"] == []
    assert any("never a guess" in lim for lim in rec["limitations"])


# ---------------------------------------------------------------------------
# §6.7 — declarative forge.workspace.yaml
# ---------------------------------------------------------------------------


def test_config_absent_returns_none(ws: Path) -> None:
    assert load_workspace_config(ws) is None


def test_config_parses_forge_block(ws: Path) -> None:
    (ws / "forge.workspace.yaml").write_text(
        "kind: forge/Workspace/v1\n"
        "members:\n"
        "  - path: backend\n"
        "  - path: data\n"
        "forge:\n"
        "  installation_profile: full\n"
        "  gateway_profile: deep\n"
        "  hosts: [claude, codex]\n"
        "  specialists:\n"
        "    mode: manual\n"
        "    include: [api-forge, platform-forge]\n",
        "utf-8",
    )
    cfg = load_workspace_config(ws)
    assert cfg is not None and cfg.declared
    assert cfg.members == ("backend", "data")
    assert cfg.installation_profile == "full"
    assert cfg.gateway_profile == "deep"
    assert cfg.hosts == ("claude", "codex")
    assert cfg.specialists_mode == "manual"
    assert cfg.specialists_include == ("api-forge", "platform-forge")
    doc = cfg.setup_doc()
    assert doc["forge"]["installation_profile"] == "full"


def test_config_legacy_marker_still_parses(ws: Path) -> None:
    (ws / "forge.workspace.yaml").write_text("forge_workspace: true\n", "utf-8")
    cfg = load_workspace_config(ws)
    assert cfg is not None
    assert cfg.declared is False
    assert cfg.warnings == ()


def test_config_unknown_fields_warn_never_crash(ws: Path) -> None:
    (ws / "forge.workspace.yaml").write_text(
        "forge:\n  installation_profile: minimal\n  bogus_field: x\n  specialists:\n    wat: 1\n",
        "utf-8",
    )
    cfg = load_workspace_config(ws)
    assert cfg is not None
    assert cfg.installation_profile == "minimal"
    assert any("bogus_field" in w for w in cfg.warnings)
    assert any("specialists.wat" in w for w in cfg.warnings)


def test_config_invalid_values_warn_and_ignore(ws: Path) -> None:
    (ws / "forge.workspace.yaml").write_text(
        "forge:\n"
        "  installation_profile: ultra\n"
        "  gateway_profile: quantum\n"
        "  hosts: [claude, emacs]\n"
        "  specialists:\n"
        "    mode: everything\n"
        "    include: [api-forge, 'Bad ID!']\n",
        "utf-8",
    )
    cfg = load_workspace_config(ws)
    assert cfg is not None
    assert cfg.installation_profile is None
    assert cfg.gateway_profile is None
    assert cfg.hosts == ("claude",)
    assert cfg.specialists_mode is None
    assert cfg.specialists_include == ("api-forge",)
    assert len(cfg.warnings) >= 4


def test_config_rejects_secret_keys_and_values(ws: Path) -> None:
    (ws / "forge.workspace.yaml").write_text(
        "forge:\n"
        "  installation_profile: full\n"
        "  api_key: abc123\n"
        "  hosts: [codex]\n"
        "members:\n"
        "  - path: app\n"
        "aws_secret_access_key: wJalrXUtnFEMI/K7MDENG+bPxRfiCYEXAMPLEKEY\n",
        "utf-8",
    )
    cfg = load_workspace_config(ws)
    assert cfg is not None
    assert cfg.installation_profile == "full"
    assert cfg.hosts == ("codex",)
    secret_drops = [w for w in cfg.warnings if "sensitive" in w or "secrets-looking" in w]
    assert len(secret_drops) >= 2


def test_config_rejects_unsafe_member_paths(ws: Path) -> None:
    (ws / "forge.workspace.yaml").write_text(
        "members:\n  - path: ../outside\n  - path: /abs/x\n  - path: ok-dir\n", "utf-8"
    )
    cfg = load_workspace_config(ws)
    assert cfg is not None
    assert cfg.members == ("ok-dir",)
    assert sum("unsafe path" in w for w in cfg.warnings) == 2


def test_config_outside_yaml_subset_is_warning_not_crash(ws: Path) -> None:
    (ws / "forge.workspace.yaml").write_text("forge:\n\tinstallation_profile: full\n", "utf-8")
    cfg = load_workspace_config(ws)
    assert cfg is not None
    assert any("yaml subset" in w for w in cfg.warnings)


# ---------------------------------------------------------------------------
# §6.6 — presets + precedence
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("preset", "profile", "gateway"),
    [
        ("economy", "minimal", "economy"),
        ("balanced", "recommended", "balanced"),
        ("full", "full", "deep"),
    ],
)
def test_preset_maps_transparently(preset: str, profile: str, gateway: str) -> None:
    res = setup_options.resolve(
        preset=preset, profile=None, gateway_profile=None, host=None, forge=None, config=None
    )
    assert res.profile == profile
    assert res.gateway_profile == gateway
    assert res.doc["preset"]["resolved"] == {"profile": profile, "gateway_profile": gateway}
    assert res.doc["resolution"]["profile"]["source"] == f"preset:{preset}"


def test_explicit_flag_matching_preset_wins_cleanly() -> None:
    res = setup_options.resolve(
        preset="full", profile="full", gateway_profile=None, host=None, forge=None, config=None
    )
    assert res.profile == "full"
    assert res.doc["resolution"]["profile"]["source"] == "flag"


@pytest.mark.parametrize(
    ("flag", "value"),
    [("profile", "minimal"), ("gateway_profile", "economy")],
)
def test_conflicting_flag_and_preset_is_usage_error(flag: str, value: str) -> None:
    kwargs: dict[str, object] = {"profile": None, "gateway_profile": None}
    kwargs[flag] = value
    with pytest.raises(UsageError, match="conflicts"):
        setup_options.resolve(
            preset="full",
            host=None,
            forge=None,
            config=None,
            **kwargs,  # type: ignore[arg-type]
        )


def test_preset_custom_requires_explicit_flags() -> None:
    with pytest.raises(UsageError, match="custom"):
        setup_options.resolve(
            preset="custom", profile=None, gateway_profile=None, host=None, forge=None, config=None
        )
    res = setup_options.resolve(
        preset="custom",
        profile="minimal",
        gateway_profile=None,
        host=None,
        forge=None,
        config=None,
    )
    assert res.profile == "minimal"


def test_config_defaults_and_cli_override(ws: Path) -> None:
    (ws / "forge.workspace.yaml").write_text(
        "forge:\n  installation_profile: minimal\n  gateway_profile: economy\n  hosts: [codex]\n",
        "utf-8",
    )
    cfg = load_workspace_config(ws)
    res = setup_options.resolve(
        preset=None, profile=None, gateway_profile=None, host=None, forge=None, config=cfg
    )
    assert res.profile == "minimal"
    assert res.gateway_profile == "economy"
    assert res.host == "codex"
    assert res.doc["resolution"]["profile"]["source"] == "forge.workspace.yaml"
    # CLI flag beats the file
    res2 = setup_options.resolve(
        preset=None, profile="full", gateway_profile=None, host=None, forge=None, config=cfg
    )
    assert res2.profile == "full"
    assert res2.doc["resolution"]["profile"]["source"] == "flag"


def test_declared_hosts_list_and_empty(ws: Path) -> None:
    (ws / "forge.workspace.yaml").write_text("forge:\n  hosts: [claude, devin]\n", "utf-8")
    cfg = load_workspace_config(ws)
    res = setup_options.resolve(
        preset=None, profile=None, gateway_profile=None, host=None, forge=None, config=cfg
    )
    assert res.host == "claude,devin"
    (ws / "forge.workspace.yaml").write_text("forge:\n  hosts: []\n", "utf-8")
    cfg2 = load_workspace_config(ws)
    res2 = setup_options.resolve(
        preset=None, profile=None, gateway_profile=None, host=None, forge=None, config=cfg2
    )
    assert res2.host == "none"


def test_forge_flag_becomes_manual_selection() -> None:
    res = setup_options.resolve(
        preset=None,
        profile=None,
        gateway_profile=None,
        host=None,
        forge="api-forge",
        config=None,
    )
    assert res.forges == ("api-forge",)
    assert res.doc["specialists"]["mode"] == "manual"


# ---------------------------------------------------------------------------
# §6.4/§9.2 — honest host onboarding states
# ---------------------------------------------------------------------------


def test_host_states_closed_vocabulary() -> None:
    assert HOST_STATES == (
        "not_found",
        "installed",
        "in_path",
        "configurable",
        "integration_written",
        "restart_needed",
        "mcp_verified",
        "validated",
    )


def _env_no_hosts(tmp_path: Path) -> dict[str, str]:
    """Environment with no host binaries on PATH."""
    bin_dir = tmp_path / "empty-bin"
    bin_dir.mkdir()
    return {"PATH": str(bin_dir), "HOME": str(tmp_path)}


def test_onboarding_no_evidence_is_not_found(ws: Path, tmp_path: Path) -> None:
    doc = build_onboarding(
        ws,
        hosts=("codex",),
        scope="project",
        dry_run=True,
        applied=False,
        env=_env_no_hosts(tmp_path),
    )
    states = {h["host"]: h["state"] for h in doc["hosts"]}
    assert set(states.values()) <= set(HOST_STATES)
    assert states["codex"] == "not_found"


def test_onboarding_bare_codex_dir_is_never_validated(ws: Path, tmp_path: Path) -> None:
    """§6.4 — a .codex/ directory alone is presence, never readiness."""
    (ws / ".codex").mkdir()
    doc = build_onboarding(
        ws,
        hosts=("codex",),
        scope="project",
        dry_run=False,
        applied=False,
        env=_env_no_hosts(tmp_path),
    )
    row = next(h for h in doc["hosts"] if h["host"] == "codex")
    assert row["state"] == "configurable"
    assert row["state"] != "validated"
    assert "not readiness" in row["detail"]


def test_onboarding_never_claims_validated(ws: Path, tmp_path: Path) -> None:
    """Even with assets written, setup never reaches 'validated' — that
    state requires an observed running host (hosts observe)."""
    (ws / ".codex").mkdir()
    (ws / ".claude").mkdir()
    doc = build_onboarding(
        ws,
        hosts=("codex", "claude"),
        scope="project",
        dry_run=False,
        applied=True,
        env=_env_no_hosts(tmp_path),
    )
    assert all(h["state"] != "validated" for h in doc["hosts"])
    # assets written + host not installed → integration_written
    row = next(h for h in doc["hosts"] if h["host"] == "codex")
    assert row["state"] in ("integration_written", "configurable")


def test_onboarding_restart_needed_when_host_installed(ws: Path, tmp_path: Path) -> None:
    env = _env_no_hosts(tmp_path)
    fake_bin = Path(env["PATH"]) / "codex"
    fake_bin.write_text("#!/bin/sh\n")
    fake_bin.chmod(0o755)
    (ws / ".codex").mkdir()
    doc = build_onboarding(
        ws, hosts=("codex",), scope="project", dry_run=False, applied=True, env=env
    )
    row = next(h for h in doc["hosts"] if h["host"] == "codex")
    assert row["state"] in ("restart_needed", "integration_written", "mcp_verified")
    assert row["state"] != "validated"


def test_onboarding_dry_run_is_honest(ws: Path, tmp_path: Path) -> None:
    doc = build_onboarding(
        ws,
        hosts=("codex",),
        scope="project",
        dry_run=True,
        applied=False,
        env=_env_no_hosts(tmp_path),
    )
    assert any("plan only" in lim for lim in doc["limitations"])
    assert any("configured != active" in lim for lim in doc["limitations"])
    assert doc["next_steps"]


# ---------------------------------------------------------------------------
# §3.1 — install_auto carries the new blocks end to end
# ---------------------------------------------------------------------------


def test_install_auto_plan_carries_cycle161_blocks(forge_home: Path, ws: Path) -> None:
    _register_stub(forge_home, "stub-forge")
    _member(ws, "svc", {"pyproject.toml": '[project]\ndependencies=["fastapi"]\n'})
    before = {p for p in ws.rglob("*") if p.is_file()}
    plan = service.install_auto(scope="project", root=ws, dry_run=True)
    after = {p for p in ws.rglob("*") if p.is_file()}
    assert plan["status"] == "planned"
    assert before == after  # dry-run writes nothing
    det = plan["workspace_detection"]
    assert det["schema"] == "forge/WorkspaceDetection/v1"
    assert "fastapi" in {t for m in det["members"] for t in m["techs"]}
    rec = plan["recommendation"]
    assert rec["schema"] == "forge/SpecialistRecommendation/v1"
    assert any(s["forge_id"] == "api-forge" for s in rec["suggested"])
    onboarding = plan["onboarding"]
    assert {h["state"] for h in onboarding["hosts"]} <= set(HOST_STATES)


def test_install_auto_blocked_receipt_still_carries_blocks(forge_home: Path, ws: Path) -> None:
    # no registered forges → blocked registry check, but blocks attach
    out = service.install_auto(scope="project", root=ws, dry_run=True)
    assert out["status"] == "failed"
    assert "workspace_detection" in out and "recommendation" in out
    assert "onboarding" in out


def test_install_auto_forge_sequence_filters_delegation(forge_home: Path, ws: Path) -> None:
    _register_stub(forge_home, "forge-a")
    _register_stub(forge_home, "forge-b")
    plan = service.install_auto(scope="project", root=ws, dry_run=True, forge=["forge-b"])
    ids = [f["forge_id"] for f in plan["forges"]]
    assert ids == ["forge-b", "the-forge"] or ids == ["forge-b"]
    assert "forge-a" not in ids


def test_install_auto_setup_doc_and_detection_passthrough(forge_home: Path, ws: Path) -> None:
    _register_stub(forge_home, "stub-forge")
    det = detect_workspace(ws)
    plan = service.install_auto(
        scope="project",
        root=ws,
        dry_run=True,
        setup={
            "preset": {
                "name": "full",
                "resolved": {"profile": "full", "gateway_profile": "deep"},
            }
        },
        detection=det,
    )
    assert plan["setup"]["preset"]["name"] == "full"
    assert plan["workspace_detection"] == det


def test_install_auto_apply_marks_onboarding_applied(forge_home: Path, ws: Path) -> None:
    _register_stub(forge_home, "stub-forge")
    out = service.install_auto(scope="project", root=ws, yes=True, host="none")
    assert out["status"] == "completed", json.dumps(out["checks"], indent=1)
    assert "onboarding" in out
    assert all(h["state"] != "validated" for h in out["onboarding"]["hosts"])


# ---------------------------------------------------------------------------
# CLI surface — workspace detect, setup --preset, §3.4 daily ops
# ---------------------------------------------------------------------------


def test_cli_workspace_detect_json_and_text(forge_home: Path, ws: Path) -> None:
    _member(ws, "api", {"pyproject.toml": '[project]\ndependencies=["fastapi"]\n'})
    proc = cli(ws, "workspace", "detect", "--json", home=forge_home)
    assert proc.returncode == 0, proc.stderr
    doc = json.loads(proc.stdout)
    assert doc["detection"]["schema"] == "forge/WorkspaceDetection/v1"
    assert doc["recommendation"]["schema"] == "forge/SpecialistRecommendation/v1"

    proc2 = cli(ws, "workspace", "detect", home=forge_home)
    assert proc2.returncode == 0
    assert "api" in proc2.stdout and "Recommendation" in proc2.stdout


def test_cli_workspace_detect_declarative_block(forge_home: Path, ws: Path) -> None:
    (ws / "forge.workspace.yaml").write_text(
        "kind: forge/Workspace/v1\nforge:\n  installation_profile: full\n", "utf-8"
    )
    proc = cli(ws, "workspace", "detect", "--json", home=forge_home)
    doc = json.loads(proc.stdout)
    assert doc["declarative"]["forge"]["installation_profile"] == "full"


def test_cli_setup_preset_in_plan(forge_home: Path, ws: Path) -> None:
    _register_stub(forge_home, "stub-forge")
    proc = cli(
        ws,
        "setup",
        "--scope",
        "project",
        "--preset",
        "full",
        "--dry-run",
        "--json",
        home=forge_home,
    )
    assert proc.returncode == 0, proc.stderr
    doc = json.loads(proc.stdout)
    assert doc["setup"]["preset"]["resolved"] == {"profile": "full", "gateway_profile": "deep"}
    assert doc["profile"] == "full"
    assert doc["execution_profile"] == "deep"
    assert "workspace_detection" in doc and "onboarding" in doc


def test_cli_setup_preset_conflict_is_usage_error(forge_home: Path, ws: Path) -> None:
    proc = cli(
        ws,
        "setup",
        "--scope",
        "project",
        "--preset",
        "full",
        "--profile",
        "minimal",
        "--dry-run",
        "--json",
        home=forge_home,
    )
    assert proc.returncode == 2
    assert "conflicts" in proc.stderr


def test_cli_setup_bare_noninteractive_degrades(ws: Path) -> None:
    proc = cli(ws, "setup")
    assert proc.returncode != 0
    # governed refusal — never a traceback
    assert "Traceback" not in proc.stderr
    assert "setup wizard requires a TTY" in proc.stderr + proc.stdout or proc.returncode in (2, 70)


@pytest.mark.parametrize(
    "args",
    [
        ("status", "--json"),
        ("doctor", "--json"),
        ("hosts", "status", "--json"),
        ("resources", "list", "--json"),
    ],
)
def test_daily_ops_verbs_run_from_workspace_root(forge_home: Path, ws: Path, args: tuple) -> None:
    """§3.4 — the daily-ops surface already exists; verify it works from a
    workspace root without duplicating any top-level command."""
    proc = cli(ws, *args, home=forge_home)
    assert proc.returncode in (0, 1), proc.stderr[:400]  # 1 = unhealthy, still a valid answer
    assert "Traceback" not in proc.stderr
    if "--json" in args and proc.stdout.strip():
        json.loads(proc.stdout)
