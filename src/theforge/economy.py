"""Economy engine: resolve a run's ``RunBudget`` and boundedly promote it (Wave H).

``resolve_budget`` maps the effective profile to the auditable ``RunBudget``
artifact. When measured complexity outranks an explicitly requested profile
(``--profile economy`` on a ``high`` task), the elastic bounds — context bytes,
files and negotiation rounds — promote **one profile step** (economy→balanced→
max), never beyond ``max`` and never on the fields that widen blast radius
(provider count, wall time, parallelism). ``auto`` needs no promotion: the
complexity assessment already selects the profile itself.
"""

from dataclasses import replace
from typing import Final

from theforge.contracts.budget import RunBudget
from theforge.contracts.canonical import utc_now
from theforge.contracts.complexity import LEVELS, ComplexityAssessment
from theforge.contracts.types import MAX_PARALLEL_NODES, BudgetProfile, Producer
from theforge.meta import PRODUCER
from theforge.profiles import PROFILES, ContextProfile

__all__ = ["resolve_budget"]

# The complexity level a profile typically covers: promotion fires only when the
# measured level ranks strictly above it (max is already the top, never promotes).
_PROFILE_RANK: Final[dict[str, int]] = {
    "economy": LEVELS.index("low"),
    "balanced": LEVELS.index("medium"),
    "max": LEVELS.index("critical"),
}
_NEXT_PROFILE: Final[dict[BudgetProfile, BudgetProfile]] = {
    "economy": "balanced", "balanced": "max"}
# The fields a promotion may raise — elastic context room only.
_PROMOTABLE: Final = ("budget_bytes", "max_files", "negotiation_rounds")


def resolve_budget(
    profile: ContextProfile,
    *,
    run_id: str,
    plan_nodes: int = 0,
    retry_attempts: int = 1,
    assessment: ComplexityAssessment | None = None,
                   producer: Producer = PRODUCER,
                   created_at: str | None = None) -> tuple[ContextProfile, RunBudget]:
    """``(effective profile, RunBudget)`` — the profile possibly promoted one step.

    ``assessment`` is the run's ComplexityAssessment; promotion applies only to
    explicitly requested profiles (``auto`` already follows the assessment) and
    only with measured confidence (``min_confidence`` gates nothing else here —
    the assessment already fell back when unconfident).
    ``plan_nodes`` > 0 marks a plan run: its provider/verification bounds cover
    the nodes, each a child run with its own budget. ``retry_attempts`` is the
    explicit retry-policy ceiling; plan provider-call budget reserves that worst
    case and records the widening in ``adjustments``.
    """
    if retry_attempts < 1:
        raise ValueError("retry_attempts must be >= 1")
    effective = profile
    adjustments: list[str] = []
    nxt_name = _NEXT_PROFILE.get(profile.name)
    # Promote when the assessment's *selected* profile outranks the requested one.
    # ``selected_profile`` already encodes the confidence fallback, so a low-confidence
    # high level can never push the budget past what the evidence supports. Under
    # ``auto`` selected == requested: nothing to promote.
    if (assessment is not None and nxt_name is not None
            and _PROFILE_RANK.get(assessment.selected_profile, -1)
            > _PROFILE_RANK[profile.name]):
        nxt = PROFILES[nxt_name]
        raised = [f"{field} {getattr(profile, field)}→{getattr(nxt, field)}"
                  for field in _PROMOTABLE
                  if getattr(profile, field) != getattr(nxt, field)]
        if raised:
            effective = replace(
                profile,
                **{field: getattr(nxt, field) for field in _PROMOTABLE})
            adjustments.append(
                f"promotion {profile.name}→{nxt_name} (complexity "
                f"{assessment.level}, confidence {assessment.confidence:.2f}): "
                + ", ".join(raised))
    provider_calls = (
        plan_nodes * retry_attempts if plan_nodes else effective.max_providers
    )
    if plan_nodes and retry_attempts > 1:
        adjustments.append(
            f"retry reserve provider_calls {plan_nodes}→{provider_calls} "
            f"(max_attempts {retry_attempts})"
        )
    budget = RunBudget(
        producer=producer, created_at=created_at or utc_now(), run_id=run_id,
        profile=profile.name,
        context_bytes=effective.budget_bytes, max_files=effective.max_files,
        provider_calls=provider_calls,
        semantic_calls=1 if (plan_nodes and effective.name != "economy") else 0,
        verification_calls=plan_nodes if plan_nodes else 1,
        wall_time_s=effective.execute_timeout_s,
        max_parallelism=MAX_PARALLEL_NODES if plan_nodes else 1,
        negotiation_rounds=effective.negotiation_rounds,
        adjustments=adjustments)
    return effective, budget
