"""Host capability matrix (cycle 16.1, FRENTE E §9.1): declared-state
reporting — never inferred from filesystem detection."""

from __future__ import annotations

from pathlib import Path

from theforge import host_capabilities as hc


def test_matrix_is_declared_and_versioned() -> None:
    doc = hc.host_matrix()
    assert doc["schema"] == hc.MATRIX_SCHEMA
    assert doc["kind"] == "declared"
    assert set(doc["hosts"]) >= {"claude", "devin", "codex", "copilot"}
    assert doc["source"]["document"] == hc.SOURCE_DOC
    # capability rows are the full declared set, in deterministic order
    for host_row in doc["hosts"].values():
        assert list(host_row) == list(hc.CAPABILITIES)


def test_every_state_is_from_the_declared_enum() -> None:
    for host in ("claude", "devin", "codex", "copilot"):
        for cap in hc.CAPABILITIES:
            entry = hc.capability_state(host, cap)
            assert entry is not None
            assert entry["state"] in hc.STATES
            assert entry["detail"]


def test_unverified_stays_unverified() -> None:
    """Copilot's unproven capabilities are UNVERIFIED — the matrix never
    promotes a filesystem guess into 'supported'."""
    assert hc.capability_state("copilot", "skills")["state"] == "unverified"
    assert hc.capability_state("copilot", "mcp")["state"] == "unverified"
    assert hc.capability_state("claude", "agents_md")["state"] == "partial"


def test_matrix_does_not_infer_from_filesystem(tmp_path: Path) -> None:
    """A stray `.claude` dir must not change declared capability data —
    detection lives in `hosts list`, not in the matrix."""
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".github").mkdir()
    doc = hc.host_matrix()
    assert doc["hosts"]["copilot"]["skills"]["state"] == "unverified"
    assert doc["hosts"]["claude"]["agents_md"]["state"] == "partial"


def test_unknown_host_is_none_not_a_row() -> None:
    assert hc.capability_state("not-a-host", "skills") is None
