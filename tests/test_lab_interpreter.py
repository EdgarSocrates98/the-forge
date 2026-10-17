"""Forge Lab interpreter resolution tests (cyc11.2 P1-005).

The collector must pick the interpreter that actually has the
specialist's extras — fixed authority order — and report honest states:
PASS/FAIL/SKIPPED/BLOCKED/ERROR, never SKIPPED→PASS. Matrix per spec:
no extras / with extras / incompatible python / missing interpreter /
corrupted environment / invalid receipt.
"""

import json
import os
import sys
from pathlib import Path

import pytest

from theforge.contracts.types import Producer
from theforge.lab import (
    _interpreter_version,
    _probe_interpreter,
    _version_satisfies,
    _version_tuple,
    collect,
    resolve_interpreter,
    write_report,
)

PRODUCER = Producer(id="theforge", version="test")


def _repo(tmp_path: Path, name: str, lab: object = ..., **forge_doc: object) -> Path:
    repo = tmp_path / name
    repo.mkdir()
    doc = {"forge_id": name, "package": name.replace("-", "_")}
    if lab is not ...:
        doc["lab"] = lab
    doc.update(forge_doc)
    (repo / "forge.json").write_text(json.dumps(doc), encoding="utf-8")
    return repo


def _fake_venv(root: Path, name: str, version: str | None = None) -> Path:
    """A fake venv: ``bin/python`` is a real symlink to sys.executable so it
    can actually run labs; ``pyvenv.cfg`` pins the *declared* version."""
    venv = root / name
    bindir = venv / ("Scripts" if os.name == "nt" else "bin")
    bindir.mkdir(parents=True)
    exe = bindir / ("python.exe" if os.name == "nt" else "python")
    try:
        exe.symlink_to(sys.executable)
    except OSError:
        pytest.skip("symlinks unavailable on this platform")
    if version is not None:
        (venv / "pyvenv.cfg").write_text(f"version = {version}\n", encoding="utf-8")
    return venv


def _receipt_home(tmp_path: Path, forge_id: str, doc: object) -> Path:
    """Forge-cli managed receipt home: <home>/.forge-cli/forges/<f>/install.json."""
    home = tmp_path / "cli-home"
    d = home / ".forge-cli" / "forges" / forge_id
    d.mkdir(parents=True)
    if isinstance(doc, (dict, list)):
        (d / "install.json").write_text(json.dumps(doc), encoding="utf-8")
    else:
        (d / "install.json").write_text(str(doc), encoding="utf-8")
    return home


DECL = {
    "command": ["{python}", "fake_lab.py", "--result-out", "{receipt}"],
    "receipt": ".forge/lab-result.json",
    "modes": ["A"],
    "suite": "fake-suite",
    "timeout_s": 30,
}

# Lab that reports per-scenario verdicts by an extras marker next to the
# interpreter's venv (<venv>/.has-extras) — deterministic, offline.
EXTRAS_LAB = """\
import json, sys, pathlib
receipt = pathlib.Path(sys.argv[sys.argv.index("--result-out") + 1])
receipt.parent.mkdir(parents=True, exist_ok=True)
venv = pathlib.Path(sys.executable).parent.parent
has = (venv / ".has-extras").exists()
receipt.write_text(json.dumps({
    "schema": "forge/BenchmarkResult/v1",
    "suite": "fake-suite",
    "forge": "fake-forge",
    "mode": "A",
    "created_at": "2026-10-17T00:00:00Z",
    "producer": {"id": "fake-forge", "version": "0.1.0"},
    "external": False,
    "results": [{"scenario_id": "s-1",
                 "verdict": "pass" if has else "skipped",
                 "detail": "" if has else "extra 'mcp' missing",
                 "metrics": {}, "duration_ms": 1}],
}))
"""


# ---------------------------------------------------------------------------
# version/spec primitives
# ---------------------------------------------------------------------------


def test_version_tuple_and_satisfies():
    assert _version_tuple("3.11.4") == (3, 11, 4)
    assert _version_tuple("3.9") == (3, 9)
    assert _version_tuple("abc") is None
    assert _version_satisfies((3, 11), ">=3.11") is True
    assert _version_satisfies((3, 10, 9), ">=3.11") is False
    assert _version_satisfies((3, 12, 1), ">=3.11,<3.13") is True
    assert _version_satisfies((3, 13, 0), ">=3.11,<3.13") is False
    assert _version_satisfies((3, 11), "garbage") is None


