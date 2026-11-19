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
from typing import TYPE_CHECKING, Any, Final

from theforge.errors import UsageError
from theforge.workspace.config import WorkspaceConfig

if TYPE_CHECKING:  # pragma: no cover - typing only
    from collections.abc import Iterable

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
            # §4.4 — an empty manual selection stays empty (blocked receipt
            # downstream as ``empty_manual_selection``); it never widens to
            # "activate everything".
            forges = config.specialists_include
            if not config.specialists_include:
                warnings.append(
                    "forge.workspace.yaml: specialists.mode 'manual' with empty "
                    "include — empty selection, nothing will be delegated"
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


def resolve_recommended(
    detection: dict[str, Any],
    registered: Iterable[str],
) -> tuple[tuple[str, ...], str | None]:
    """``specialists.mode: recommended`` → primary suggestions ∩ registry.

    Pure: ``detection``/``registered`` are caller-supplied evidence, so the
    CLI and the wizard resolve identical selections from identical inputs.
    Returns ``(selected, empty_state)`` — ``empty_state`` is the named §4.4
    state when the selection comes out empty (``None`` otherwise):

    - ``no_installed_runtimes``    — primary suggestions exist but none is
      registered (install the runtime via the forge's own CLI first);
    - ``recommendation_ambiguous`` — tied/subset alternatives, no primary —
      ambiguity is named, never guessed;
    - ``no_relevant_recommendation`` — nothing relevant was detected.
    """
    from theforge.workspace.recommend import recommend_specialists

    rec = recommend_specialists(detection, registered=sorted(registered))
    primaries = [s for s in rec.get("suggested") or () if s.get("role") == "primary"]
    selected = tuple(str(s["forge_id"]) for s in primaries if s.get("installed"))
    if selected:
        return selected, None
    if primaries:
        return (), "no_installed_runtimes"
    if rec.get("alternatives"):
        return (), "recommendation_ambiguous"
    return (), "no_relevant_recommendation"


@dataclass(frozen=True)
class WizardResolution:
    """``resolve`` output packaged for the interactive wizard path.

    ``forges``/``doc`` are what ``install_auto(forge=..., setup=...)`` must
    receive so the wizard-approved plan is the CLI plan verbatim; the
    per-field provenance lives in ``doc["resolution"]`` (``flag`` /
    ``preset:<name>`` / ``forge.workspace.yaml`` / ``default``) and in
    ``doc["specialists"]["source"]``.
    """

    resolution: SetupResolution
    forges: tuple[str, ...] | None
    doc: dict[str, Any]
    empty_state: str | None = None  # named §4.4 state when forges == ()


def wizard_defaults(
    *,
    config: WorkspaceConfig | None,
    detection: dict[str, Any] | None = None,
    registered: Iterable[str] = (),
) -> WizardResolution:
    """Resolve what the setup wizard pre-checks — no side effects.

    The wizard path has no flags, so resolution is ``config > detection >
    default``; the operator's answers remain the explicit tier. ``detection``
    and ``registered`` are needed only when the declared mode is
    ``recommended`` — the caller performs that bounded IO and passes the
    result in, keeping this function a pure resolver.
    """
    res = resolve(
        preset=None,
        profile=None,
        gateway_profile=None,
        host=None,
        forge=None,
        config=config,
    )
    forges = res.forges
    doc = res.doc
    empty_state: str | None = None
    if res.specialists_mode == "recommended":
        forges, empty_state = resolve_recommended(detection or {}, registered)
        doc = dict(res.doc)
        specialists = dict(doc.get("specialists") or {})
        specialists["selected"] = list(forges)
        if empty_state is not None:
            specialists["empty_state"] = empty_state
        doc["specialists"] = specialists
    return WizardResolution(resolution=res, forges=forges, doc=doc, empty_state=empty_state)


__all__ = [
    "PRESETS",
    "SetupResolution",
    "WizardResolution",
    "resolve",
    "resolve_recommended",
    "wizard_defaults",
]
