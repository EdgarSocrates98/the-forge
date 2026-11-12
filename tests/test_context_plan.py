"""Progressive context routing (Onda 08): L1→L2→L3 budgeted plan."""
from __future__ import annotations

import json
from pathlib import Path

from theforge.context.plan import _terms, plan_context
from theforge.context.resources import ResourceResolver, discover_roots


def _root(base: Path, fid: str, resources: list[dict]) -> Path:
    base.mkdir(parents=True, exist_ok=True)
    (base / "forge.agentic.json").write_text(
        json.dumps({"forge_id": fid, "resources": resources}), encoding="utf-8"
    )
    return base


def _resolver(tmp: Path) -> ResourceResolver:
    a = _root(
        tmp / "a",
        "forge-a",
        [
            {"id": "spark-tuning", "kind": "skill",
             "location": "skills/spark-tuning/SKILL.md",
             "description": "AWS Glue PySpark tuning", "tags": ["spark", "aws"]},
        ],
    )
    (a / "skills/spark-tuning").mkdir(parents=True)
    (a / "skills/spark-tuning/SKILL.md").write_bytes(b"# spark tuning\n" * 10)
    b = _root(
        tmp / "b",
        "forge-b",
        [
            {"id": "api-design", "kind": "skill",
             "location": "skills/api-design/SKILL.md",
             "description": "REST OpenAPI design", "tags": ["api"]},
            {"id": "gone", "kind": "skill", "location": None,
             "availability": "unavailable",
             "unavailable_reason": "not shipped"},
        ],
    )
    return ResourceResolver(
        discover_roots(None, explicit=[("forge-a", a), ("forge-b", b)],
                       scan_installed=False)
    )


def test_plan_routes_primary_and_bounded_l3(tmp_path: Path) -> None:
    plan = plan_context("tune AWS Glue PySpark job", _resolver(tmp_path))
    assert plan.level2_forge == "forge-a"
    assert plan.level3_refs == ["forge-a:spark-tuning"]
    assert plan.est_level3_bytes <= plan.budget_bytes
    assert plan.metrics["unavailable_skipped"] == 1


def test_plan_no_match_is_honest(tmp_path: Path) -> None:
    plan = plan_context("kubernetes gitops flux", _resolver(tmp_path))
    assert plan.level2_forge is None
    assert plan.level3_refs == []


def test_terms_stopwords() -> None:
    assert "the" not in _terms("the spark job")
    assert "spark" in _terms("the spark job")
