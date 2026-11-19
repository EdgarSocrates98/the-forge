"""Setup option resolution (cycle 16.1, §6.6 presets + §6.7 declarative config).

One place decides what ``theforge setup`` resolves to, with explicit,
visible precedence:

    CLI flag  >  --preset  >  forge.workspace.yaml ``forge:`` block  >  default

Presets are transparent aliases onto the existing ``--profile`` /
``--gateway-profile`` vocabulary — they never reinterpret ``full`` or
``deep``, and the resolved mapping is reported in the plan so the user
sees it *before* approving. An explicit flag that contradicts the preset
is a ``UsageError``, never a silent override.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

from theforge.errors import UsageError
from theforge.workspace.config import WorkspaceConfig

PRESETS: Final[dict[str, tuple[str | None, str | None]]] = {
    "economy": ("minimal", "economy"),
    "balanced": ("recommended", "balanced"),
    "full": ("full", "deep"),
    # ``custom`` = "take my explicit flags" — it must not invent values.
    "custom": (None, None),
}

_SPECIALIST_MODES: Final = ("all", "recommended", "manual")


@dataclass(frozen=True)
class SetupResolution:
    """Resolved setup choices plus the receipt-facing provenance doc."""

    profile: str
    gateway_profile: str | None
    host: str
    forges: tuple[str, ...] | None  # specialist filter; None = every registered
    specialists_mode: str | None  # declared mode (recommended resolved by caller)
    doc: dict[str, Any]
    warnings: tuple[str, ...] = ()


def _pick(
    flag: str | None,
    preset_value: str | None,
    config_value: str | None,
    default: str | None,
    name: str,
    preset: str | None,
    doc: dict[str, Any],
) -> tuple[str | None, str | None]:
    """flag > preset > config > default; records the provenance in ``doc``."""
    if flag is not None:
        if preset is not None and preset_value is not None and flag != preset_value:
            raise UsageError(
                f"--{name} {flag!r} conflicts with --preset {preset} "
                f"(which resolves to {preset_value!r}); drop the flag or the preset"
            )
        doc[name] = {"value": flag, "source": "flag"}
        return flag, "flag"
    if preset_value is not None:
        doc[name] = {"value": preset_value, "source": f"preset:{preset}"}
        return preset_value, "preset"
    if config_value is not None:
        doc[name] = {"value": config_value, "source": "forge.workspace.yaml"}
        return config_value, "config"
    doc[name] = {"value": default, "source": "default"}
    return default, "default"


def resolve(
    *,
    preset: str | None,
    profile: str | None,
    gateway_profile: str | None,
    host: str | None,
    forge: str | None,
    config: WorkspaceConfig | None,
) -> SetupResolution:
    """Resolve setup choices; raises ``UsageError`` on preset/flag conflicts."""
    if preset is not None and preset not in PRESETS:
        raise UsageError(f"--preset {preset!r}; expected one of {sorted(PRESETS)}")
    preset_profile, preset_gateway = PRESETS.get(preset or "", (None, None))
    if preset == "custom" and profile is None and gateway_profile is None:
        raise UsageError(
            "--preset custom means 'use my explicit flags' — "
            "pass --profile and/or --gateway-profile with it"
        )

    resolution_doc: dict[str, Any] = {}
    cfg_profile = config.installation_profile if config else None
    cfg_gateway = config.gateway_profile if config else None
    profile_v, _ = _pick(
        profile,
        preset_profile,
        cfg_profile,
        "recommended",
        "profile",
        preset,
        resolution_doc,
    )
    gateway_v, _ = _pick(
        gateway_profile,
        preset_gateway,
        cfg_gateway,
        None,
        "gateway-profile",
        preset,
        resolution_doc,
    )

    warnings: list[str] = list(config.warnings) if config else []

    # host: explicit flag > declared hosts > "all". An empty declared list
    # is an explicit "no host integration" → "none".
    host_v = host
    host_source = "flag" if host else None
    if host_v is None and config is not None and config.hosts is not None:
        host_v = ",".join(config.hosts) if config.hosts else "none"
        host_source = "forge.workspace.yaml"
    if host_v is None:
        host_v = "all"
        host_source = "default"
    resolution_doc["host"] = {"value": host_v, "source": host_source}

    # specialists: explicit --forge wins over any declared mode.
    forges: tuple[str, ...] | None = None
    specialists_mode: str | None = None
    specialists_doc: dict[str, Any] | None = None
    if forge:
        forges = (forge,)
        specialists_doc = {"mode": "manual", "include": [forge], "source": "flag"}
    elif config is not None and config.specialists_mode:
        specialists_mode = config.specialists_mode
        specialists_doc = {
            "mode": specialists_mode,
            "include": list(config.specialists_include),
            "source": "forge.workspace.yaml",
        }
        if specialists_mode == "manual":
            if config.specialists_include:
                forges = config.specialists_include
            else:
                warnings.append(
                    "forge.workspace.yaml: specialists.mode 'manual' with empty "
                    "include — every registered forge stays in scope"
                )
        # "recommended" is resolved by the caller — it needs the detection
        # pass to pick the primary suggestions ∩ registered forges.

    doc: dict[str, Any] = {"resolution": resolution_doc}
    if preset is not None:
        doc["preset"] = {
            "name": preset,
            "resolved": {
                "profile": preset_profile or profile or "recommended",
                "gateway_profile": preset_gateway or gateway_profile,
            },
        }
    if config is not None:
        doc["declarative"] = config.setup_doc()
    if specialists_doc is not None:
        doc["specialists"] = specialists_doc

    return SetupResolution(
        profile=str(profile_v or "recommended"),
        gateway_profile=gateway_v,
        host=host_v,
        forges=forges,
        specialists_mode=specialists_mode,
        doc=doc,
        warnings=tuple(warnings),
    )


__all__ = ["PRESETS", "SetupResolution", "resolve"]
