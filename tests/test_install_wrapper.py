"""Regression coverage for the Windows install wrapper's PATH handling."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_windows_template_selects_one_python_command() -> None:
    """Multiple PATH matches must not become one invalid executable string."""
    source = (ROOT / "scripts" / "installkit" / "vendor.py").read_text(encoding="utf-8")
    assert (
        "Get-Command $c -CommandType Application -ErrorAction SilentlyContinue"
        " | Select-Object -First 1"
    ) in source


def test_checked_in_windows_wrapper_matches_selection_contract() -> None:
    source = (ROOT / "install.ps1").read_text(encoding="utf-8")
    assert "Select-Object -First 1" in source
