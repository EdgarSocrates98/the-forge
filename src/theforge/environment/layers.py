"""Layered doctor model (cycle 16.1, FRENTE F §10.1).

``theforge doctor`` already reported a flat check list; §10.1 asks for the
diagnosis organized by *layer* so a failure is located, not just listed.
The 20 named layers below are the report contract — every layer appears in
``layers`` in this order, with the checks that belong to it; a layer with
no checks reports ``not_applicable`` rather than disappearing.

The flat ``checks`` list is unchanged (backward compatibility): layers are
a projection over check names, never a second diagnostic engine.
"""

from __future__ import annotations

from typing import Any, Final

LAYER_ORDER: Final[tuple[str, ...]] = (
    "runtime",  # 1. os/arch/python/git the engine itself needs
    "version",  # 2. theforge + recorded install versions
    "registry",  # 3. provider records, trust, health, account env
    "workspace-root",  # 4. .forge presence + writability
    "members",  # 5. workspace member repos
    "contracts",  # 6. .forge/context registry/routing validity
    "skills",  # 7. installed skill catalogs
    "agents",  # 8. installed agent specs
    "knowledge",  # 9. knowledge payloads + context layer
    "rules",  # 10. executable rule catalogs
    "evals",  # 11. eval definitions
    "mcp",  # 12. .mcp.json namespacing/duplicates/launch + probe
    "hosts",  # 13. host detection + declared capabilities
    "secrets",  # 14. secret-shaped files (names only — never content)
    "ownership",  # 15. install ledger ownership
    "drift",  # 16. ledger vs. filesystem drift
    "dependencies",  # 17. declared forge dependencies
    "receipts",  # 18. install receipts
    "context",  # 19. .forge/context capability layer
    "ci",  # 20. CI/integration environment
)

_LAYER_OF: Final[dict[str, str]] = {
    "os": "runtime",
    "architecture": "runtime",
    "python": "runtime",
    "git": "runtime",
    "version": "version",
    "account-environment": "registry",
    "workspace": "workspace-root",
    "registry": "registry",
    "providers": "registry",
    "members": "members",
    "contracts": "contracts",
    "skills": "skills",
    "agents": "agents",
    "knowledge": "knowledge",
    "rules": "rules",
    "evals": "evals",
    "mcp": "mcp",
    "host": "hosts",
    "hosts": "hosts",
    "secrets": "secrets",
    "ownership": "ownership",
    "drift": "drift",
    "dependencies": "dependencies",
    "receipts": "receipts",
    "context": "context",
    "ci": "ci",
}


def layer_of(check_name: str) -> str:
    """The layer a check belongs to (prefix rules, deterministic)."""
    if check_name.startswith("provider:"):
        return "registry"
    if check_name.startswith("mcp-") or check_name.startswith("mcp:"):
        return "mcp"
    if check_name.startswith("drift:"):
        return "drift"
    if check_name.startswith("member:"):
        return "members"
    if check_name.startswith("secret:"):
        return "secrets"
    if check_name.startswith("receipt:"):
        return "receipts"
    if check_name.startswith("version:"):
        return "version"
    if check_name.startswith("skill:"):
        return "skills"
    if check_name.startswith("agent:"):
        return "agents"
    return _LAYER_OF.get(check_name, "runtime")


def group_layers(checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Project flat ``checks`` into the 20-layer ordered report.

    ``status`` is the worst status among the layer's checks
    (``fail`` > ``warn`` > ``ok``); an empty layer is ``not_applicable``.
    """
    by_layer: dict[str, list[dict[str, Any]]] = {name: [] for name in LAYER_ORDER}
    for check in checks:
        by_layer.setdefault(layer_of(str(check.get("name", ""))), []).append(check)
    layers: list[dict[str, Any]] = []
    for index, name in enumerate(LAYER_ORDER, start=1):
        layer_checks = by_layer.get(name, [])
        status = "ok"
        for check in layer_checks:
            if check.get("status") == "fail":
                status = "fail"
                break
            if check.get("status") == "warn":
                status = "warn"
        if not layer_checks:
            status = "not_applicable"
        layers.append(
            {
                "index": index,
                "name": name,
                "status": status,
                "checks": [str(c.get("name")) for c in layer_checks],
            }
        )
    return layers


__all__ = ["LAYER_ORDER", "group_layers", "layer_of"]
