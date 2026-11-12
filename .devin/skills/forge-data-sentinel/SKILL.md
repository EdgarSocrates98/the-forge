---
name: forge-data-sentinel
description: "When and how to use data-sentinel-forge: Spark/data runtime diagnosis — OOM, skew, shuffle, spill, EMR/Glue/Databricks run inspection from exported artifacts. Load when the task is runtime diagnosis of data jobs; NEVER for producing pipelines or static source review."
---

# forge-data-sentinel

<background_information>
Operational guide to `data-sentinel-forge` — the Spark/data runtime diagnostician (observer, not producer). It diagnoses from exported runtime evidence: driver/executor logs, OOM/skew/shuffle/spill, Glue/EMR run dumps, SQL and physical plans, Iceberg metadata, OpenLineage events, and `forge-doctor-data` handoff bundles.
</background_information>

<instructions>
## Recognize it when the task mentions

"diagnose this glue job failure" · OOM/skew/shuffle/spill in Spark logs · "explain this physical plan" · EMR/Glue run inspection · importing a forge-doctor-data handoff for independent runtime diagnosis.

## Boundaries — do NOT route here

- Spark engineering/production → `spark-forge-aws` / `spark-forge-azure` (cloud-split, never interchangeable).
- Static source review of a repo → the spark-forges or `forge-doctor-data`.
- API runtime diagnosis → `api-sentinel-forge`.
- Runs with no logs/plans/run dumps — the sentinel refuses rather than inventing a diagnosis.

## Operate

1. `theforge knowledge show data-sentinel-forge` — install (`data-sentinel-forge>=0.4.0,<0.5.0`, Python ≥3.11).
2. **UNADAPTED (documented gap, lf-0031):** there is no `adapters/datasentinel` — the specialist ships `forge.agentic.json` + a governed CLI, but no Forge Protocol `describe/health/execute` surface. Every orchestration pick resolves to a provider-absent/degraded refusal, never a silent skip or a fabricated run. Do not assume routing works; check `theforge registry list` first.
3. Until the adapter lands, the specialist is usable **outside** the control plane: `data-sentinel` CLI directly on exported artifacts (per the spark-forge `delegate-specialists` lane).

## Limits

Diagnostics require the runtime artifacts it consumes. The UNADAPTED state is intentional and documented in the knowledge package — a full sentinel adapter is the scope of a later spec, not a workaround to improvise.
<!-- forge:freshness specialists=data-sentinel-forge version=0.4.0 -->
</instructions>
<!-- forge:freshness specialists=data-sentinel-forge version=0.4.0 -->