# ---------------------------------------------------------------------------
# authority order
# ---------------------------------------------------------------------------


def test_resolution_priority_order(tmp_path):
    repo = _repo(tmp_path, "prio-forge", DECL)
    bare = _repo(tmp_path, "prio-bare", DECL)  # no .venv — fallback reachable
    explicit_py = _fake_venv(tmp_path, "v-explicit") / "bin" / "python"
    receipt_venv = _fake_venv(tmp_path, "v-receipt")
    home = _receipt_home(tmp_path, "prio-forge", {"venv": str(receipt_venv)})
    manifest_venv = _fake_venv(tmp_path, "v-manifest")
    manifest = {"forge_id": "prio-forge", "venv": str(manifest_venv)}
    spec_env = _fake_venv(repo, ".venv")
    empty = tmp_path / "empty-home"
    cases = [
        (
            dict(checkout=repo, explicit=str(explicit_py), home=home, manifest=manifest),
            ("explicit", str(explicit_py)),
        ),
        (
            dict(checkout=repo, home=home, manifest=manifest),
            ("managed-receipt", str(receipt_venv / "bin" / "python")),
        ),
        (
            dict(checkout=repo, home=empty, manifest=manifest),
            ("manifest", str(manifest_venv / "bin" / "python")),
        ),
        (
            dict(checkout=repo, home=empty),
            ("specialist-env", str(spec_env / "bin" / "python")),
        ),
        (dict(checkout=bare, home=empty), ("fallback", sys.executable)),
    ]
    for kwargs, (source, path) in cases:
        res = resolve_interpreter(forge_id="prio-forge", **kwargs)
        assert (res.source, res.python) == (source, path), (kwargs, res)


def test_managed_receipt_bin_sibling(tmp_path):
    repo = _repo(tmp_path, "sib-forge", DECL)
    venv = _fake_venv(tmp_path, "v-sib")
    fake_bin = venv / "bin" / "sib-forge"
    fake_bin.write_text("#!/bin/sh\n")
    home = _receipt_home(tmp_path, "sib-forge", {"bin": str(fake_bin)})
    res = resolve_interpreter(forge_id="sib-forge", checkout=repo, home=home)
    assert res.source == "managed-receipt"
    assert res.python == str(venv / "bin" / "python")


# ---------------------------------------------------------------------------
# spec-required scenarios
# ---------------------------------------------------------------------------


def test_incompatible_python_rejected(tmp_path):
    repo = _repo(tmp_path, "old-forge", DECL)
    old = _fake_venv(tmp_path, "v-old", version="3.9.0")
    manifest = {
        "forge_id": "old-forge",
        "venv": str(old),
        "python": {"satisfies": ">=3.11"},
    }
    res = resolve_interpreter(
        forge_id="old-forge", checkout=repo, manifest=manifest,
        home=tmp_path / "empty",
    )
    assert res.source == "fallback"  # sys.executable satisfies >=3.11
    rejected = {c.source: c.verdict for c in res.rejected}
    assert "does not satisfy '>=3.11'" in rejected["manifest"]


def test_all_candidates_rejected_blocks(tmp_path):
    repo = _repo(tmp_path, "noble-forge", DECL)
    old = _fake_venv(tmp_path, "v-ancient", version="3.8.0")
    manifest = {
        "forge_id": "noble-forge",
        "venv": str(old),
        "python": {"satisfies": ">=99"},
        "source": {"path": str(repo)},
    }
    res = resolve_interpreter(
        forge_id="noble-forge", checkout=repo, manifest=manifest,
        home=tmp_path / "empty",
    )
    assert res.python is None and res.source == "none"
    outcomes, _ = collect(manifests=[manifest], mode="A",
                          home=tmp_path / "empty")
    (out,) = outcomes
    assert out.forge_id == "noble-forge"
    assert out.status == "blocked" and out.state == "BLOCKED"
    assert out.reason == "no-interpreter"
    assert "does not satisfy" in out.detail


