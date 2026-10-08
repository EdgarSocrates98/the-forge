---
name: forge-spark-azure
description: When and how to use spark-forge-azure: Azure Spark engineering (Databricks, ADLS, Synapse, Event Hubs, Fabric, ADF, Unity Catalog). Load when the task is Spark-on-Azure; NOT for AWS estates (that is spark-forge-aws).
---

# forge-spark-azure

<background_information>
Operational guide to `spark-forge-azure` — the Azure-native Spark specialist exposing real seams (`sdd.check`, `sdd.status`, `azure.access-diagnose`, `fabric.access-diagnose`, `azure.doctor`). It is not an AWS alias. `theforge knowledge show spark-forge-azure` is the bootstrap source of truth.
</background_information>

<instructions>
## Recognize it when the task mentions

Databricks (jobs, clusters, notebooks) · ADLS Gen2 storage · Synapse Spark pools · Microsoft Fabric (pipelines, lakehouses) · ADF pipelines · Event Hubs · Unity Catalog governance · Spark on Azure networking/access failures.

## Boundaries — do NOT route here

- AWS: Glue/EMR/Lake Formation/Athena → `spark-forge-aws`. Unity Catalog is not Lake Formation; ADF is not Glue.
- API work → `api-forge`; platform estate → `platform-forge`.
- Independent verification → `forge-doctor-data`.

## Operate

1. `theforge knowledge show spark-forge-azure` — install (venv-pip, `sparkforge-azure>=0.1,<0.2`, Python ≥3.10), verify, verifiers.
2. Inputs are staged bundles (`case.yaml` + layers, or `docs/sdd/` trees): evidence is re-bound to the sha256 of the *staged* file, never the specialist's self-reported hash.
3. Runtime `describe` is authoritative for capabilities — this skill never lists them.

## Limits

Azure-only signals. SDD seams require the specialist's own gate (`sparkforge-azure sdd check`) semantics — refusals carry named `unlock` instructions.
</instructions>
<!-- forge:freshness specialists=spark-forge-azure version=0.1.0 -->
