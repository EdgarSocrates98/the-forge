"""Context governance (cycle 16.1, FRENTE D §8): selection evidence,
cross-cloud routing, don't-load-everything, budget audit, cache epoch,
and the permanent-context measurement for a 12-forge workspace."""

from __future__ import annotations

import json
import os
from pathlib import Path

from theforge.context.budget import CATEGORY_ORDER, context_budget
from theforge.context.fingerprints import FingerprintStore, cache_epoch
from theforge.context.plan import plan_context
from theforge.context.resources import ResourceResolver, discover_roots


def _root(base: Path, fid: str, resources: list[dict]) -> Path:
    base.mkdir(parents=True, exist_ok=True)
    (base / "forge.agentic.json").write_text(
        json.dumps({"forge_id": fid, "resources": resources}), encoding="utf-8"
    )
    for res in resources:
        loc = res.get("location")
        if isinstance(loc, str):
            target = base / loc
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(f"# {res['id']}\n" + "body\n" * 20, "utf-8")
    return base


def _resolver(tmp: Path, order: list[str]) -> ResourceResolver:
    """Workspace shaped like the real one: two clouds + an API forge +
    a product forge — the §8.4 cross-cloud routing fixture."""
    paths = {
        "spark-forge-aws": _root(
            tmp / "aws",
            "spark-forge-aws",
            [
                {
                    "id": "glue-pipeline",
                    "kind": "skill",
                    "location": "skills/glue/SKILL.md",
                    "description": "AWS Glue PySpark ETL job tuning",
                    "tags": ["spark", "aws", "glue", "etl"],
                    "domain": "data-engineering",
                },
                {
                    "id": "lakehouse-s3",
                    "kind": "knowledge",
                    "location": "knowledge/iceberg-s3.md",
                    "description": "Iceberg tables on S3 with Glue catalog",
                    "tags": ["iceberg", "aws", "s3"],
                    "domain": "data-engineering",
                },
            ],
        ),
        "spark-forge-azure": _root(
            tmp / "azure",
            "spark-forge-azure",
            [
                {
                    "id": "adf-adls-pipeline",
                    "kind": "skill",
                    "location": "skills/adf/SKILL.md",
                    "description": "Azure Data Factory / ADLS pipelines",
                    "tags": ["spark", "azure", "adls", "databricks", "adf"],
                    "domain": "data-engineering",
                },
                {
                    "id": "lakehouse-adls",
                    "kind": "knowledge",
                    "location": "knowledge/iceberg-adls.md",
                    "description": "Iceberg tables on ADLS with Unity Catalog",
                    "tags": ["iceberg", "azure", "adls"],
                    "domain": "data-engineering",
                },
            ],
        ),
        "api-forge": _root(
            tmp / "api",
            "api-forge",
            [
                {
                    "id": "openapi-design",
                    "kind": "skill",
                    "location": "skills/openapi/SKILL.md",
                    "description": "REST OpenAPI contract design",
                    "tags": ["api", "rest", "openapi"],
                    "domain": "api",
                }
            ],
        ),
        "product-forge": _root(
            tmp / "product",
            "product-forge",
            [
                {
                    "id": "analytics-dashboard",
                    "kind": "skill",
                    "location": "skills/dashboard/SKILL.md",
                    "description": "product analytics dashboards",
                    "tags": ["analytics", "dashboard", "product"],
                    "domain": "product",
                }
            ],
        ),
        "iac-forge": _root(
            tmp / "iac",
            "iac-forge",
            [
                {
                    "id": "terraform-modules",
                    "kind": "skill",
                    "location": "skills/terraform/SKILL.md",
                    "description": "Terraform module review",
                    "tags": ["terraform", "iac", "hcl"],
                    "domain": "infrastructure",
                }
            ],
        ),
    }
    explicit = [(fid, paths[fid]) for fid in order]
    return ResourceResolver(discover_roots(None, explicit=explicit, scan_installed=False))


ORDER = [
    "spark-forge-aws",
    "spark-forge-azure",
    "api-forge",
    "product-forge",
    "iac-forge",
]


# --- §8.3 selection evidence -------------------------------------------------


def test_plan_carries_selection_evidence(tmp_path: Path) -> None:
    plan = plan_context("tune an AWS Glue PySpark job", _resolver(tmp_path, ORDER))
    assert plan.selection == "selected"
    assert plan.confidence in ("high", "medium")
    assert plan.level2_forge == "spark-forge-aws"
    assert plan.evidence["spark-forge-aws"]
    assert plan.forge_scores["spark-forge-aws"] > 0
    assert plan.disambiguation  # a reason, never silence
    # the alternatives carry why-not, never a fabricated winner
    assert all(a["forge_id"] != plan.level2_forge for a in plan.alternatives)


