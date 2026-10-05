"""ProjectIntel: fingerprinted, staleness-aware workspace memory (Cycle 3 Wave I).

The technical memory of the project — not conversational memory. One snapshot at
``.forge/intel/project.json``: the last ``WorkspaceDescriptor`` the core computed,
the content digests of everything it derives from, and which sections were reused
verbatim at the last refresh.

I2 — never stale silently: this contract deliberately carries *no* ``validity``
field. A stored ``current`` would be exactly the lie the spec forbids: freshness
is a read-time verdict — ``intel.freshness`` recomputes the fingerprints and
reports ``current``/``stale`` — never persisted as truth.
"""

from dataclasses import dataclass, field

from theforge.contracts.base import ContractError
from theforge.contracts.types import Producer
from theforge.contracts.workspace import WorkspaceDescriptor

INTEL_SCHEMA = "theforge/ProjectIntel/v1"


@dataclass(frozen=True, kw_only=True)
class IntelFingerprints:
    """Content digests of every input the cached descriptor derives from.

    Recomputed cheaply at read time (no git, no dependency parsing): an equal
    digest proves the corresponding descriptor section is still accurate.
    """

    files_sha: str  # sha256 over the sorted WorkspaceScan file list
    repos_sha: str  # sha256 over the discovered repository paths
    depfiles_sha: str  # sha256 over (path, content sha256) of each dependency manifest
    manifests_sha: str  # sha256 over (id, state, manifest sha256) of registry records
    relations_sha: str  # sha256 of .forge/config/workspace.toml bytes ("" if absent)


@dataclass(frozen=True, kw_only=True)
class ProjectIntel:
    """The cached workspace snapshot plus the evidence needed to re-verify it.

    ``reused`` audits the incremental refresh: the descriptor sections that came
    from the prior snapshot instead of being recomputed (``"technologies"``,
    ``"dependency_files"``). Git state is *never* served from the snapshot — it
    is re-read live on every refresh; the ``git`` summaries in
    ``descriptor.repositories`` are as fresh as the refresh that wrote them.
    """

    schema: str = INTEL_SCHEMA
    producer: Producer
    created_at: str  # first computation of this snapshot line
    updated_at: str  # last refresh
    root: str
    fingerprints: IntelFingerprints
    descriptor: WorkspaceDescriptor
    capability_graph_sha: str | None = None  # last computed graph (reference only)
    reused: list[str] = field(default_factory=list)
    source: str = "scan+git+manifests"  # how the snapshot was produced

    def __post_init__(self) -> None:
        if self.schema != INTEL_SCHEMA:
            raise ContractError(
                f"unsupported schema {self.schema!r}, expected {INTEL_SCHEMA!r}")
        for name in self.fingerprints.__dataclass_fields__:
            value = getattr(self.fingerprints, name)
            if not isinstance(value, str):
                raise ContractError(f"intel fingerprint {name} must be a string")
