"""Explainable specialist recommendation (cycle 16.1, §6.3).

Maps the ``forge/WorkspaceDetection/v1`` tech summary to suggested forges —
always advisory, never an install decision. The mapping is **data-driven**:
core code names no specialist; each suggestion is resolved against the
declared ``technologies`` of the ``theforge/ForgeKnowledge/v1`` packages
bundled in ``forge-knowledge/`` (a new specialist onboards by shipping a
package, never by editing this file).

Deterministic rules, all explainable:

- a forge *matches* when detected techs intersect its declared technologies
  (normalized: lower-case, `` ``/``_`` → ``-``);
- *specific* matches are those outside the generic language/runtime set —
  ``python`` alone never makes an API specialist primary;
- forges whose declared ``family`` is a companion surface (verification,
  observability, code navigation, session bridges) are ``aux`` — useful
  alongside a primary, never the primary pick for a workspace;
- a suggestion is ``primary`` when no other eligible forge's specific
  matched set strictly dominates it — disjoint domains can both be
  primary (an API backend and its Terraform stack);
- tied top contenders (``pyspark`` alone → the cloud-specific Spark
  specialists) become ``alternatives`` — ambiguity is named, never guessed.

Every row carries its ``evidence`` (``member:tech`` attributions), a
``confidence`` derived from the detection evidence, and a ``reason``
assembled from the package's declared surface. The ``choices`` block
mirrors the setup options — ``recommended`` / ``all`` / ``manual`` /
``keep-existing`` (the default): every choice reversible, none applied
implicitly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final

if TYPE_CHECKING:  # pragma: no cover - typing only
    from theforge.contracts.knowledge import ForgeKnowledge

RECOMMENDATION_SCHEMA: Final = "forge/SpecialistRecommendation/v1"

MAX_EVIDENCE: Final = 4
MAX_AUX: Final = 4

#: Techs that name a language/runtime, not a specialist domain — they never
#: drive a primary pick by themselves (a bare ``python`` project is not an
#: API-engineering problem). Generic, provider-free vocabulary.
_GENERIC_TECHS: Final = frozenset(
    {
        "python",
        "javascript",
        "typescript",
        "node",
        "java",
        "dotnet",
        "go",
        "rust",
        "shell",
        "frontend",
    }
)

#: Declared families that are companion surfaces — they augment a primary
#: specialist (review, observability, navigation, host bridges) and are
#: therefore suggested as ``aux`` whenever they match.
_AUX_FAMILIES: Final = frozenset(
    {"verification", "observability", "code-intelligence", "agent-session-bridge"}
)

_CONFIDENCE_RANK: Final = {"low": 0, "medium": 1, "high": 2}

_CHOICES: Final = (
    {"id": "recommended", "description": "activate the suggested specialists"},
    {"id": "all", "description": "activate every registered specialist"},
    {"id": "manual", "description": "pick specialists one by one"},
    {"id": "keep-existing", "description": "leave the current selection unchanged"},
)


def _norm(token: str) -> str:
    return token.strip().lower().replace(" ", "-").replace("_", "-")


def _packages() -> dict[str, ForgeKnowledge]:
    """Bundled bootstrap knowledge — the declared surface each suggestion
    is built from. An absent directory means an empty ecosystem."""
    from theforge import knowledge

    return knowledge.load_all()


def _tech_index(
    detection: dict[str, Any],
) -> tuple[dict[str, list[str]], dict[str, str], set[str]]:
    """tech → member attributions, tech → best evidence confidence, all techs."""
    attribution: dict[str, list[str]] = {}
    confidence: dict[str, str] = {}
    for member in detection.get("members") or []:
        path = str(member.get("path") or "?")
        for tech in member.get("techs") or []:
            attribution.setdefault(str(tech), []).append(path)
        for ev in member.get("evidence") or []:
            tech = str(ev.get("tech") or "")
            conf = str(ev.get("confidence") or "low")
            if _CONFIDENCE_RANK.get(conf, 0) > _CONFIDENCE_RANK.get(confidence.get(tech, "low"), 0):
                confidence[tech] = conf
    return attribution, confidence, set(attribution)


def _evidence_for(techs: set[str], attribution: dict[str, list[str]]) -> list[str]:
    return sorted({f"{p}:{t}" for t in techs for p in attribution.get(t, ())})[:MAX_EVIDENCE]


def _row(
    forge_id: str,
    *,
    role: str,
    confidence: str,
    reason: str,
    evidence: list[str],
    installed: bool,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "forge_id": forge_id,
        "confidence": confidence,
        "reason": reason,
        "evidence": evidence,
        "installed": installed,
    }
    if role != "candidate":
        row["role"] = role
    return row


def recommend_specialists(
    detection: dict[str, Any],
    registered: tuple[str, ...] | list[str] = (),
    *,
    packages: dict[str, ForgeKnowledge] | None = None,
) -> dict[str, Any]:
    """``forge/SpecialistRecommendation/v1`` for a detection document.

    ``registered`` = forge ids installed today (bootstrap registry) —
    suggestions still name unregistered forges; ``installed`` says which
    could be activated in this run. ``packages`` is injectable for tests;
    by default the bundled ``forge-knowledge/`` packages are used.
    """
    attribution, tech_confidence, techs = _tech_index(detection)
    registered_set = {str(fid) for fid in registered}
    known = packages if packages is not None else _packages()

    matched_by_forge: dict[str, set[str]] = {}
    specific_by_forge: dict[str, set[str]] = {}
    aux_forge_ids: set[str] = set()
    for fid, pkg in known.items():
        declared = {_norm(t) for t in pkg.technologies}
        matched = techs & declared
        if not matched:
            continue
        matched_by_forge[fid] = matched
        if pkg.family in _AUX_FAMILIES:
            aux_forge_ids.add(fid)
            continue
        specific_by_forge[fid] = matched - _GENERIC_TECHS

    suggested: list[dict[str, Any]] = []
    alternatives: list[dict[str, Any]] = []

    # Primary race: eligible = specific match outside aux families. A forge
    # is primary iff no other's specific set strictly dominates it; equal
    # top sets are ambiguity → alternatives.
    eligible = {fid: spec for fid, spec in specific_by_forge.items() if spec}
    for fid in sorted(eligible):
        spec = eligible[fid]
        dominators = [other for other, o_spec in eligible.items() if other != fid and spec < o_spec]
        evidence = _evidence_for(spec, attribution)
        conf = max(
            (tech_confidence.get(t, "low") for t in spec),
            key=lambda c: _CONFIDENCE_RANK.get(c, 0),
        )
        if dominators:
            alternatives.append(
                _row(
                    fid,
                    role="candidate",
                    confidence="medium",
                    reason=(
                        f"specific match {sorted(spec)} is a subset of "
                        f"{dominators[0]!r}'s evidence — viable if the "
                        "estate differs"
                    ),
                    evidence=evidence,
                    installed=fid in registered_set,
                )
            )
            continue
        tied = [other for other, o_spec in eligible.items() if other != fid and spec == o_spec]
        if tied:
            alternatives.append(
                _row(
                    fid,
                    role="candidate",
                    confidence="medium",
                    reason=(
                        f"specific match {sorted(spec)} tied with "
                        f"{sorted(tied)} — provider undetermined"
                    ),
                    evidence=evidence,
                    installed=fid in registered_set,
                )
            )
            continue
        suggested.append(
            _row(
                fid,
                role="primary",
                confidence=conf,
                reason=f"declared technologies matched: {sorted(spec)}",
                evidence=evidence,
                installed=fid in registered_set,
            )
        )

    # Aux: companion families that matched anything (review, observability,
    # navigation). A bare language/runtime overlap is never enough to name
    # a domain specialist — the suggestion would be noise. Bounded.
    aux_candidates = sorted(
        aux_forge_ids,
        key=lambda fid: (-len(matched_by_forge[fid]), fid),
    )
    for fid in aux_candidates[:MAX_AUX]:
        matched = matched_by_forge[fid]
        suggested.append(
            _row(
                fid,
                role="aux",
                confidence="low",
                reason="companion surface",
                evidence=_evidence_for(matched, attribution),
                installed=fid in registered_set,
            )
        )

    limitations = list(detection.get("limitations") or [])
    if not techs:
        limitations.append("no technology evidence — recommendation is empty, never a guess")
    return {
        "schema": RECOMMENDATION_SCHEMA,
        "suggested": suggested,
        "alternatives": alternatives,
        "choices": list(_CHOICES),
        "default_choice": "keep-existing",
        "note": "advisory only — the suggestion never installs or activates by itself",
        "limitations": limitations,
    }


__all__ = ["RECOMMENDATION_SCHEMA", "recommend_specialists"]
