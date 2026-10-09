"""What the adapter exposes of Platform Forge: the public seam map and the surface snapshot.

``native_surface.json`` is a snapshot of the specialist's *public boundary surface*, rewritten
by ``python -m theforge_platformforge.record`` in the specialist's interpreter. A seam is
exposed as a Forge capability only when the snapshot says it is present; when a seam is absent
the capability becomes a manifest limitation instead, so the manifest never claims a surface
the installed specialist does not have. The adapter drives only public, offline, read-only
seams:

- ``platformforge.iac.terraform.analyze_hcl(path)`` — Terraform/HCL tree → fact document.
  Exposed as ``iac.analyze``.
- ``platformforge.iac.plan.analyze_plan(path)`` — a ``terraform show -json`` plan → fact
  document plus plan findings. Exposed as ``iac.plan-review``.
- ``platformforge.iac.plan.analyze_state(path)`` — a tfstate document → fact document.
  Exposed as ``iac.state``.
- ``platformforge.k8s.manifests.analyze_k8s(path)`` — Kubernetes manifests → fact document.
  Exposed as ``k8s.analyze``.
- ``platformforge.security.scan.scan_secrets(path)`` — staged tree → secret findings with
  automatic redaction. Exposed as ``secrets.scan``.
- ``platformforge.cicd.github_actions.analyze_gha(path)`` — ``.github/workflows`` → fact
  document. Exposed as ``gha.analyze``.
- ``platformforge.cicd.gitops.analyze_gitops(path)`` — GitOps trees (ArgoCD/Flux/Kustomize
  layout) → fact document. Exposed as ``gitops.analyze``.
- ``platformforge.product.catalog.analyze_catalog(path)`` — Backstage ``catalog-info.yaml``
  → fact document. Exposed as ``catalog.analyze``.
- ``platformforge.forge.manifest.capability_manifest()`` — the specialist's own
  ``platformforge/capability-manifest/v3`` declaration. Exposed as ``platform.manifest`` (no
  staged input: it reports the installed surface).

The manifest's ``tools`` table, ``domains``, ``cross_forge`` contract and ``operations`` are
recorded in the snapshot for observability and drift — surface evidence, not a claimed
capability. Mutating executors stay unexposed (the manifest itself marks them
``runtime_available: false``).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SNAPSHOT_PATH = Path(__file__).with_name("native_surface.json")
DOMAINS = ("platform", "iac", "k8s", "security", "cicd", "product")
HAND_BUILT = "hand-built"

SEAM_IAC_ANALYZE = "iac_analyze"
SEAM_PLAN_REVIEW = "plan_review"
SEAM_STATE = "state_analyze"
SEAM_K8S = "k8s_analyze"
SEAM_SECRETS = "secrets_scan"
SEAM_GHA = "gha_analyze"
SEAM_GITOPS = "gitops_analyze"
SEAM_CATALOG = "catalog_analyze"
SEAM_MANIFEST = "capability_manifest"

# fnmatch ``*`` already spans ``/`` (``k8s/*.yaml`` matches ``k8s/a/b.yaml``); a bare name like
# ``case.yaml`` also matches by basename through the stage fallback.
IAC_GLOBS = ("*.tf", "*.tf.json", "*.hcl", "*.tfvars")
PLAN_GLOBS = ("tfplan.json", "*.tfplan.json", "plan.json", "*.plan.json")
STATE_GLOBS = ("*.tfstate", "terraform.tfstate", "*.tfstate.json")
K8S_GLOBS = (
    "*.yaml",
    "*.yml",
    "k8s/*.yaml",
    "manifests/*.yaml",
    "deploy/*.yaml",
    "charts/*",
)
SECRETS_GLOBS = ("*",)
# Routing signals for ``secrets.scan``: the file families a secret scan reads. Broad but
# literal — a catch-all glob would be rejected as a signal and would name nothing.
SECRET_FILE_GLOBS = (
    ".env",
    ".env.*",
    "*.env",
    "*.pem",
    "*.key",
    "*.p12",
    "*.pfx",
    "*.keystore",
    "credentials",
    "credentials.*",
    "id_rsa",
    "id_rsa.*",
    "*.secret",
    "*.secrets",
    "*.properties",
    "*.tfvars",
    "*.ini",
    "*.cfg",
    "*.conf",
    "*.yaml",
    "*.yml",
    "*.json",
    "*.toml",
    "*.sh",
    "*.ps1",
    "*.py",
    "*.tf",
)
GHA_GLOBS = (".github/workflows/*.yml", ".github/workflows/*.yaml")
GITOPS_GLOBS = (
    "*.yaml",
    "*.yml",
    "kustomization.yaml",
    "Chart.yaml",
    "argocd/*.yaml",
    "fluxcd/*.yaml",
)
CATALOG_GLOBS = ("catalog-info.yaml", "catalog-info.yml", "catalog-info.*.yaml")

# Artifact types the capabilities emit (consumed via the evidence bus by providers that
# declare a matching ``consumes``).
IAC_FACTS = "platform.iac-facts"
PLAN_REVIEW = "platform.plan-review"
STATE_FACTS = "platform.state-facts"
K8S_FACTS = "platform.k8s-facts"
SECRETS_REPORT = "platform.secrets-report"
GHA_FACTS = "platform.gha-facts"
GITOPS_FACTS = "platform.gitops-facts"
CATALOG_FACTS = "platform.catalog-facts"
MANIFEST_DOC = "platform.capability-manifest"


@dataclass(frozen=True)
class CapabilitySpec:
    """How a capability runs: its seam, inputs, actions and routing signals.

    ``input_globs`` name the files the capability reads from ``stage/``; ``stage_root``
    inputs receive the staged workspace root itself. ``needs_input=False`` marks a seam that
    inspects the installed package (``platform.manifest``) instead of staged files.
    ``relations`` carries the declared capability-graph edges (``produces`` artifact types,
    and ``consumes`` only where the specialist's own manifest declares acceptance —
    ``cross_forge.accepts`` is recorded verbatim in the snapshot).
    """

    seam: str
    actions: tuple[str, ...]
    input_globs: tuple[str, ...]
    signals_keywords: tuple[str, ...]
    file_globs: tuple[str, ...]
    description: str
    stage_root: bool = True
    needs_input: bool = True
    relations: Mapping[str, tuple[str, ...]] = field(default_factory=dict)


CAPABILITY_MAP: Mapping[str, CapabilitySpec] = {
    "iac.analyze": CapabilitySpec(
        seam=SEAM_IAC_ANALYZE,
        actions=("analyze",),
        input_globs=IAC_GLOBS,
        signals_keywords=(
            "terraform",
            "hcl",
            "iac",
            "infrastructure as code",
            "tf plan",
            "terraform module",
            "resource block",
        ),
        file_globs=IAC_GLOBS,
        description="Terraform/HCL tree → fact document: resources, modules, providers and "
        "their attributes with provenance (iac.terraform.analyze_hcl).",
        relations={"produces": (IAC_FACTS,)},
    ),
    "iac.plan-review": CapabilitySpec(
        seam=SEAM_PLAN_REVIEW,
        actions=("analyze",),
        input_globs=PLAN_GLOBS,
        signals_keywords=(
            "terraform plan",
            "tfplan",
            "plan review",
            "will destroy",
            "plan output",
        ),
        file_globs=PLAN_GLOBS,
        description="A ``terraform show -json`` plan → fact document: creates/updates/"
        "deletes with risk-relevant attributes (iac.plan.analyze_plan).",
        relations={"produces": (PLAN_REVIEW,)},
    ),
    "iac.state": CapabilitySpec(
        seam=SEAM_STATE,
        actions=("analyze",),
        input_globs=STATE_GLOBS,
        signals_keywords=("tfstate", "terraform state", "state file", "drift input"),
        file_globs=STATE_GLOBS,
        description="A tfstate document → fact document: recorded resources and outputs "
        "(iac.plan.analyze_state).",
        relations={"produces": (STATE_FACTS,)},
    ),
    "k8s.analyze": CapabilitySpec(
        seam=SEAM_K8S,
        actions=("analyze",),
        input_globs=K8S_GLOBS,
        signals_keywords=(
            "kubernetes",
            "k8s",
            "manifest",
            "deployment",
            "pod",
            "helm",
            "kustomize",
        ),
        file_globs=K8S_GLOBS,
        description="Kubernetes manifest tree → fact document: workloads, services, RBAC "
        "and security-relevant fields (k8s.manifests.analyze_k8s).",
        relations={"produces": (K8S_FACTS,)},
    ),
    "secrets.scan": CapabilitySpec(
        seam=SEAM_SECRETS,
        actions=("scan",),
        input_globs=SECRETS_GLOBS,
        signals_keywords=(
            "secret",
            "credential leak",
            "api key",
            "token in code",
            "private key",
            "password",
        ),
        # Routing signals name the file families a secret scan targets; the staged
        # *input* is the whole tree (``*`` = "any staged file", like the Doctors) —
        # a secret can hide anywhere. Catch-all globs are rejected as signals.
        file_globs=SECRET_FILE_GLOBS,
        description="Staged tree → secret findings with automatic redaction; never emits "
        "raw secret material (security.scan.scan_secrets).",
        relations={"produces": (SECRETS_REPORT,)},
    ),
    "gha.analyze": CapabilitySpec(
        seam=SEAM_GHA,
        actions=("analyze",),
        input_globs=GHA_GLOBS,
        signals_keywords=(
            "github actions",
            "workflow",
            "gha",
            "ci pipeline",
            ".github/workflows",
        ),
        file_globs=GHA_GLOBS,
        description="GitHub Actions workflows → fact document: jobs, permissions, triggers "
        "and action pins (cicd.github_actions.analyze_gha).",
        relations={"produces": (GHA_FACTS,)},
    ),
    "gitops.analyze": CapabilitySpec(
        seam=SEAM_GITOPS,
        actions=("analyze",),
        input_globs=GITOPS_GLOBS,
        signals_keywords=(
            "gitops",
            "argocd",
            "flux",
            "kustomization",
            "sync wave",
        ),
        file_globs=GITOPS_GLOBS,
        description="GitOps trees (ArgoCD applications, Flux sources, Kustomize layouts) → "
        "fact document (cicd.gitops.analyze_gitops).",
        relations={"produces": (GITOPS_FACTS,)},
    ),
    "catalog.analyze": CapabilitySpec(
        seam=SEAM_CATALOG,
        actions=("analyze",),
        input_globs=CATALOG_GLOBS,
        signals_keywords=(
            "backstage",
            "catalog-info",
            "service catalog",
            "component spec",
            "api spec registration",
        ),
        file_globs=CATALOG_GLOBS,
        description="Backstage catalog-info documents → fact document: components, APIs, "
        "resources and ownership claims (product.catalog.analyze_catalog).",
        relations={"produces": (CATALOG_FACTS,)},
    ),
    "platform.manifest": CapabilitySpec(
        seam=SEAM_MANIFEST,
        actions=("report",),
        input_globs=(),
        signals_keywords=(
            "platform manifest",
            "platformforge capability",
            "platform surface",
            "capability manifest",
        ),
        file_globs=(),
        description="The specialist's own capability-manifest/v3 declaration: tools, "
        "operations, modes, domains, contracts and the cross-forge delegation contract "
        "(forge.manifest.capability_manifest).",
        needs_input=False,
        relations={"produces": (MANIFEST_DOC,)},
    ),
}


class SnapshotError(ValueError):
    """``native_surface.json`` is missing or malformed."""


def _seam(data: object, index: int) -> dict[str, Any]:
    where = f"snapshot.seams[{index}]"
    if not isinstance(data, dict):
        raise SnapshotError(f"{where}: expected an object")
    for key in ("name", "module", "callable"):
        if not isinstance(data.get(key), str) or not data[key]:
            raise SnapshotError(f"{where}.{key}: expected a non-empty string")
    if type(data.get("present")) is not bool:
        raise SnapshotError(f"{where}.present: expected a boolean")
    return dict(data)


def validate_snapshot(data: object) -> dict[str, Any]:
    """The snapshot as a dict, or ``SnapshotError`` naming the first malformed field."""
    if not isinstance(data, dict):
        raise SnapshotError("snapshot: expected an object")
    for key in ("specialist_version", "recorded_at", "provenance"):
        if not isinstance(data.get(key), str) or not data[key]:
            raise SnapshotError(f"snapshot.{key}: expected a non-empty string")
    seams = data.get("seams")
    if not isinstance(seams, list):
        raise SnapshotError("snapshot.seams: expected a list")
    seen: set[str] = set()
    for index, item in enumerate(seams):
        seam = _seam(item, index)
        if seam["name"] in seen:
            raise SnapshotError(f"snapshot.seams[{index}]: duplicate seam {seam['name']!r}")
        seen.add(seam["name"])
    for list_key in ("tools", "domains", "cross_forge_accepts"):
        value = data.get(list_key, [])
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise SnapshotError(f"snapshot.{list_key}: expected a list of strings")
    return data


def load_snapshot(path: Path = SNAPSHOT_PATH) -> dict[str, Any]:
    """Read and validate the packaged surface snapshot."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise SnapshotError(f"{path.name}: unreadable ({type(exc).__name__})") from None
    return validate_snapshot(data)