def test_missing_explicit_and_manifest_interpreter(tmp_path):
    repo = _repo(tmp_path, "gone-forge", DECL)
    res = resolve_interpreter(
        forge_id="gone-forge",
        checkout=repo,
        explicit=str(tmp_path / "no-such-python"),
        manifest={"forge_id": "gone-forge",
                  "python": {"executable": str(tmp_path / "gone-python")}},
        home=tmp_path / "empty",
    )
    assert res.source == "fallback"
    verdicts = {c.source: c.verdict for c in res.rejected}
    assert "is not a file" in verdicts["explicit"]
    assert "no interpreter" in verdicts["manifest"]


def test_corrupted_environment_undeterminable_version(tmp_path):
    """venv python exists but cannot prove a version → rejected under a spec."""
    repo = _repo(tmp_path, "corrupt-forge", DECL)
    venv = tmp_path / "broken-venv"
    (venv / "bin").mkdir(parents=True)
    (venv / "bin" / "python").write_text("garbage-not-a-python\n")
    manifest = {
        "forge_id": "corrupt-forge",
        "venv": str(venv),
        "python": {"satisfies": ">=3.11"},
    }
    res = resolve_interpreter(
        forge_id="corrupt-forge", checkout=repo, manifest=manifest,
        home=tmp_path / "empty",
    )
    assert res.source == "fallback"
    rejected = {c.source: c.verdict for c in res.rejected}
    assert "undeterminable" in rejected["manifest"]


def test_invalid_managed_receipt_warns_and_falls_through(tmp_path):
    repo = _repo(tmp_path, "badreceipt-forge", DECL)
    home = _receipt_home(tmp_path, "badreceipt-forge", "{corrupt json")
    res = resolve_interpreter(forge_id="badreceipt-forge", checkout=repo, home=home)
    assert res.source == "fallback"
    assert any("unreadable" in w for w in res.warnings)
    rejected = {c.source: c.verdict for c in res.rejected}
    assert "managed-receipt" in rejected


def test_receipt_venv_missing_interpreter_warns(tmp_path):
    repo = _repo(tmp_path, "novenv-forge", DECL)
    home = _receipt_home(tmp_path, "novenv-forge", {"venv": str(tmp_path / "no-venv")})
    res = resolve_interpreter(forge_id="novenv-forge", checkout=repo, home=home)
    assert res.source == "fallback"
    assert any("has no interpreter" in w for w in res.warnings)


# ---------------------------------------------------------------------------
# extras — declared in forge.json, probed against each candidate
# ---------------------------------------------------------------------------


def test_missing_declared_extras_blocks(tmp_path):
    """forge.json ``extras`` the candidate cannot import → rejected at every
    level → BLOCKED with the precise missing-extras reason."""
    repo = _repo(tmp_path, "mcp-forge", DECL, extras=["definitely_missing_extra_xyz"])
    res = resolve_interpreter(
        forge_id="mcp-forge", checkout=repo, home=tmp_path / "empty"
    )
    assert res.python is None and res.source == "none"
    assert res.extras == ("definitely_missing_extra_xyz",)
    assert any("missing extras" in c.verdict for c in res.rejected)
    outcomes, _ = collect(manifests=[], repos=(repo,), mode="A",
                          home=tmp_path / "empty")
    (out,) = outcomes
    assert out.state == "BLOCKED" and out.reason == "no-interpreter"
    assert "missing extras" in out.detail


def test_extras_present_selects_candidate(tmp_path):
    """A stdlib-importable declared extra keeps the candidate eligible."""
    repo = _repo(tmp_path, "ok-forge", DECL, extras=["json"])
    venv = _fake_venv(tmp_path, "v-ok")
    home = _receipt_home(tmp_path, "ok-forge", {"venv": str(venv)})
    res = resolve_interpreter(forge_id="ok-forge", checkout=repo, home=home)
    assert res.source == "managed-receipt"
    assert res.extras == ("json",)


def test_specialist_env_beats_collector_fallback(tmp_path):
    """``.venv`` inside the checkout wins over sys.executable — the collector
    env no longer decides which extras exist."""
    repo = _repo(tmp_path, "envforge", DECL)
    venv = _fake_venv(repo, ".venv")
    res = resolve_interpreter(
        forge_id="envforge", checkout=repo, home=tmp_path / "empty"
    )
    assert res.source == "specialist-env"
    assert res.python == str(venv / "bin" / "python")


