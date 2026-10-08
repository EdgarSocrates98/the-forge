---
name: forge-spark-aws
description: When and how to use spark-forge-aws: AWS Spark engineering (Glue, EMR, Lake Formation, S3, Athena, Iceberg, AWS lakehouse). Load when the task is Spark-on-AWS; NOT for Azure estates (that is spark-forge-azure).
---

# forge-spark-aws

<background_information>
Operational guide to the `spark-forge-aws` specialist — recognition, scope boundaries, install and verification. Deep Spark/Glue/EMR domain knowledge lives in the specialist repo; this skill covers how The Forge uses it. `theforge knowledge show spark-forge-aws` is the bootstrap source of truth.
</background_information>

<instructions>
## Recognize it when the task mentions

Glue jobs/catalog · EMR clusters/steps · Lake Formation grants/tag-policies · S3 data lakes / S3 Tables · Athena queries/workgroups · Iceberg tables/compaction · AWS lakehouse architecture · PySpark on AWS runtimes · Spark event logs/Spark UI analysis on AWS estates.

## Boundaries — do NOT route here

- Azure anything: Databricks, Synapse, Fabric, ADLS, ADF, Unity Catalog → `spark-forge-azure`. No false equivalence.
- API contracts → `api-forge`. Platform/IDP estate analysis → `platform-forge`.
- Independent review of its own output → `forge-doctor-data` (preferred verifier).

## Operate

1. `theforge knowledge show spark-forge-aws` — install recipe (venv-pip, Python ≥3.11 venv, `sparkforge-aws>=0.5,<0.6` + adapter), verify command, preferred verifiers.
2. `theforge registry show spark-forge-aws` — live version, manifest sha, surface fingerprint.
3. Capabilities come from runtime `describe` — never hardcode a list here.
4. Verify results through `forge-doctor-data` when independence is required.

## Limits

AWS-only signals; it will not recognize Azure/GCP tasks. Records `limitations` in results honestly — a partial answer is a partial answer.
</instructions>
