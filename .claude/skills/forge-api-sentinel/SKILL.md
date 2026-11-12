---
name: forge-api-sentinel
description: "When and how to use api-sentinel-forge: API runtime intelligence — runtime observation, SLO assessment, anomaly detection, incident investigation and deployment correlation over real telemetry. Load when an API task is about live/runtime health or incidents; NEVER for producing API work or for static source review."
allowed-tools: "Read, Bash, Grep"
---

# forge-api-sentinel

## Overview

Operational guide to `api-sentinel-forge` — the API runtime diagnostician (observer, not producer). Exposed to The Forge via `adapters/apisentinel` with five capabilities: `api.runtime-observation`, `api.slo-assessment`, `api.anomaly-detection`, `api.incident-investigation`, `api.deployment-correlation`.

## Recognize it when the task mentions

"is this API healthy right now" · SLO/error-budget posture · 5xx/latency spikes · incident investigation from telemetry · "did the last deploy regress the service" · runtime diagnosis of an api-forge service.

## Boundaries — do NOT route here

- API design/contracts/production → `api-forge`; independent source-level review → `forge-doctor-api`.
- Data/Spark runtime diagnosis → `data-sentinel-forge` (see its UNADAPTED note in `forge-knowledge/data-sentinel-forge.json`).
- Platform estate / CI/CD → `platform-forge`.
- Runs without runtime evidence — sentinel diagnostics need telemetry batches, run dumps or SLO windows; absent inputs degrade to an honest refusal, never a fabricated healthy verdict.

## Operate

1. `theforge knowledge show api-sentinel-forge` — install (`api-sentinel-forge>=0.1.0,<0.2.0`, Python ≥3.11, adapter `adapters/apisentinel` installed in the specialist interpreter).
2. `theforge ask "<task>"` — the router resolves on the sentinel intents; ambiguity stays `ambiguous`.
3. Inputs = telemetry/run artifacts or a handoff from `api-forge`/`forge-doctor-api`, as contract refs, never prose.
4. Profiles: `local` runs fully offline; `aws`/`opentelemetry` degrade to `unavailable:*` without their collectors — honest states by design.

## Limits

Diagnoses only what the evidence supports; `UNKNOWN`/`UNVERIFIED` are valid answers, fabricated health is a defect. Adapter capabilities are verified against a live `describe()` — drifted specialist surface degrades to manifest limitations, never a surprise.
<!-- forge:freshness specialists=api-sentinel-forge version=0.1.0 -->
<!-- forge:freshness specialists=api-sentinel-forge version=0.1.0 -->
