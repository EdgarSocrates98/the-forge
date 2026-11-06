"""Evidence-based conformance for agent rosters exposed by a Forge checkout.

The ``forge.agentic.json`` manifest is declarative.  A roster on disk is
evidence about what the checkout can actually render, not a second registry.
This module deliberately returns ``UNKNOWN`` when no canonical roster is
available and never upgrades a specialist's trust or routing state.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from theforge.contracts.specialist import AgenticManifest

ROSTER_STATES = ("CONFORMANT", "DRIFT", "STALE", "CONFLICT", "UNKNOWN")

# These are repository-native rosters.  Host projections (.codex/.claude) are
# intentionally not authorities: they are generated/installed views of the
# same agent definition and may contain host-only helpers.
CANONICAL_ROSTER_DIRS = (Path("agentic/agents"), Path("agents"))
ROSTER_SUFFIXES = frozenset({".md", ".toml"})


@dataclass(frozen=True)
class RosterSource:
    """One on-disk roster and the identifiers observed in it."""

    path: str
    agents: tuple[str, ...]


@dataclass(frozen=True)
class RosterConformance:
    """Deterministic projection of manifest declarations versus roster evidence."""

    provider: str
    state: str
    declared: tuple[str, ...]
    observed: tuple[str, ...]
    sources: tuple[RosterSource, ...]
    evidence: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.state not in ROSTER_STATES:
            raise ValueError(f"unknown roster conformance state: {self.state!r}")

    @property
    def routable(self) -> bool:
        """Roster conformance is never a routing grant; only exact evidence is usable."""

        return self.state == "CONFORMANT"

    def as_dict(self) -> dict[str, object]:
        """Stable JSON-shaped projection for catalog/Portal consumers."""

        return {
            "provider": self.provider,
            "state": self.state,
            "declared": list(self.declared),
            "observed": list(self.observed),
            "sources": [
                {"path": source.path, "agents": list(source.agents)} for source in self.sources
            ],
            "evidence": list(self.evidence),
            "routable": self.routable,
        }


def _files_in(path: Path) -> tuple[str, ...]:
    if not path.is_dir():
        return ()
    return tuple(
        sorted(
            item.stem
            for item in path.iterdir()
            if (
                item.is_file()
                and item.suffix.lower() in ROSTER_SUFFIXES
                and not item.name.startswith(".")
            )
        )
    )


def _declared(manifest: AgenticManifest) -> tuple[str, ...]:
    return tuple(sorted(set(manifest.agents) | set(manifest.coordinators)))


def inspect_roster(
    manifest: AgenticManifest,
    checkout: Path,
    *,
    roster_dirs: tuple[Path, ...] = CANONICAL_ROSTER_DIRS,
) -> RosterConformance:
    """Compare a manifest with canonical repository rosters.

    State meanings:

    * ``CONFORMANT`` — every declared id equals the observed roster;
    * ``DRIFT`` — evidence exists but declarations omit or add ids;
    * ``STALE`` — a declared id has no corresponding roster file;
    * ``CONFLICT`` — two canonical roster sources disagree;
    * ``UNKNOWN`` — no canonical roster exists, so no claim is made.

    A mismatch is evidence for catalog display and review.  It is not a
    capability, health, or trust decision.
    """

    checkout = checkout.resolve()
    declared = _declared(manifest)
    sources = tuple(
        RosterSource(
            str((checkout / relative).relative_to(checkout)),
            _files_in(checkout / relative),
        )
        for relative in roster_dirs
        if (checkout / relative).is_dir()
    )
    if not sources:
        return RosterConformance(
            provider=manifest.provider,
            state="UNKNOWN",
            declared=declared,
            observed=(),
            sources=(),
            evidence=("no canonical repository roster was found",),
        )

    source_sets = {source.agents for source in sources}
    observed = tuple(sorted(set().union(*(set(source.agents) for source in sources))))
    if len(source_sets) > 1:
        state = "CONFLICT"
        evidence = ("canonical roster sources disagree",)
    elif set(declared) - set(observed):
        state = "STALE"
        evidence = ("manifest declares ids absent from the canonical roster",)
    elif declared == observed:
        state = "CONFORMANT"
        evidence = ("manifest and canonical roster are equal",)
    else:
        state = "DRIFT"
        evidence = ("canonical roster contains ids absent from the manifest",)
    return RosterConformance(
        provider=manifest.provider,
        state=state,
        declared=declared,
        observed=observed,
        sources=sources,
        evidence=evidence,
    )


__all__ = [
    "CANONICAL_ROSTER_DIRS",
    "ROSTER_STATES",
    "RosterConformance",
    "RosterSource",
    "inspect_roster",
]
