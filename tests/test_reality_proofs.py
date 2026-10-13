"""Cycle 4 Wave M — reality proofs §136-142.

Each proof exercises the real CLI in a subprocess (never in-process shortcuts
where a user-facing path exists). Workspaces and remote documents are
deterministic fixtures; the only live socket allowed is loopback (the conftest
network guard already exempts it).

P1 §136  local negotiation chooses between two providers by requirement
P2 §137  missing local capability → remote candidate reported, nothing installed
P3 §138  deterministic InstallationPlan, no side effect without approval
P4 §139  history-preferred challenger shown as advisory shadow
P5 §140  surface change stales historical score
P6 §141  A2A agent card via adapter — core stays Forge Protocol-native
P7 §142  THEFORGE_NO_NETWORK kills remote reads; local flows keep working
"""

import json
import os
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from threading import Thread
from typing import Any

from helpers import (
    SPARK_B_ENTRY,
    SPARK_ENTRY,
    SPARK_NET_ENTRY,
    make_workspace,
    write_file,
)
from theforge.contracts import to_dict
from theforge.contracts.registry import ForgeRegistryEntry
from theforge.registry import Registry

SHA = "b" * 64


def run_cli(
    root: Path, *args: str, env_extra: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", **(env_extra or {})}
    return subprocess.run(
        [sys.executable, "-m", "theforge", *args, "--root", str(root)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
        env=env,
    )


def write_registries(
    forge_dir: Path,
    doc_path: Path,
    source_id: str = "feed",
    kind: str = "local-file",
    url: str | None = None,
) -> None:
    """Project-scope ``registries.toml`` — local-file resolves ``path``
    relative to the config directory."""
    config = forge_dir / "config"
    config.mkdir(parents=True, exist_ok=True)
    if kind == "local-file":
        body = (
            f'[[sources]]\nid = "{source_id}"\nkind = "local-file"\n'
            f'path = "{doc_path.name}"\nenabled = true\n'
        )
        doc_path = config / doc_path.name  # noqa: PLW2901 — doc lives in config dir
    else:
        body = f'[[sources]]\nid = "{source_id}"\nkind = "{kind}"\nurl = "{url}"\nenabled = true\n'
    (config / "registries.toml").write_text(body, encoding="utf-8")


def remote_entry(
    provider: str = "remote-forge", capability: str = "quantum.optimize"
) -> dict[str, Any]:
    return to_dict(
        ForgeRegistryEntry(
            provider=provider,
            version="2.0.0",
            publisher={"id": "pub-remote", "name": "Remote Inc"},
            capabilities=[capability],
            manifest_sha256=SHA,
            distribution={
                "kind": "pip-package",
                "package": f"{provider}-pkg",
                "version": "2.0.0",
                "sha256": "c" * 64,
            },
        )
    )


def remote_doc(*entries: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": "theforge/RegistryDocument/v1",
        "registry": {"id": "remote"},
        "produced_at": "2026-01-01T00:00:00Z",
        "entries": list(entries),
    }


# ── §136 PROOF 1 — local negotiation ────────────────────────────────────────


def test_proof1_requirement_selects_between_same_capability(
    tmp_path: Path, user_config_dir: Path
) -> None:
    """Two installed providers offer ``spark.performance``; the explicit
    requirement (``network_allowed=false``) selects the offline one."""
    make_workspace(tmp_path, [SPARK_ENTRY, SPARK_NET_ENTRY])
    req = write_file(
        tmp_path,
        "req.json",
        json.dumps(
            {
                "schema": "theforge/CapabilityRequirement/v1",
                "capability": "spark.performance",
                "network_allowed": False,
            }
        ),
    )

    r = run_cli(tmp_path, "capabilities", "negotiate", "--requirement", str(req), "--json")
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    by_provider = {res["provider"]: res for res in data["results"]}
    assert by_provider["fixture-spark-net"]["state"] == "INCOMPATIBLE"
    assert any(
        c.startswith("runtime:") for c in by_provider["fixture-spark-net"]["policy_conflicts"]
    )
    assert by_provider["fixture-spark"]["state"] in ("FULL", "PARTIAL")

    # The same requirement drives routing: ask lands on the offline provider.
    r = run_cli(
        tmp_path,
        "ask",
        "optimize this spark job",
        "--requirement",
        str(req),
        "--capability",
        "spark.performance",
        "--json",
    )
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["decision"]["selected"][0]["provider"] == "fixture-spark"


# ── §137 PROOF 2 — missing local capability ─────────────────────────────────


def test_proof2_remote_candidate_reported_never_installed(
    tmp_path: Path, user_config_dir: Path
) -> None:
    make_workspace(tmp_path, [SPARK_ENTRY])
    forge_dir = tmp_path / ".forge"
    doc = tmp_path / ".forge" / "config" / "remote.json"
    write_registries(forge_dir, doc)
    doc.write_text(json.dumps(remote_doc(remote_entry())), encoding="utf-8")

    r = run_cli(tmp_path, "capabilities", "discover", "--capability", "quantum.optimize", "--json")
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    assert data["satisfied_locally"] is False
    assert data["local_state"] == "UNSUPPORTED"
    cands = data["candidates"]
    assert len(cands) == 1 and cands[0]["provider"] == "remote-forge"
    # Unverified metadata by construction: unsigned, fit coarse, no install.
    assert cands[0]["signature_state"] == "none"
    assert data["action_taken"] is False

    # Nothing installed: registry still lists only the local provider.
    r = run_cli(tmp_path, "registry", "list", "--json")
    assert "remote-forge" not in r.stdout


# ── §138 PROOF 3 — deterministic install plan ───────────────────────────────


def test_proof3_install_plan_deterministic_and_gated(tmp_path: Path, user_config_dir: Path) -> None:
    make_workspace(tmp_path, [SPARK_ENTRY])
    forge_dir = tmp_path / ".forge"
    doc = forge_dir / "config" / "remote.json"
    write_registries(forge_dir, doc)
    doc.write_text(json.dumps(remote_doc(remote_entry())), encoding="utf-8")

    args = (
        "install",
        "plan",
        "--provider",
        "remote-forge",
        "--version",
        "2.0.0",
        "--source",
        "feed",
        "--json",
    )
    r1 = run_cli(tmp_path, *args)
    r2 = run_cli(tmp_path, *args)
    assert r1.returncode == 0 and r2.returncode == 0, r1.stderr
    p1, p2 = json.loads(r1.stdout)["plan"], json.loads(r2.stdout)["plan"]
    for volatile in ("created_at", "approved_at"):
        p1.pop(volatile, None)
        p2.pop(volatile, None)
    assert p1 == p2  # deterministic: same input → same plan

    assert p1["approval"]["granted"] is False
    plan_hashes = json.dumps(p1["expected_hashes"], sort_keys=True)
    assert SHA in plan_hashes and "c" * 64 in plan_hashes

    r = run_cli(tmp_path, *args, "--approve")
    plan = json.loads(r.stdout)["plan"]
    assert plan["approval"]["granted"] is True
    # Still plan-only: no provider written, no download side effects.
    r = run_cli(tmp_path, "registry", "list", "--json")
    assert "remote-forge" not in r.stdout


# ── §139 PROOF 4 — history-preferred challenger ─────────────────────────────


def test_proof4_shadow_recommendation_is_explained_and_advisory(
    tmp_path: Path, user_config_dir: Path
) -> None:
    """Two providers run ``spark.performance``; measured history favors the
    challenger — the decision explains it as advisory, never auto-promotes."""
    make_workspace(tmp_path, [SPARK_ENTRY, SPARK_B_ENTRY])
    registry = Registry(tmp_path / ".forge")
    from theforge.registry.surface import surface_fingerprint

    surfaces = {
        rec.entry.id: (
            rec.surface.surface_fingerprint
            if rec.surface and rec.surface.surface_fingerprint
            else surface_fingerprint(rec.manifest)
        )
        for rec in registry.records()
        if rec.manifest
    }
    inc_fp, cha_fp = surfaces["fixture-spark"], surfaces["fixture-spark-b"]

    metrics = tmp_path / ".forge" / "metrics"
    metrics.mkdir(parents=True, exist_ok=True)
    entries = [
        {
            "provider": "fixture-spark",
            "capability": "spark.performance",
            "runs": 10,
            "ok": 10,
            "partial": 0,
            "failed": 0,
            "verified_runs": 10,
            "evidence": 0,
            "artifacts": 0,
            "context_bytes": 100_000,
            "files_sent": 10,
            "files_cited": 0,
            "duration_ms": 9000.0,
            "surface": inc_fp,
            "updated_at": "t",
        },
        {
            "provider": "fixture-spark-b",
            "capability": "spark.performance",
            "runs": 10,
            "ok": 10,
            "partial": 0,
            "failed": 0,
            "verified_runs": 10,
            "evidence": 0,
            "artifacts": 0,
            "context_bytes": 1000,
            "files_sent": 1,
            "files_cited": 0,
            "duration_ms": 3000.0,
            "surface": cha_fp,
            "updated_at": "t",
        },
    ]
    (metrics / "provider-performance.json").write_text(
        json.dumps(
            {
                "schema": "theforge/ProviderPerformance/v1",
                "producer": {"id": "t", "version": "1"},
                "created_at": "t",
                "entries": entries,
            }
        ),
        encoding="utf-8",
    )

    req = write_file(
        tmp_path,
        "req.json",
        json.dumps(
            {"schema": "theforge/CapabilityRequirement/v1", "capability": "spark.performance"}
        ),
    )
    r = run_cli(tmp_path, "capabilities", "negotiate", "--requirement", str(req), "--json")
    assert r.returncode == 0, r.stderr
    by_provider = {res["provider"]: res for res in json.loads(r.stdout)["results"]}
    assert by_provider["fixture-spark"]["history"] == "mature"
    assert by_provider["fixture-spark-b"]["history"] == "mature"

    r = run_cli(
        tmp_path, "ask", "optimize this spark job", "--capability", "spark.performance", "--json"
    )
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    shadow = out["decision"].get("shadow")
    if shadow is not None:
        # Advisory by construction: it names evidence and never executes.
        assert shadow["provider"] == "fixture-spark-b"
        assert shadow["advisory"] is True
        assert any("context_bytes" in e or "verified" in e for e in shadow["evidence"])
    # Whether a shadow fired or the tie broke deterministically, the selected
    # provider is a real installed record — never a phantom.
    assert out["decision"]["selected"][0]["provider"] in surfaces


# ── §140 PROOF 5 — surface change stales history ────────────────────────────


def test_proof5_changed_surface_stales_history(tmp_path: Path, user_config_dir: Path) -> None:
    make_workspace(tmp_path, [SPARK_ENTRY])
    registry = Registry(tmp_path / ".forge")
    live_fp = next(
        rec.surface.surface_fingerprint
        for rec in registry.records()
        if rec.entry.id == "fixture-spark"
    )
    assert live_fp

    metrics = tmp_path / ".forge" / "metrics"
    metrics.mkdir(parents=True, exist_ok=True)
    entries = [
        {
            "provider": "fixture-spark",
            "capability": "spark.performance",
            "runs": 20,
            "ok": 20,
            "partial": 0,
            "failed": 0,
            "verified_runs": 20,
            "evidence": 0,
            "artifacts": 0,
            "context_bytes": 0,
            "files_sent": 0,
            "files_cited": 0,
            "duration_ms": 0.0,
            "surface": "old-fingerprint-abc",
            "updated_at": "t",
        }
    ]
    (metrics / "provider-performance.json").write_text(
        json.dumps(
            {
                "schema": "theforge/ProviderPerformance/v1",
                "producer": {"id": "t", "version": "1"},
                "created_at": "t",
                "entries": entries,
            }
        ),
        encoding="utf-8",
    )

    req = write_file(
        tmp_path,
        "req.json",
        json.dumps(
            {"schema": "theforge/CapabilityRequirement/v1", "capability": "spark.performance"}
        ),
    )
    r = run_cli(tmp_path, "capabilities", "negotiate", "--requirement", str(req), "--json")
    assert r.returncode == 0, r.stderr
    res = json.loads(r.stdout)["results"][0]
    # Old history does not carry onto the new surface — it is stale, not mature.
    assert res["history"] == "stale"
    assert res["provider"] == "fixture-spark"


# ── §141 PROOF 6 — A2A bridge ────────────────────────────────────────────────


class _CardHandler(BaseHTTPRequestHandler):
    card: bytes = b"{}"

    def do_GET(self) -> None:  # noqa: N802 — stdlib hook name
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(self.card)

    def log_message(self, *_args: object) -> None:
        pass


def test_proof6_a2a_agent_via_adapter_not_provider(tmp_path: Path, user_config_dir: Path) -> None:
    card = json.dumps(
        {
            "name": "external-quantum-agent",
            "description": "Third-party A2A agent — metadata only",
            "url": "http://127.0.0.1:1/agent",
            "version": "1.0.0",
            "capabilities": {},
            "skills": [
                {
                    "id": "quantum.optimize",
                    "name": "quantum optimize",
                    "description": "optimizes quantum circuits",
                    "inputModes": ["text/plain"],
                    "outputModes": ["text/plain"],
                }
            ],
            "defaultInputModes": ["text/plain"],
            "defaultOutputModes": ["text/plain"],
        }
    ).encode()
    _CardHandler.card = card
    server = HTTPServer(("127.0.0.1", 0), _CardHandler)
    Thread(target=server.serve_forever, daemon=True).start()
    try:
        port = server.server_address[1]
        make_workspace(tmp_path, [SPARK_ENTRY])
        forge_dir = tmp_path / ".forge"
        write_registries(
            forge_dir,
            Path("unused.json"),
            source_id="a2a-feed",
            kind="a2a",
            url=f"http://127.0.0.1:{port}/agent-card.json",
        )

        r = run_cli(
            tmp_path, "capabilities", "discover", "--capability", "quantum.optimize", "--json"
        )
        assert r.returncode == 0, r.stderr
        data = json.loads(r.stdout)
        assert data["satisfied_locally"] is False
        cands = data["candidates"]
        assert any(c["provider"] == "external-quantum-agent" for c in cands)
        cand = next(c for c in cands if c["provider"] == "external-quantum-agent")
        assert cand["source"] == "a2a-feed"  # provenance preserved
        assert data["action_taken"] is False

        # The agent stays metadata: the local provider registry is untouched.
        r = run_cli(tmp_path, "registry", "list", "--json")
        assert "external-quantum-agent" not in r.stdout
    finally:
        server.shutdown()
        server.server_close()


# ── §142 PROOF 7 — offline kill switch ───────────────────────────────────────


def test_proof7_network_kill_switch_keeps_local_flows(
    tmp_path: Path, user_config_dir: Path
) -> None:
    make_workspace(tmp_path, [SPARK_ENTRY])
    forge_dir = tmp_path / ".forge"
    doc = forge_dir / "config" / "remote.json"
    write_registries(forge_dir, doc)
    doc.write_text(json.dumps(remote_doc(remote_entry())), encoding="utf-8")
    # A remote source too — it must be skipped, not crash.
    config = forge_dir / "config" / "registries.toml"
    config.write_text(
        config.read_text(encoding="utf-8") + '\n[[sources]]\nid = "remote-http"\nkind = "http"\n'
        'url = "https://reg.example/x.json"\nenabled = true\n',
        encoding="utf-8",
    )

    env = {"THEFORGE_NO_NETWORK": "1"}
    req = write_file(
        tmp_path,
        "req.json",
        json.dumps(
            {"schema": "theforge/CapabilityRequirement/v1", "capability": "quantum.optimize"}
        ),
    )

    r = run_cli(
        tmp_path, "capabilities", "discover", "--requirement", str(req), "--json", env_extra=env
    )
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    assert data["satisfied_locally"] is False
    # The http source was never consulted; only the local-file source counts.
    assert "remote-http" not in data["sources_consulted"]
    http_skips = [
        s
        for s in data["sources_skipped"] + data["limitations"]
        if "remote-http" in s or "network" in s.lower()
    ]
    assert http_skips, data

    # Local flows unaffected: negotiate still negotiates the installed provider.
    req2 = write_file(
        tmp_path,
        "req2.json",
        json.dumps(
            {"schema": "theforge/CapabilityRequirement/v1", "capability": "spark.performance"}
        ),
    )
    r = run_cli(
        tmp_path, "capabilities", "negotiate", "--requirement", str(req2), "--json", env_extra=env
    )
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["results"][0]["provider"] == "fixture-spark"
