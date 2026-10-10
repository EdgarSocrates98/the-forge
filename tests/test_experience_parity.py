"""Cross-forge experience parity (Cycle 4.6).

The vendored UI kit must be byte-identical to the canonical one modulo
the package import rewrite, and every sibling must wire its bare CLI
entry to the interactive home with a headless fallback.
"""

from __future__ import annotations

from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[2]

REPOS = {
    "api-forge": ("src/apiforge", "src/apiforge/cli.py", "apiforge.ui.home"),
    "spark-forge-aws": (
        "sparkforge_aws",
        "sparkforge_aws/adapters/cli.py",
        "sparkforge_aws.ui.home",
    ),
    "spark-forge-azure": (
        "sparkforge_azure",
        "sparkforge_azure/cli/main.py",
        "sparkforge_azure.ui.home",
    ),
    "platform-forge": ("platformforge", "platformforge/cli/main.py", "platformforge.ui.home"),
    "forge-doctor-data": (
        "src/forge_doctor_data",
        "src/forge_doctor_data/cli/app.py",
        "forge_doctor_data.ui.home",
    ),
    "forge-doctor-api": (
        "src/forge_doctor_api",
        "src/forge_doctor_api/cli/__init__.py",
        "forge_doctor_api.ui.home",
    ),
}

KIT_FILES = ("kit.py", "i18n.py", "wizard.py")


def _canonical(fname: str, pkg: str) -> str:
    src = (WORKSPACE / "the-forge" / "src" / "theforge" / "ui" / fname).read_text(encoding="utf-8")
    return src.replace("theforge.ui", f"{pkg}.ui")


def test_kit_byte_parity_per_repo():
    drift = []
    for repo, (pkg_rel, _entry, _mod) in REPOS.items():
        pkg = pkg_rel.split("/")[-1]
        for fname in KIT_FILES:
            vendored = WORKSPACE / repo / pkg_rel / "ui" / fname
            if not vendored.is_file():
                drift.append(f"{repo}: missing ui/{fname}")
                continue
            assert vendored.read_text(encoding="utf-8") == _canonical(fname, pkg), (
                f"{repo}: ui/{fname} drifted from canonical kit"
            )
    assert not drift


def test_every_repo_has_home():
    for repo, (pkg_rel, _entry, _mod) in REPOS.items():
        home = WORKSPACE / repo / pkg_rel / "ui" / "home.py"
        assert home.is_file(), f"{repo}: no ui/home.py"
        body = home.read_text(encoding="utf-8")
        assert "run_home" in body and "NonInteractive" in body


def test_bare_entry_wired_with_headless_fallback():
    for repo, (_pkg, entry, mod) in REPOS.items():
        src = (WORKSPACE / repo / entry).read_text(encoding="utf-8")
        assert mod in src, f"{repo}: {entry} does not import {mod}"
        assert "isatty" in src, f"{repo}: bare entry lacks the TTY gate"


def test_menus_reference_real_verbs():
    import json

    for repo, (pkg_rel, _e, _m) in REPOS.items():
        inv = WORKSPACE / repo / "docs" / "reference" / "commands.generated.json"
        home = WORKSPACE / repo / pkg_rel / "ui" / "home.py"
        if not inv.is_file() or not home.is_file():
            continue
        verbs = {
            c["path"].split()[0] for c in json.loads(inv.read_text(encoding="utf-8"))["commands"]
        }
        import re

        for argv in re.findall(r"\['([a-z-]+)'", home.read_text(encoding="utf-8")):
            assert argv in verbs, f"{repo}: menu verb {argv!r} not a real command"