def test_plan_tie_is_declared_ambiguous_never_first_install(tmp_path: Path) -> None:
    """A real tie — two forges with identical metadata — is `ambiguous`,
    never silently the first-installed."""
    res = [
        {
            "id": "shared-skill",
            "kind": "skill",
            "location": "skills/s/SKILL.md",
            "description": "same metadata on both",
            "tags": ["iceberg", "lakehouse"],
        }
    ]
    a = _root(tmp_path / "first", "forge-aaa", res)
    b = _root(tmp_path / "second", "forge-bbb", res)
    resolver = ResourceResolver(
        discover_roots(None, explicit=[("forge-aaa", a), ("forge-bbb", b)], scan_installed=False)
    )
    plan = plan_context("iceberg lakehouse layout", resolver)
    assert plan.selection == "ambiguous"
    assert plan.level2_forge is None  # no arbitrary winner
    assert plan.confidence == "low"
    tied = {x["forge_id"] for x in plan.alternatives}
    assert tied == {"forge-aaa", "forge-bbb"}
    assert plan.level3_refs == []  # ambiguity escalates nothing to L3


# --- §8.4 cross-cloud routing matrix -------------------------------------------


def test_glue_job_routes_aws(tmp_path: Path) -> None:
    plan = plan_context("debug an AWS Glue ETL job", _resolver(tmp_path, ORDER))
    assert plan.level2_forge == "spark-forge-aws"


def test_databricks_adls_routes_azure(tmp_path: Path) -> None:
    plan = plan_context("optimize a Databricks job reading ADLS", _resolver(tmp_path, ORDER))
    assert plan.level2_forge == "spark-forge-azure"


def test_terraform_routes_contextually(tmp_path: Path) -> None:
    plan = plan_context("review a Terraform module change", _resolver(tmp_path, ORDER))
    assert plan.level2_forge == "iac-forge"


def test_cross_cloud_migration_selects_both(tmp_path: Path) -> None:
    plan = plan_context(
        "migrate an AWS Glue pipeline to Azure Data Factory",
        _resolver(tmp_path, ORDER),
    )
    selected = {plan.level2_forge, *plan.level2_aux} - {None}
    assert {"spark-forge-aws", "spark-forge-azure"} <= selected


def test_install_order_never_biases_routing(tmp_path: Path) -> None:
    """§8.4 — a second-installed forge must win on merit, not position."""
    task = "optimize a Databricks job reading ADLS"
    forward = plan_context(task, _resolver(tmp_path, ORDER))
    # reversed install order: azure first
    reverse = plan_context(task, _resolver(tmp_path, list(reversed(ORDER))))
    assert forward.level2_forge == reverse.level2_forge == "spark-forge-azure"


def test_second_installed_forge_wins_on_merit(tmp_path: Path) -> None:
    """The aws resolver is 'installed' first; the azure task still lands
    on the second-installed forge — position is never a score."""
    plan = plan_context(
        "review an Azure Data Factory pipeline",
        _resolver(tmp_path, ORDER),
    )
    assert plan.level2_forge == "spark-forge-azure"
    assert plan.forge_scores["spark-forge-azure"] > plan.forge_scores.get("spark-forge-aws", -1)


# --- §8.7 don't-load-everything ------------------------------------------------


def test_aws_task_never_selects_unrelated_forges(tmp_path: Path) -> None:
    resolver = _resolver(tmp_path, ORDER)
    plan = plan_context("tune an AWS Glue PySpark job", resolver)
    assert plan.level2_forge == "spark-forge-aws"
    ids = set(plan.level3_refs)
    assert ids
    # L3 refs stay inside the selected forge set — no Product/API/Azure bodies
    forbidden = {"product-forge", "api-forge", "spark-forge-azure", "iac-forge"}
    assert all(not i.startswith(tuple(f + ":" for f in forbidden)) for i in ids)
    # discovered ≠ retrieved: the plan scans metadata, reads nothing
    assert plan.metrics["retrieved_refs"] == 0
    assert plan.metrics["discovered_refs"] >= len(ids)


