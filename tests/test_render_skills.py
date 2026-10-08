"""Canonical skill renderer tests (agentic prompt §16): one source → three hosts.

``scripts/agentic/render_skills.py`` renders ``agentic/skills/*.md`` to the
.claude/.agents/.devin mirrors; ``--check`` is the drift gate. These tests
exercise the renderer by path (the scripts/ci pattern, like
test_agentic_parity.py) and assert the generated outputs stay in sync on the
real repository.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO = Path(__file__).resolve().parents[1]
RENDERER = REPO / "scripts" / "agentic" / "render_skills.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("render_skills", RENDERER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


render = _load()

MINIMAL = """\
+++
name = "forge-demo"
description = "Demo trigger."

[claude]
allowed_tools = "Read, Bash"
argument_hint = "<x>"
[codex]
display_name = "Demo"
short_description = "demo"
+++

# forge-demo

## Overview

Overview body.

## When to Use

- always

<!-- host:devin -->
Devin-only note.
<!-- /host -->
"""


def test_real_repository_outputs_are_in_sync() -> None:
    result = subprocess.run(
        [sys.executable, str(RENDERER), "--check"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_all_fifteen_ecosystem_skills_render() -> None:
    sources = render.load_sources()
    names = {s.name for s in sources}
    assert names == {
        "forge-ecosystem",
        "forge-routing",
        "forge-discovery",
        "forge-install",
        "forge-bootstrap",
        "forge-capability-negotiation",
        "forge-cross-domain-planning",
        "forge-verification",
        "forge-troubleshooting",
        "forge-spark-aws",
        "forge-spark-azure",
        "forge-api",
        "forge-platform",
        "forge-doctor-data",
        "forge-doctor-api",
    }
    assert len(names) == 15


def test_rendered_outputs_exist_for_every_host() -> None:
    for src in render.load_sources():
        outputs = render.render_all(src)
        assert set(outputs) == {
            f".claude/skills/{src.name}/SKILL.md",
            f".agents/skills/{src.name}/SKILL.md",
            f".agents/skills/{src.name}/agents/openai.yaml",
            f".devin/skills/{src.name}/SKILL.md",
        }
        for rel in outputs:
            assert (REPO / rel).is_file(), rel


def test_claude_gets_tools_and_plain_sections(tmp_path: Path) -> None:
    src = render.parse_source(_write(tmp_path, MINIMAL))
    out = render.render_claude(src)
    assert "allowed-tools: Read, Bash" in out
    assert "argument-hint: <x>" in out
    assert "## Overview" in out
    assert "<background_information>" not in out
    assert "Devin-only note" not in out


def test_agents_and_devin_get_envelope(tmp_path: Path) -> None:
    src = render.parse_source(_write(tmp_path, MINIMAL))
    for host in ("codex", "devin"):
        out = render.render_envelope(src, host)
        assert "<background_information>\nOverview body.\n</background_information>" in out
        assert "<instructions>" in out and "</instructions>" in out
        assert "## Overview" not in out
        assert "allowed-tools" not in out
    assert "Devin-only note." in render.render_envelope(src, "devin")
    assert "Devin-only note." not in render.render_envelope(src, "codex")


def test_openai_yaml_uses_codex_metadata(tmp_path: Path) -> None:
    src = render.parse_source(_write(tmp_path, MINIMAL))
    out = render.render_openai_yaml(src)
    assert 'display_name: "Demo"' in out
    assert "allow_implicit_invocation: false" in out


def test_missing_overview_is_a_render_error(tmp_path: Path) -> None:
    bad = MINIMAL.replace("## Overview\n\nOverview body.\n\n", "")
    with pytest.raises(render.RenderError, match="Overview"):
        render.parse_source(_write(tmp_path, bad))


def test_name_must_match_filename(tmp_path: Path) -> None:
    bad = MINIMAL.replace('name = "forge-demo"', 'name = "other"')
    with pytest.raises(render.RenderError, match="must match"):
        render.parse_source(_write(tmp_path, bad))


def test_unclosed_host_block_fails_render(tmp_path: Path) -> None:
    bad = MINIMAL.replace("<!-- /host -->", "")
    src = render.parse_source(_write(tmp_path, bad))
    with pytest.raises(render.RenderError, match="host block"):
        render.render_envelope(src, "devin")


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "forge-demo.md"
    path.write_text(text, encoding="utf-8")
    return path
