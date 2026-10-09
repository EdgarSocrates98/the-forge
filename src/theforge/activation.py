"""Host activation planning + receipts (FASE 4 + 8.6).

Activation is verified per component, never assumed from file presence:

- ``skills``/``agents`` are read by hosts at session start or on-demand;
  after install the honest outcome is RESTART_REQUIRED unless the host
  is not the current session (assets exist for the *next* session).
- ``mcp`` stdio servers are spawned per call, so a verified handshake
  justifies ACTIVE_NOW for the MCP component only.
- UNSUPPORTED when the host declares no consumption path.
"""

from __future__ import annotations

from theforge.contracts.specialist import (
    HostActivationPlan,
    HostActivationReceipt,
)

# Components each host can consume at all (declared support, not proof
# of a live session load).
_SUPPORTED_COMPONENTS: dict[str, frozenset[str]] = {
    "claude": frozenset({"skills", "agents", "mcp"}),
    "devin": frozenset({"skills", "agents", "mcp"}),
    "codex": frozenset({"skills", "agents", "mcp"}),
    "copilot": frozenset({"skills", "mcp"}),
}


def build_activation_plan(
    *,
    host: str,
    provider: str,
    scope: str,
    components: list[str],
    writes: list[str],
) -> HostActivationPlan:
    return HostActivationPlan(
        host=host,
        provider=provider,
        scope=scope,
        components=components,
        writes=writes,
        approval_required=bool(writes),
    )


def evaluate_activation(
    plan: HostActivationPlan,
    *,
    host_is_current_session: bool,
    mcp_handshake_passed: bool | None,
) -> HostActivationReceipt:
    """Produce the honest outcome for a plan after install + checks.

    ``mcp_handshake_passed``: None when the specialist has no MCP.
    """
    checks: dict[str, str] = {}
    unsupported = [
        c for c in plan.components if c not in _SUPPORTED_COMPONENTS.get(plan.host, set())
    ]
    for comp in plan.components:
        if comp in unsupported:
            checks[comp] = "UNSUPPORTED"
        elif comp == "mcp":
            if mcp_handshake_passed is True:
                checks[comp] = "PASS"
            elif mcp_handshake_passed is None:
                checks[comp] = "NOT_APPLICABLE"
            else:
                checks[comp] = "FAIL"
        else:
            # files were written by install; load-by-host not observable.
            checks[comp] = "UNVERIFIED"

    if unsupported and all(checks[c] == "UNSUPPORTED" for c in plan.components):
        outcome = "UNSUPPORTED"
    elif checks.get("mcp") == "PASS" and all(
        checks.get(c) in ("PASS", "NOT_APPLICABLE") for c in plan.components
    ):
        # MCP-only activation with a real handshake: consumable now.
        outcome = "ACTIVE_NOW"
    elif checks.get("mcp") == "FAIL":
        outcome = "RESTART_REQUIRED" if host_is_current_session else "RESTART_REQUIRED"
    else:
        outcome = "RESTART_REQUIRED"

    resume: list[str] = []
    if outcome == "RESTART_REQUIRED":
        resume = [
            f"restart the {plan.host} session to load new skills/agents",
            "re-run `theforge specialists status` after restart to confirm",
        ]
    limitations = [
        "host-side loading of skills/agents is not observable offline",
        "ACTIVE_NOW is only claimed for components verified by a live check",
    ]
    return HostActivationReceipt(
        host=plan.host,
        provider=plan.provider,
        scope=plan.scope,
        outcome=outcome,
        checks=checks,
        resume_instructions=resume,
        limitations=limitations,
    )