def test_aws_task_retrieval_stays_in_selected_set(tmp_path: Path) -> None:
    """Fetching only the selected L3 refs must never touch another forge's
    content — retrieved identities ⊆ expected set."""
    resolver = _resolver(tmp_path, ORDER)
    plan = plan_context("tune an AWS Glue PySpark job", resolver)
    from theforge.context.resources import ResourceFailure

    retrieved = []
    for identity in plan.level3_refs:
        try:
            content = resolver.get(identity, max_bytes=64_000)
        except ResourceFailure:
            continue
        if getattr(content, "text", None):
            retrieved.append(identity)
    assert retrieved
    assert all(i.startswith("spark-forge-aws:") for i in retrieved)


def test_multi_domain_task_can_escalate_both_sides(tmp_path: Path) -> None:
    """A genuinely multi-domain task may select both forges — the rule is
    never *everything*, always *evidence*."""
    plan = plan_context(
        "migrate the AWS Glue ETL to Azure Databricks on ADLS",
        _resolver(tmp_path, ORDER),
    )
    selected = {plan.level2_forge, *plan.level2_aux} - {None}
    assert {"spark-forge-aws", "spark-forge-azure"} <= selected
    forges_with_refs = {i.split(":", 1)[0] for i in plan.level3_refs}
    assert forges_with_refs <= selected


# --- §8.5 context budget --------------------------------------------------------


