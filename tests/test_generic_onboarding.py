"""Cycle 5.1 W5: generic onboarding — a never-seen provider climbs the ladder.

``example-forge`` is a provider nobody wrote an adapter for: it speaks Forge
Protocol v1 through the generic ``fixture_forge.py`` driver and a plain manifest
file. The tests prove it reaches DISCOVERABLE → CONTRACT_COMPATIBLE →
SURFACE_VALIDATED → PLANNABLE (and executes end-to-end) through exactly the same
code path every real specialist uses — no ``if provider == "example-forge"``
anywhere.

The second half is the audit gate: ``src/theforge`` must never name a real
provider in *executable* code (docstrings citing history are fine). The check is
AST-based: any string constant that is not a bare statement (docstring) and
contains a real provider id or adapter module name is a violation.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from helpers import PROVIDERS, fixture_argv, make_workspace
from theforge.capability_graph import build_capability_graph
from theforge.contracts import ForgeManifest, from_dict
from theforge.contracts.integrity import validate_manifest_limits
from theforge.contracts.taxonomy import validate_taxonomy
from theforge.forger import AskRequest, Forger
from theforge.registry import Registry
from theforge.runs import RunStore

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src" / "theforge"
FIXTURE = PROVIDERS / "fixture-example.json"

EXAMPLE_ENTRY = {
    "id": "example-forge",
    "argv": fixture_argv("fixture_forge.py", str(FIXTURE)),
    "trust": "local",
}

# The six real providers and their adapter modules: none of these strings may
# steer core behavior.
FORBIDDEN = (
    "spark-forge-aws",
    "spark-forge-azure",
    "api-forge",
    "platform-forge",
    "forge-doctor-data",
    "forge-doctor-api",
    "theforge_sparkforge_aws",
    "theforge_sparkforge_azure",
    "theforge_apiforge",
    "theforge_platformforge",
    "theforge_doctordata",
    "theforge_doctorapi",
)


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    return make_workspace(tmp_path, [EXAMPLE_ENTRY])


def _record(root: Path):
    return Registry(root / ".forge").get("example-forge")


class TestGenericOnboarding:
    """The maturity ladder from raw evidence — the same rungs the federation
    conformance derives for the real specialists."""

    def test_discoverable_and_contract_compatible(self, workspace: Path) -> None:
        record = _record(workspace)
        assert record.state == "ready", record.error
        manifest = record.manifest
        assert manifest is not None and manifest.id == "example-forge"
        # CONTRACT_COMPATIBLE: both contract validators accept the manifest.
        assert validate_taxonomy(manifest) == ()
        assert validate_manifest_limits(manifest) == ()

    def test_surface_validated(self, workspace: Path) -> None:
        manifest = _record(workspace).manifest
        assert manifest is not None
        assert manifest.native_surface_fingerprint is not None

    def test_plannable(self, workspace: Path) -> None:
        record = _record(workspace)
        manifest = record.manifest
        assert manifest is not None and "execute" in manifest.ops
        routable = [
            c
            for c in manifest.capabilities
            if c.state == "supported" and c.operation_class == "read_only"
        ]
        assert routable, "no supported read-only capability"
        assert record.routable()

    def test_graph_ingests_the_new_provider(self, workspace: Path) -> None:
        record = _record(workspace)
        graph = build_capability_graph([record], run_id="onboarding")
        nodes = {n.id for n in graph.nodes}
        assert "provider:example-forge" in nodes
        assert "capability:example-forge/example.scan" in nodes
        assert "artifact_type:example.report" in nodes

    def test_executes_end_to_end(self, workspace: Path) -> None:
        out = Forger(workspace, Registry(workspace / ".forge"), RunStore(workspace / ".forge")).ask(
            AskRequest(intent="scan the example", capability="example.scan")
        )
        assert out.status in ("ok", "partial"), out.error
        assert out.result is not None and out.result.evidence
        assert out.decision.selected[0].provider == "example-forge"


class TestNoSpecialistNamesInCore:
    """The genericity gate: core code carries zero provider-name branches."""

    def _code_strings(self, path: Path) -> list[str]:
        """String constants that are *executed*: a bare ``Expr(Constant(str))``
        is a docstring (prose, allowed); every other string literal is data the
        runtime inspects."""
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        out: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
                continue  # docstring position
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                out.append(node.value)
        return out

    def test_no_provider_name_logic_in_core(self) -> None:
        hits: list[str] = []
        for path in sorted(SRC.rglob("*.py")):
            for literal in self._code_strings(path):
                for name in FORBIDDEN:
                    if name in literal:
                        hits.append(f"{path.relative_to(REPO)}: {name}")
        assert hits == [], "core code names a real provider:\n" + "\n".join(hits)

    def test_new_specialists_needed_no_core_change(self) -> None:
        """Regression evidence for the claim 'the core is generic': the diff of
        this cycle's work touches no `src/theforge` file in a way that mentions
        the new provider ids — enforced above; here we also assert the manifest
        fixture itself is contract-clean before use."""
        manifest = from_dict(ForgeManifest, json.loads(FIXTURE.read_text(encoding="utf-8")), "$")
        assert manifest.id == "example-forge"
        assert validate_taxonomy(manifest) == ()
        assert validate_manifest_limits(manifest) == ()
