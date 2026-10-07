"""Adaptive strategy: shadow champion/challenger recommendation (Cycle 4, Wave H).

History-aware, advisory-only (§51-55, §102-103): when measured history clearly
prefers a provider other than the selected one, the decision carries a
``ShadowRecommendation`` — *candidate*, never an executed alternative, and
never a silent promotion. The promotion bar is evidence-shaped:

- enough observations: challenger maturity ``warming``/``mature`` (cold
  history never advises — no acting on one or two runs);
- quality not degraded: verified-run rate at least the incumbent's;
- cost/context improvement observed: strictly lower average context bytes
  when the incumbent has comparable history (when the incumbent has *no*
  history, any verified challenger history qualifies — the gap itself is
  the evidence).

Everything is scoped by surface fingerprint: a provider that changed its
surface starts a fresh history and cannot borrow the old numbers.
"""

from theforge.contracts.performance import (
    ProviderCapabilityPerformance,
    ProviderPerformance,
)
from theforge.contracts.routing import ShadowRecommendation

__all__ = ["shadow_recommendation"]


def _entry(performance: ProviderPerformance, provider: str, capability: str,
           surface: str | None) -> ProviderCapabilityPerformance | None:
    return next((e for e in performance.entries
                 if e.provider == provider and e.capability == capability
                 and e.surface == surface), None)


def _verified_rate(entry: ProviderCapabilityPerformance) -> float:
    return entry.verified_runs / entry.runs if entry.runs else 0.0


def _avg_context(entry: ProviderCapabilityPerformance) -> float:
    return entry.context_bytes / entry.runs if entry.runs else float("inf")


def shadow_recommendation(
    performance: ProviderPerformance | None, *,
    selected_provider: str, capability: str, selected_surface: str | None,
    rival_surfaces: dict[str, str | None],
) -> ShadowRecommendation | None:
    """The history-preferred challenger for ``capability``, or None.

    ``rival_surfaces`` maps each non-selected candidate provider to the
    surface fingerprint it would run against — comparison happens inside the
    surface scope only.
    """
    if performance is None or not rival_surfaces:
        return None
    # Lazy: negotiation pulls the registry layer (see observations.py).
    import theforge.registry  # noqa: F401
    from theforge.negotiation import maturity

    incumbent = _entry(performance, selected_provider, capability,
                       selected_surface)
    qualified: list[tuple[tuple[float, ...], str, ProviderCapabilityPerformance]] = []
    for provider in sorted(rival_surfaces):
        if provider == selected_provider:
            continue
        entry = _entry(performance, provider, capability,
                       rival_surfaces[provider])
        if entry is None or entry.runs == 0:
            continue
        state = maturity(performance, provider, capability, entry.surface)
        if state not in ("warming", "mature"):
            continue  # cold/absent history never advises (§55)
        if incumbent is not None and incumbent.runs > 0:
            if _verified_rate(entry) < _verified_rate(incumbent):
                continue  # quality regression — no recommendation
            if _avg_context(entry) >= _avg_context(incumbent):
                continue  # no observed cost/context improvement
        elif entry.verified_runs == 0:
            continue  # challenger has runs but none verified — no evidence
        qualified.append(
            (performance.score(provider, capability, entry.surface),
             provider, entry))
    if not qualified:
        return None
    # Best measured score wins; provider id breaks ties (deterministic).
    qualified.sort(key=lambda item: (tuple(-v for v in item[0]), item[1]))
    _, provider, challenger = qualified[0]
    state = maturity(performance, provider, capability, challenger.surface)
    assert state in ("warming", "mature")
    evidence = [f"runs {challenger.runs} ({state})"]
    if incumbent is not None and incumbent.runs > 0:
        evidence.append(f"verified_rate {_verified_rate(challenger):.2f} vs "
                        f"{_verified_rate(incumbent):.2f}")
        evidence.append(f"avg context_bytes {_avg_context(challenger):.0f} vs "
                        f"{_avg_context(incumbent):.0f}")
    else:
        evidence.append(f"verified_rate {_verified_rate(challenger):.2f} "
                        f"— incumbent has no measured history on this surface")
    return ShadowRecommendation(
        provider=provider, capability=capability, maturity=state,
        evidence=evidence)