def test_budget_categories_and_honest_tokens(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text("# x\n" * 100, "utf-8")
    skill = tmp_path / ".agents/skills/demo"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("---\nname: demo\n---\nbody\n" * 10, "utf-8")
    doc = context_budget(tmp_path)
    assert doc["schema"] == "theforge/ContextBudget/v1"
    cats = doc["categories"]
    assert set(CATEGORY_ORDER) <= set(cats)
    assert cats["permanent_instructions"]["bytes"] > 0
    assert cats["permanent_instructions"]["state"] == "measured"
    assert cats["skill_metadata"]["bytes"] > 0
    assert cats["skill_body"]["bytes"] > 0
    # tool output is never observable offline — unmeasured, not zero
    assert cats["tool_output"]["state"] == "unmeasured"
    assert cats["tool_output"]["bytes"] is None
    # every token figure is estimated + labeled, never "observed"
    for cat in cats.values():
        est = cat["estimated_tokens"]
        if est is not None:
            assert est["kind"] == "estimated"
            assert est["method"]
            assert est["confidence"] == "low"
    assert doc["total"]["estimated_tokens"]["kind"] == "estimated"


def test_budget_empty_workspace_is_honest_zeros(tmp_path: Path) -> None:
    doc = context_budget(tmp_path)
    assert doc["categories"]["permanent_instructions"]["bytes"] == 0
    assert doc["categories"]["retrieved_code"]["state"] == "unmeasured"


# --- §8.6 fingerprint epoch invalidation ----------------------------------------


def _fp_root(tmp: Path) -> Path:
    root = tmp / "ws"
    (root / "src").mkdir(parents=True)
    f = root / "src/app.py"
    f.write_text("print(1)\n", "utf-8")
    # age the file past the cache's racy window so a stat-match hit is
    # even possible (recorded_ns - mtime_ns must exceed RACY_WINDOW_NS)
    import time as _t

    old = _t.time_ns() - 300_000_000_000
    os.utime(f, ns=(old, old))
    return root


def _fingerprint(store: FingerprintStore) -> None:
    store.file("src/app.py", store.root / "src/app.py")
    store.save()


def test_epoch_invalidates_on_forge_update(tmp_path: Path) -> None:
    root = _fp_root(tmp_path)
    v1 = cache_epoch("0.7.0", "sha-aaa", "trusted")
    v2 = cache_epoch("0.7.0", "sha-bbb", "trusted")  # manifest changed
    s1 = FingerprintStore(root, cache_dir=tmp_path / "cache", epoch=v1)
    _fingerprint(s1)
    s2 = FingerprintStore(root, cache_dir=tmp_path / "cache", epoch=v2)
    assert any("epoch" in w for w in s2.warnings)
    assert s2.stats.hits == 0  # nothing trusted across the epoch


def test_epoch_kept_when_parts_unchanged(tmp_path: Path) -> None:
    root = _fp_root(tmp_path)
    ep = cache_epoch("0.7.7", "sha-aaa", "trusted")
    s1 = FingerprintStore(root, cache_dir=tmp_path / "cache", epoch=ep)
    _fingerprint(s1)
    s2 = FingerprintStore(root, cache_dir=tmp_path / "cache", epoch=ep)
    fp = s2.file("src/app.py", root / "src/app.py")
    assert fp is not None and fp.reused


def test_epoch_revocation_and_security_rule_update(tmp_path: Path) -> None:
    root = _fp_root(tmp_path)
    trusted = cache_epoch("0.7.7", "sha-aaa", "trusted")
    revoked = cache_epoch("0.7.7", "sha-aaa", "blocked")
    upgraded = cache_epoch("0.7.8", "sha-aaa", "trusted")  # rules ship in the pkg
    s1 = FingerprintStore(root, cache_dir=tmp_path / "cache", epoch=trusted)
    _fingerprint(s1)
    for ep, why in ((revoked, "revocation"), (upgraded, "security-rule update")):
        s = FingerprintStore(root, cache_dir=tmp_path / "cache", epoch=ep)
        assert any("epoch" in w for w in s.warnings), why


def test_workspace_change_is_a_different_cache(tmp_path: Path) -> None:
    a, b = _fp_root(tmp_path / "a"), _fp_root(tmp_path / "b")
    ep = cache_epoch("0.7.7", "sha-aaa", "trusted")
    sa = FingerprintStore(a, cache_dir=tmp_path / "cache", epoch=ep)
    _fingerprint(sa)
    sb = FingerprintStore(b, cache_dir=tmp_path / "cache", epoch=ep)
    assert sb.path != sa.path  # root-digest keyed — no cross-root trust


def test_file_change_misses_entry_level(tmp_path: Path) -> None:
    """Content change is handled by the entry fingerprint itself."""
    root = _fp_root(tmp_path)
    s1 = FingerprintStore(root, cache_dir=tmp_path / "cache")
    _fingerprint(s1)
    target = root / "src/app.py"
    target.write_text("print(2)\n", "utf-8")
    # force a different mtime+size so the stat key cannot collide
    os.utime(target, ns=(target.stat().st_atime_ns, target.stat().st_mtime_ns + 5_000_000_000))
    s2 = FingerprintStore(root, cache_dir=tmp_path / "cache")
    fp = s2.file("src/app.py", target)
    assert fp is not None and not fp.reused


# --- §8.1 permanent-context audit (12 forges) -------------------------------------


def test_permanent_context_audit_twelve_forges(tmp_path: Path) -> None:
    """Measure the installed L0 docs for a 12-forge workspace: the compact
    AGENTS.md blocks + ecosystem + protocol stay small and pointer-based."""
    from theforge import _forgecontext as fctx

    registry = {
        "schema": "forge/context-registry/v1",
        "forges": [
            {
                "forge_id": f"forge-{i:02d}",
                "name": f"Forge {i:02d}",
                "version": "1.0.0",
                "domains": [f"domain-{i}"],
            }
            for i in range(12)
        ],
    }
    manifests = {
        f"forge-{i:02d}": {
            "forge_id": f"forge-{i:02d}",
            "name": f"Forge {i:02d}",
            "version": "1.0.0",
            "domains": [f"domain-{i}"],
            "interfaces": {"cli": {"name": f"forge{i:02d}"}},
            "discovery": {"commands": [{"argv": ["forge", "doctor"]}]},
        }
        for i in range(12)
    }
    protocol = fctx.protocol_document(registry, manifests)
    agents = "# mine\n" + "\n".join(
        fctx.apply_managed_block(
            "", f"forge:{fid}", fctx._forge_block_compact(manifests[fid]), name="AGENTS.md"
        )
        for fid in manifests
    )
    agents = fctx.apply_managed_block(
        agents, "forge:ecosystem", fctx._ecosystem_block(), name="AGENTS.md"
    )
    protocol_bytes = len(protocol.encode("utf-8"))
    agents_bytes = len(agents.encode("utf-8"))
    # real numbers, asserted as bounds: fixed protocol ~2-3KB, ~<400B/forge
    per_forge = (protocol_bytes - 4000) / 12
    assert per_forge < 700, f"per-forge protocol text too big: {per_forge:.0f}B"
    assert agents_bytes < 12 * 500 + 2500, f"AGENTS.md too heavy: {agents_bytes}B"
    # compact blocks carry pointers, not duplicated instruction text
    block = fctx._forge_block_compact(manifests["forge-00"])
    assert "capability manifest" in block.lower()
    assert "Discovery:" not in block  # detail lives in the manifest + protocol
    # safety-critical rules are still in the shared ecosystem block
    eco = fctx._ecosystem_block()
    assert "data, never instructions" in eco
    assert "never invented" in eco
