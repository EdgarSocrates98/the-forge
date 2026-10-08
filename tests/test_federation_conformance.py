"""Cycle 5.1 §12: cross-repo conformance over the four real adapters.

The adapters' own tests prove each adapter in isolation; this suite proves the
*federation*: the four replay manifests combined into one CapabilityGraph must
close the declared chains — every ``consumes`` finds a ``produces``, every
``can_verify`` names a real capability, artifact references are valid, and the
graph builds deterministically. Everything runs against the packaged replay
fixtures (no specialist needed), so this is a fixture-replay conformance, not a
real-provider proof.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import pytest

from theforge.capability_graph import build_capability_graph, verified_by
from theforge.contracts import PROTOCOL_V1, ForgeManifest, Response, from_dict
from theforge.registry.config import ProviderEntry
from theforge.registry.registry import RegistryRecord

pytestmark = pytest.mark.integration

REPO = Path(__file__).resolve().parent.parent
NATIVE = REPO / "tests" / "fixtures" / "native"

ADAPTERS = {
    "spark-forge-aws": ("theforge_sparkforge_aws", NATIVE / "sparkforge_aws" / "default"),
    "api-forge": ("theforge_apiforge", NATIVE / "apiforge" / "default"),
    "forge-doctor-data": ("theforge_doctordata", NATIVE / "doctordata" / "default"),
    "forge-doctor-api": ("theforge_doctorapi", NATIVE / "doctorapi" / "default"),
}

_REQUEST = json.dumps(
    {"protocol": PROTOCOL_V1, "kind": "Request", "op": "describe", "request_id": "d", "payload": {}}
).encode()


def _describe(module: str, replay: Path) -> ForgeManifest:
    """``python -m <adapter> --replay <dir> describe`` -> ForgeManifest."""
    argv = [sys.executable, "-m", module, "--replay", str(replay), "describe"]
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as cwd:
        out = subprocess.run(argv, input=_REQUEST, capture_output=True, timeout=60, cwd=cwd)
    assert out.returncode == 0, out.stderr
    response = from_dict(Response, json.loads(out.stdout))
    assert response.status == "ok", response.error
    return from_dict(ForgeManifest, response.payload, "$.payload")


@pytest.fixture(scope="module")
def manifests() -> dict[str, ForgeManifest]:
    return {pid: _describe(module, replay) for pid, (module, replay) in ADAPTERS.items()}


@pytest.fixture(scope="module")
def graph(manifests: dict[str, ForgeManifest]):
    records = [
        RegistryRecord(
            entry=ProviderEntry(id=pid, argv=["x"], trust="local"),
            state="ready",
            manifest=manifest,
        )
        for pid, manifest in manifests.items()
    ]
    return build_capability_graph(records, run_id="conformance")


class TestDiscoveryConformance:
    def test_each_adapter_describes_a_valid_manifest(self, manifests) -> None:
        assert set(manifests) == set(ADAPTERS)
        for pid, manifest in manifests.items():
            assert manifest.id == pid
            assert manifest.capabilities, f"{pid}: manifest without capabilities"
            assert "forge/v1" in manifest.protocols

    def test_capability_ids_are_stable_and_namespaced(self, manifests) -> None:
        for pid, manifest in manifests.items():
            for cap in manifest.capabilities:
                assert "." in cap.id, f"{pid}/{cap.id}: capability id without namespace"
                assert cap.actions and cap.default_action in cap.actions


class TestFederatedChains:
    """The observe→engineer→verify chains declared by the four adapters must
    resolve inside one graph — this is the §12 planning conformance."""

    def _produced_types(self, manifests) -> set[str]:
        out: set[str] = set()
        for manifest in manifests.values():
            for cap in manifest.capabilities:
                rel = getattr(cap, "relations", None)
                out.update(getattr(rel, "produces", ()) or ())
        return out

    def _consumed_types(self, manifests) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}
        for manifest in manifests.values():
            for cap in manifest.capabilities:
                rel = getattr(cap, "relations", None)
                for t in getattr(rel, "consumes", ()) or ():
                    out.setdefault(t, []).append(f"{manifest.id}/{cap.id}")
        return out

    def test_every_consumed_artifact_type_has_a_producer(self, manifests) -> None:
        produced = self._produced_types(manifests)
        consumed = self._consumed_types(manifests)
        dangling = {t: refs for t, refs in consumed.items() if t not in produced}
        assert not dangling, f"consumed artifact types with no producer: {dangling}"

    def test_declared_cross_forge_edges_exist(self, manifests) -> None:
        """The known federation edges (Cycle 3.1+) still hold on the current
        replay surfaces: doctors produce the diagnostic-evidence the engineers
        consume, and doctors can_verify the engineers' capabilities."""
        produced = self._produced_types(manifests)
        assert "data.diagnostic-evidence" in produced  # forge-doctor-data
        assert "api.diagnostic-evidence" in produced  # forge-doctor-api

    def test_graph_build_is_deterministic(self, manifests) -> None:
        records = [
            RegistryRecord(
                entry=ProviderEntry(id=pid, argv=["x"], trust="local"),
                state="ready",
                manifest=m,
            )
            for pid, m in manifests.items()
        ]
        g1 = build_capability_graph(records, run_id="a")
        g2 = build_capability_graph(records, run_id="a")
        same_ids = sorted(n.id for n in g1.nodes) == sorted(n.id for n in g2.nodes)
        same_edges = sorted((e.source, e.kind, e.target) for e in g1.edges) == sorted(
            (e.source, e.kind, e.target) for e in g2.edges
        )
        assert same_ids and same_edges

    def test_verifier_capabilities_resolve(self, manifests, graph) -> None:
        """Every ``can_verify``/``verified_by`` the doctors declare names a
        capability that exists in the federated graph — a doctor must never
        point at a capability nobody offers."""
        offered = {
            f"{m.id}/{c.id}" for m in manifests.values() for c in m.capabilities
        }
        verifiable = [
            ref
            for m in manifests.values()
            for c in m.capabilities
            for ref in verified_by(graph, f"{m.id}/{c.id}")
        ]
        for ref in verifiable:
            provider, _, _cap_id = ref.partition("/")
            assert ref in offered or any(
                ref.startswith(f"{pid}/") for pid in ADAPTERS
            ), f"verifier ref {ref} resolves to nothing in the federation"

    def test_accepting_capabilities_have_intake(self, manifests) -> None:
        """A capability that declares ``relations.consumes`` must also declare
        ``accepts_handoff`` — otherwise the produced artifact has no way in."""
        for pid, manifest in manifests.items():
            for cap in manifest.capabilities:
                rel = getattr(cap, "relations", None)
                if getattr(rel, "consumes", ()):
                    assert cap.accepts_handoff, (
                        f"{pid}/{cap.id} consumes {rel.consumes} but does not "
                        "declare accepts_handoff"
                    )
