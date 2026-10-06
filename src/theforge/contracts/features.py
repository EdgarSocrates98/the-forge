"""Provider protocol features: the negotiated vocabulary of ``manifest.features``.

A feature id is ``<name>/v<major>`` — namespaced, versioned, additive. The core
never assumes a provider supports a feature: absent means *not negotiated*, and
the call site degrades (a limitation, a skipped step, a narrower request) —
never crashes. Well-formed ids this core does not know are ignored, so a newer
provider can declare ``delta/v2`` against an older core.

``supports`` resolves a feature against the manifest twice: the explicit
``features`` list, and the features *implied* by other declared fields — a
capability with ``accepts_handoff`` already states ``handoff/v1``, an ``ops``
list with ``verify`` already states ``verify/v1``. Implied features keep
pre-features manifests fully describable and make a contradictory declaration
(``features`` without ``handoff/v1`` plus ``accepts_handoff``) resolve to the
more specific capability-level statement.
"""

from typing import Final

from theforge.contracts.manifest import ForgeManifest

# The vocabulary this core knows. Documented in docs/versioning.md; a feature
# absent from this set is simply never asked for.
HANDOFF: Final = "handoff/v1"                # consumes Handoff in ExecuteRequest
VERIFY: Final = "verify/v1"                  # answers the ``verify`` op
PLAN_PROPOSAL: Final = "plan-proposal/v1"    # answers plan purpose="proposal"
RESOLVE: Final = "resolve/v1"                # answers ``resolve`` requests
SEMANTIC_HANDOFF: Final = "semantic-handoff/v1"  # structured semantic handoff items
ECONOMY_RECEIPT: Final = "economy-receipt/v1"  # economy data in results
TRACE_REF: Final = "trace-ref/v1"            # emits linkable trace references
RESUME: Final = "resume/v1"                  # resume/partial re-execution aware
DELTA: Final = "delta/v1"                    # accepts/produces delta handoffs
GRAPH_REFS: Final = "graph-refs/v1"          # emits graph reference artifacts

KNOWN_FEATURES: Final = frozenset({
    HANDOFF, VERIFY, PLAN_PROPOSAL, RESOLVE, SEMANTIC_HANDOFF, ECONOMY_RECEIPT,
    TRACE_REF, RESUME, DELTA, GRAPH_REFS,
})


def implied_features(manifest: ForgeManifest) -> frozenset[str]:
    """Features implied by the manifest's other declared fields."""
    implied: set[str] = set()
    if "verify" in manifest.ops:
        implied.add(VERIFY)
    if "plan" in manifest.ops and any(c.proposes_plans for c in manifest.capabilities):
        implied.add(PLAN_PROPOSAL)
    if "resolve" in manifest.ops and any(c.resolves_ambiguity
                                       for c in manifest.capabilities):
        implied.add(RESOLVE)
    if any(c.accepts_handoff for c in manifest.capabilities):
        implied.add(HANDOFF)
    return frozenset(implied)


def supported_features(manifest: ForgeManifest) -> frozenset[str]:
    """Declared ∪ implied — the features a caller may rely on."""
    return frozenset(manifest.features) | implied_features(manifest)


def supports(manifest: ForgeManifest, feature: str) -> bool:
    """Whether the provider's declared surface negotiates ``feature``."""
    return feature in supported_features(manifest)