def seam_present(snapshot: Mapping[str, Any], name: str) -> bool:
    """Whether the recorded surface has the seam an exposed capability needs."""
    return any(
        isinstance(item, Mapping) and item.get("name") == name and item.get("present") is True
        for item in snapshot.get("seams") or ()
    )


def native_fingerprint(snapshot: Mapping[str, Any]) -> str:
    """The sha256 the manifest declares as ``native_surface_fingerprint``: the canonical
    snapshot minus ``recorded_at`` (a timestamp, not surface)."""
    canonical = dict(snapshot)
    canonical.pop("recorded_at", None)
    blob = json.dumps(canonical, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def capability_entry(spec: CapabilitySpec) -> dict[str, Any]:
    """The manifest capability for a seam the recorded surface provides."""
    entry: dict[str, Any] = {
        "actions": list(spec.actions),
        "default_action": spec.actions[0],
        "state": "supported",
        "operation_class": "read_only",
        "description": spec.description,
        "signals": {
            "keywords": list(spec.signals_keywords),
            "file_globs": list(spec.file_globs),
            "dependencies": [],
        },
    }
    if spec.relations:
        entry["relations"] = {name: list(refs) for name, refs in spec.relations.items()}
    return entry


def manifest_payload(
    snapshot: Mapping[str, Any],
    *,
    provider_id: str,
    version: str,
    ops: Sequence[str] = ("describe", "health", "execute"),
) -> dict[str, Any]:
    """The ``ForgeManifest`` v1 payload derived from a validated surface snapshot."""
    capabilities: list[dict[str, Any]] = []
    limitations: list[str] = []
    if snapshot["provenance"] == HAND_BUILT:
        limitations.append(
            "native surface snapshot is hand-built (provisional until re-recorded with "
            "python -m theforge_platformforge.record)"
        )
    for capability_id in sorted(CAPABILITY_MAP):
        spec = CAPABILITY_MAP[capability_id]
        if seam_present(snapshot, spec.seam):
            capabilities.append({"id": capability_id, **capability_entry(spec)})
            if capability_id == "secrets.scan":
                # Declared, not discovered at runtime: the core never stages
                # secret-named files, so the scan reads staged content only.
                limitations.append(
                    "secrets.scan reads staged content only: files whose names match "
                    "the core's secret-name boundary (.env, .env.*, *.pem, *.key, "
                    "credentials*, secrets.*) are excluded before staging — an ok "
                    "result with zero facts does not mean 'no secrets'"
                )
        else:
            limitations.append(
                f"capability '{capability_id}' not exposed: seam "
                f"{spec.seam!r} absent from the recorded native surface"
            )
    return {
        "schema": "theforge/ForgeManifest/v1",
        "id": provider_id,
        "version": version,
        "protocols": ["forge/v1"],
        "ops": list(ops),
        "domains": list(DOMAINS),
        "capabilities": capabilities,
        "execution": {"local": True, "offline": True, "requires_network": False},
        "limitations": limitations,
        "unknowns": [],
        # context-intelligence-v2: the adapter verifies the sha256 of every file it stages
        # and the specialist reads only those copies.
        "context_revalidation": "hash",
        "adapter_version": version,
        "native_surface_fingerprint": native_fingerprint(snapshot),
    }
