---
name: forge-doctor-api
description: When and how to use forge-doctor-api: independent verification and diagnosis of API engineering output (ApiHandoffBundle intake, api.verify). Load when api-forge output needs independent review; NEVER for producing API work.
---

# forge-doctor-api

<background_information>
Operational guide to `forge-doctor-api` — a doctor, not a producer. It consumes `ApiHandoffBundle` documents, diagnoses API findings and runs `api.verify` on api-forge output with producer/verifier separation enforced.
</background_information>

<instructions>
## Recognize it when the task mentions

"verify this API result independently" · reviewing api-forge contract reviews/migration plans · diagnosing `ApiHandoffBundle` findings · API evidence second opinions.

## Boundaries — do NOT route here

- API design/production → `api-forge` first; doctors never produce.
- Data/Spark verification → `forge-doctor-data`.
- Self-verification loops — independence is enforced by the graph relations, not convention.

## Operate

1. `theforge knowledge show forge-doctor-api` — install (`forge-doctor-api>=0.2.0,<0.3.0`, Python ≥3.11).
2. `api.verify` requires the specialist's post-PR-13 main (`035b635`): earlier builds crash `ApiHandoffBundle.from_dict` with `NameError: DeltaContext` — check version before blaming the input.
3. Input = the bundle/artifact refs + producer identity, as a contract, never prose.

## Limits

Verifier-only surface. Version-floor above is a hard prerequisite for `api.verify`; it is recorded in the knowledge package because it bit in reality, not as trivia.
</instructions>
<!-- forge:freshness specialists=forge-doctor-api version=0.3.0 -->
