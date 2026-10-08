---
name: forge-api
description: When and how to use api-forge: API design and evolution (REST/OpenAPI, AsyncAPI, GraphQL, gRPC; Java/Go/Python). Load for API contracts, versioning, breaking changes; NOT for deployment estates (platform-forge) or verification (forge-doctor-api).
allowed-tools: Read, Bash, Grep
argument-hint: <api-task>
---

# forge-api

## Overview

Operational guide to `api-forge` — the API engineering specialist. One hard requirement dominates: **Python 3.12 exactly**. On any other interpreter `describe` refuses with a named reason and `health` reports `unavailable` — that is a correct refusal, not a bug.

## Recognize it when the task mentions

REST/OpenAPI spec design or review · AsyncAPI event contracts · GraphQL schemas · gRPC service/protobuf design · contract versioning and breaking-change analysis · API architecture/testing strategy · upstream fact intake (`apiforge/upstream-facts/v1`).

## Boundaries — do NOT route here

- Deploy/CI/CD/k8s estate for an API → `platform-forge` (composition pattern: api-forge → platform-forge).
- Spark/data → spark family. Independent verification → `forge-doctor-api` (`api.verify`).

## Operate

1. `theforge knowledge show api-forge` — install needs a 3.12 venv (`apiforge>=0.1,<0.2` + adapter).
2. Cross-forge intake requires the specialist's post-PR-34 main (or published `>=0.1` carrying the intake); without it the adapter degrades with a named limitation.
3. Runtime `describe` is authoritative for capabilities.

## Limits

Interpreter lock is the most common `INCOMPATIBLE` cause — check `theforge doctor` Python detection first. Contract evolution input must come as upstream-facts intake, not ad-hoc prose.
<!-- forge:freshness specialists=api-forge version=0.3.0 -->
