"""The specialist-reality collector stays evidence-honest (Cycle 5.1)."""

import json
import sys
from pathlib import Path

import pytest
from scripts.reality import collect as reality

pytestmark = pytest.mark.unit


def _spec(name: str = "api-forge") -> reality.Specialist:
    return next(s for s in reality.SPECIALISTS if s.name == name)


def test_manifest_shape_when_nothing_is_configured(tmp_path, monkeypatch):
    monkeypatch.delenv("THEFORGE_REAL_APIFORGE_PYTHON", raising=False)
    manifest = reality.collect(
        fetch=False, overrides={"api-forge": str(tmp_path / "missing-python")}
    )
    assert manifest["kind"] == "theforge/specialist-reality/v1"
    api = next(s for s in manifest["specialists"] if s["name"] == "api-forge")
    assert api["compatibility_status"] == "missing"
    assert api["python_source"].startswith("--python")


def test_status_rollup_matrix():
    def entry(drift: str, relation: str | None) -> dict:
        return {
            "drift": {"status": drift},
            "installed": {"checkout": {"relation_to_origin_main": relation}},
        }

    assert reality._status_of(entry("none", "same")) == "fresh"
    assert reality._status_of(entry("additive", "same")) == "snapshot_fresh_install_diverged"
    assert reality._status_of(entry("none", "descendant")) == "snapshot_fresh_install_ahead"
    assert reality._status_of(entry("none", "ancestor")) == "snapshot_fresh_install_diverged"
    assert reality._status_of(entry("none", "diverged")) == "snapshot_fresh_install_diverged"
    assert reality._status_of(entry("breaking", "same")) == "drifted"
    assert reality._status_of(entry("unverifiable", "same")) == "unverifiable"
    assert reality._status_of(entry("none", None)) == "unverifiable"


def test_snapshot_info_counts_lists_and_dicts(tmp_path):
    snap = tmp_path / "native.json"
    snap.write_text(
        json.dumps(
            {
                "specialist_version": "1.0",
                "recorded_at": "2026-10-06",
                "tools": {"a": {}, "b": {}},
                "seams": ["x"],
            }
        ),
        encoding="utf-8",
    )
    info = reality._snapshot_info(snap)
    assert info["entries"] == {"tools": 2, "seams": 1}
    assert len(info["sha256"]) == 64
    assert info["specialist_version"] == "1.0"


def test_checkout_state_file_url_windows(tmp_path):
    # A file:// URL pointing at a directory without .git is unverifiable, not an error.
    state = reality._checkout_state(tmp_path.as_uri(), fetch=False)
    if sys.platform == "win32":
        # Path(tmp_path.as_uri()) style paths parse to the real directory.
        assert state["relation_to_origin_main"] == "unverifiable"
    else:
        assert state["relation_to_origin_main"] == "unverifiable"


def test_checkout_state_missing_location():
    state = reality._checkout_state(None, fetch=False)
    assert state["relation_to_origin_main"] == "unverifiable"
    assert "direct_url" in state["reason"]


def test_checkout_state_real_repo():
    repo = Path(__file__).resolve().parent.parent
    state = reality._checkout_state(repo.as_uri(), fetch=False)
    assert state["commit_sha"]
    assert state["origin_main"] or state["relation_to_origin_main"] in {"unverifiable"}


def test_contract_counts_match_schema_parity():
    counts = reality._contract_counts()
    schemas = len(list((reality.ROOT / "schemas").glob("*.json")))
    assert counts["contracts"] == schemas == 69
    assert counts.get("closed_contracts", 39) >= 39


def test_check_mode_fails_on_missing(tmp_path, capsys):
    out = tmp_path / "manifest.json"
    missing = {s.name: str(tmp_path / f"no-{s.name}") for s in reality.SPECIALISTS}
    argv = ["--out", str(out), "--check"] + [f"--python={k}={v}" for k, v in missing.items()]
    rc = reality.main(argv)
    assert rc == 1
    assert "reality check failed" in capsys.readouterr().err