# ---------------------------------------------------------------------------
# honest states end-to-end
# ---------------------------------------------------------------------------


def test_extras_present_vs_absent_same_lab(tmp_path):
    """Managed venv with the extras marker runs; without it the receipt
    honestly reports per-scenario `skipped` — never mapped to PASS."""
    repo = _repo(tmp_path, "fake-forge", DECL)
    (repo / "fake_lab.py").write_text(EXTRAS_LAB, encoding="utf-8")
    venv = _fake_venv(tmp_path, "v-extras")
    home = _receipt_home(tmp_path, "fake-forge", {"venv": str(venv)})

    outcomes, _ = collect(manifests=[], repos=(repo,), mode="A", home=home)
    (out,) = outcomes
    assert out.state == "PASS"
    assert out.interpreter is not None and out.interpreter.source == "managed-receipt"
    assert out.runs[0].results[0].verdict == "skipped"  # extra absent — honest

    (venv / ".has-extras").write_text("mcp,graphql\n")
    outcomes, _ = collect(manifests=[], repos=(repo,), mode="A", home=home)
    (out,) = outcomes
    assert out.state == "PASS"
    assert out.runs[0].results[0].verdict == "pass"


def test_states_and_reasons_in_report(tmp_path):
    ran_repo = _repo(tmp_path, "fake-forge", DECL)
    (ran_repo / "fake_lab.py").write_text(EXTRAS_LAB, encoding="utf-8")
    venv = _fake_venv(tmp_path, "v-r")
    (venv / ".has-extras").write_text("x\n")
    home = _receipt_home(tmp_path, "fake-forge", {"venv": str(venv)})
    undeclared = _repo(tmp_path, "no-lab")
    blocked = _repo(tmp_path, "blk", DECL, python=">=99")
    outcomes, _ = collect(
        manifests=[],
        repos=(ran_repo, undeclared, blocked),
        mode="A",
        home=home,
    )
    by_forge = {o.forge_id: o for o in outcomes}
    assert by_forge["fake-forge"].state == "PASS"
    assert by_forge["no-lab"].state == "SKIPPED"
    assert by_forge["no-lab"].reason == "undeclared"
    assert by_forge["blk"].state == "BLOCKED"
    assert by_forge["blk"].reason == "no-interpreter"
    data = write_report(
        root=tmp_path, mode="A", outcomes=outcomes, producer=PRODUCER,
        out=tmp_path / "bench", guardrails={"mode": "A"},
    )
    summary = data["summary"]
    assert summary["states"] == {"PASS": 1, "SKIPPED": 1, "BLOCKED": 1}
    forge_rows = {f["forge"]: f for f in data["forges"]}
    assert forge_rows["fake-forge"]["interpreter"]["source"] == "managed-receipt"
    assert forge_rows["blk"]["reason"] == "no-interpreter"
    md = Path(data["report"]).read_text(encoding="utf-8")
    assert "| blk | BLOCKED |" in md
    assert "SKIPPED" in md  # skip states stay visible, never folded to PASS


def test_version_probe_free_and_spawned(tmp_path):
    # sys.executable resolves without spawn
    assert _interpreter_version(sys.executable, probe=False) == tuple(
        sys.version_info[:3]
    )
    # pyvenv.cfg is the env's own declaration — read without spawn, and it
    # wins over the resolved binary identity
    venv = _fake_venv(tmp_path, "v-cfg", version="3.12.1")
    assert _interpreter_version(str(venv / "bin" / "python"), probe=False) == (3, 12, 1)
    # a symlinked interpreter without pyvenv.cfg resolves to sys.executable
    venv2 = _fake_venv(tmp_path, "v-nocfg")
    assert _interpreter_version(str(venv2 / "bin" / "python"), probe=True) == tuple(
        sys.version_info[:3]
    )
    # a non-interpreter returns None — never fabricated
    bogus = tmp_path / "bogus"
    bogus.write_text("nope\n")
    assert _interpreter_version(str(bogus)) is None
    # combined probe reports version + missing extras in one spawn
    version, missing = _probe_interpreter(sys.executable, ("json", "nope_xyz"))
    assert version == tuple(sys.version_info[:3])
    assert missing == ("nope_xyz",)
    assert _probe_interpreter(str(bogus), ("x",)) == (None, None)
