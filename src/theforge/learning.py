"""Learning v2 — governed strategy-policy lifecycle (Cycle 5, Wave Q/R).

The only channel by which experiment outcomes influence routing is a
``StrategyPolicy`` minted here. ``promote_experiment`` requires:

- the experiment in ``eligible_for_review`` state (both arms observed,
  quality gates held, a measured economy improvement — see
  ``adaptive.advance_experiment``), and
- an explicit ``approval_sha256`` — the hash of the operator approval
  artifact. Auto-promotion does not exist (§105); the returned experiment
  is the caller's promoted record, carrying the approval hash so the
  contract-level gate (``promoted`` requires ``approval_sha256``) holds.

Policies are scoped to the exact surface they were measured on: a surface
change makes them non-authoritative (``policy_applies`` returns False), and
``refresh_policies`` marks them ``stale`` — history is never silently reused.
"""

from collections.abc import Mapping, Sequence
from dataclasses import replace
from statistics import median

from theforge.contracts.adaptive import StrategyExperiment
from theforge.contracts.canonical import sha256_of, utc_now
from theforge.contracts.observation import ExecutionObservation
from theforge.contracts.strategy import StrategyPolicy
from theforge.meta import PRODUCER

__all__ = [
    "active_policies",
    "policy_applies",
    "preferred_providers",
    "promote_experiment",
    "refresh_policies",
]


def promote_experiment(
    experiment: StrategyExperiment,
    evaluation: Sequence[ExecutionObservation],
    *,
    approval_sha256: str,
) -> tuple[StrategyExperiment, StrategyPolicy]:
    """Promote an eligible experiment into a governed ``StrategyPolicy``.

    Returns ``(promoted_experiment, policy)``; raises ``ValueError`` if the
    experiment is not eligible — an ineligible experiment cannot become a
    policy regardless of who approves it.
    """
    if experiment.state != "eligible_for_review":
        raise ValueError(
            f"experiment {experiment.experiment_id!r} is {experiment.state!r}, "
            "not eligible_for_review"
        )
    scoped = [
        item
        for item in evaluation
        if item.provider == experiment.challenger
        and item.capability == experiment.capability
        and item.task_family == experiment.task_family
        and item.surface_fingerprint == experiment.challenger_surface
    ]
    # Sample: prefer re-enumerated evaluation runs; fall back to the count the
    # experiment itself measured (advance_experiment already gated it).
    sample = len(scoped) or experiment.observations
    metrics: dict[str, float] = {
        "runs": float(sample),
        "verified_rate": (
            sum(1 for i in scoped if i.verification == "passed") / len(scoped) if scoped else 0.0
        ),
        "delivered_rate": (
            sum(1 for i in scoped if i.status in ("ok", "partial")) / len(scoped) if scoped else 0.0
        ),
    }
    for name in ("wall_time_ms", "context_bytes", "cost_usd"):
        values = [float(v) for i in scoped if (v := getattr(i, name)) is not None]
        if values and len(values) == len(scoped):
            metrics[f"median_{name}"] = float(median(values))
    promoted = replace(experiment, state="promoted", approval_sha256=approval_sha256)
    policy = StrategyPolicy(
        producer=PRODUCER,
        created_at=utc_now(),
        id=sha256_of(
            {
                "capability": experiment.capability,
                "task_family": experiment.task_family,
                "provider": experiment.challenger,
                "surface": experiment.challenger_surface,
                "experiment": experiment.experiment_id,
            }
        ),
        capability=experiment.capability,
        task_family=experiment.task_family,
        surface_fingerprint=experiment.challenger_surface,
        prefer=[experiment.challenger],
        experiment_id=experiment.experiment_id,
        approval_sha256=approval_sha256,
        sample_runs=sample,
        metrics=metrics,
        valid_from=utc_now(),
        limitations=[
            f"measured on challenger surface {experiment.challenger_surface}; "
            "a surface change makes this policy non-authoritative"
        ],
    )
    return promoted, policy


def policy_applies(
    policy: StrategyPolicy,
    *,
    capability: str,
    surface_fingerprint: str | None,
    task_family: str | None = None,
    at: str | None = None,
) -> bool:
    """Whether a policy is authoritative for this negotiation — exact scope
    match only. A stale or out-of-scope policy never influences ordering."""
    if policy.stale or policy.capability != capability:
        return False
    if policy.surface_fingerprint != surface_fingerprint:
        return False
    if policy.task_family is not None and policy.task_family != task_family:
        return False
    return not (policy.valid_until is not None and at is not None and at > policy.valid_until)


def active_policies(
    policies: Sequence[StrategyPolicy],
    *,
    capability: str,
    surface_fingerprint: str | None,
    task_family: str | None = None,
    at: str | None = None,
) -> list[StrategyPolicy]:
    """The applicable policies, deterministically ordered (valid_from, id)."""
    return sorted(
        (
            p
            for p in policies
            if policy_applies(
                p,
                capability=capability,
                surface_fingerprint=surface_fingerprint,
                task_family=task_family,
                at=at,
            )
        ),
        key=lambda p: (p.valid_from, p.id),
    )


def preferred_providers(
    policies: Sequence[StrategyPolicy],
    *,
    capability: str,
    surface_fingerprint: str | None,
    task_family: str | None = None,
    at: str | None = None,
) -> list[str]:
    """The preference ladder from active policies, order preserved.

    Each policy contributes its ``prefer`` list; duplicates collapse keeping
    the earliest position. Empty when no policy applies — absence is neutral,
    never a negative signal.
    """
    seen: dict[str, None] = {}
    for policy in active_policies(
        policies,
        capability=capability,
        surface_fingerprint=surface_fingerprint,
        task_family=task_family,
        at=at,
    ):
        for provider in policy.prefer:
            seen.setdefault(provider)
    return list(seen)


def refresh_policies(
    policies: Sequence[StrategyPolicy],
    current_surfaces: Mapping[str, str],
) -> list[StrategyPolicy]:
    """Mark policies stale whose recorded surface no longer matches the
    provider's *current* surface (``current_surfaces``: provider → fingerprint).

    A policy never regains freshness by accident: once ``stale``, it stays
    stale — a new measurement produces a new policy, per §117.
    """
    refreshed: list[StrategyPolicy] = []
    for policy in policies:
        if policy.stale:
            refreshed.append(policy)
            continue
        providers = policy.prefer
        current = {current_surfaces.get(p) for p in providers}
        if len(providers) == 1 and policy.surface_fingerprint not in current:
            refreshed.append(
                replace(
                    policy,
                    stale=True,
                    limitations=[
                        *policy.limitations,
                        "surface fingerprint changed; policy marked stale",
                    ],
                )
            )
        else:
            refreshed.append(policy)
    return refreshed
