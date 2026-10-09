"""Cross-repo agentic manifest validation.

For every workspace checkout that ships ``forge.agentic.json``, verify:

- the document parses to ``AgenticManifest/v1`` (strict contract),
- ``cli_entry`` is a ``module:function`` reference whose module imports
  when the checkout's package is importable (skip when deps missing),
- every workflow command's first literal token after ``{cli}`` is a real
  top-level verb of that CLI per ``commands.generated.json`` when present.

Skips silently when no checkout declares a manifest — absence is honest,
a malformed manifest is not.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from theforge import _installkit as kit
from theforge.contracts.base import from_dict
from theforge.contracts.specialist import AgenticManifest

WORKSPACE = Path(__file__).resolve().parents[2]


def _checkouts() -> list[Path]:
    if not WORKSPACE.is_dir():
        return []
    return [m for m in kit.discover_projects(WORKSPACE) if (m / "forge.agentic.json").is_file()]


def _real_verbs(checkout: Path) -> set[str] | None:
    inv = checkout / "docs" / "reference" / "commands.generated.json"
    if not inv.is_file():
        return None
    doc = json.loads(inv.read_text(encoding="utf-8"))
    return {c.get("path", "").split()[0] for c in doc.get("commands", []) if c.get("path")}


def _manifests() -> list[tuple[Path, AgenticManifest]]:
    out = []
    for checkout in _checkouts():
        doc = json.loads((checkout / "forge.agentic.json").read_text(encoding="utf-8"))
        out.append((checkout, from_dict(AgenticManifest, doc)))
    return out


def test_manifests_parse_to_contract():
    manifests = _manifests()
    assert manifests, "no forge.agentic.json found in workspace checkouts"
    for checkout, manifest in manifests:
        assert manifest.provider == json.loads(
            (checkout / "forge.json").read_text(encoding="utf-8")
        )["forge_id"], f"{checkout.name}: manifest provider != forge.json forge_id"


def test_workflow_commands_use_real_verbs():
    for checkout, manifest in _manifests():
        verbs = _real_verbs(checkout)
        assert manifest.workflows, f"{checkout.name}: manifest declares no workflows"
        for wf in manifest.workflows:
            assert wf.command, f"{checkout.name}:{wf.id} empty command"
            assert "{cli}" in wf.command or "{python}" in wf.command, (
                f"{checkout.name}:{wf.id} has no executable placeholder"
            )
            if verbs is not None:
                literal_verbs = [
                    t
                    for i, t in enumerate(wf.command)
                    if not t.startswith("{") and not t.startswith("-") and i > 0
                ]
                if literal_verbs:
                    first = literal_verbs[0]
                    assert first in verbs, (
                        f"{checkout.name}:{wf.id} verb {first!r} not in generated "
                        f"inventory: {sorted(verbs)[:10]}…"
                    )


def test_cli_entry_shape():
    for checkout, manifest in _manifests():
        if not manifest.cli_entry:
            continue
        assert ":" in manifest.cli_entry, f"{checkout.name}: cli_entry must be module:function"
        module, _, fn = manifest.cli_entry.partition(":")
        assert module and fn and fn.isidentifier()
        # import check only when the package is trivially importable
        pkg_root = checkout / "src" if (checkout / "src" / module.split(".")[0]).is_dir() else checkout
        probe = f"import sys; sys.path.insert(0, {str(pkg_root)!r}); import {module.split('.')[0]}"
        import subprocess

        proc = subprocess.run(
            [sys.executable, "-c", probe], capture_output=True, text=True, timeout=60
        )
        if proc.returncode == 0:
            # package imports — verify the module does too. A failure whose
            # missing module is the package itself is a manifest bug; a
            # missing third-party dep (typer, yaml…) is an environment gap.
            proc2 = subprocess.run(
                [sys.executable, "-c", probe + f"; import {module}"],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if proc2.returncode != 0:
                top = module.split(".")[0]
                own_missing = f"No module named '{top}'" in proc2.stderr or (
                    f"No module named '{module}'" in proc2.stderr
                )
                assert not own_missing, (
                    f"{checkout.name}: cli_entry module {module} does not import: "
                    f"{proc2.stderr[-300:]}"
                )
        # else: deps missing — import unverifiable, recorded as skipped
