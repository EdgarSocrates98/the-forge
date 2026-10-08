---
name: forge-doctor-data
description: When and how to use forge-doctor-data: independent verification and diagnosis of data/Spark engineering output. Load when a result from a spark/platform specialist needs independent review; NEVER for producing engineering work.
---

# forge-doctor-data

<background_information>
Operational guide to `forge-doctor-data` — a doctor, not a producer. It diagnoses and reviews `forge-contracts/1` evidence documents; the adapter bridges to the specialist's public seams in a child process (no subprocess or network inside the specialist side beyond that seam).
</background_information>

<instructions>
## Recognize it when the task mentions

"verify this Spark/data result independently" · reviewing tuning/migration output from spark-forge-* · diagnosing data-quality finding bundles · second-opinion on data engineering evidence · producer/verifier separation for data work.

## Boundaries — do NOT route here

- Implementation/production work — doctors never produce. Route to the engineering family first.
- API contract verification → `forge-doctor-api`.
- Any plan where it would verify output it produced itself — independence is checked, not assumed.

## Operate

1. `theforge knowledge show forge-doctor-data` — install (`forge-doctor-data>=1.0.0rc1,<2.0.0`, Python ≥3.11).
2. Input = artifact refs + producer identity (the `Handoff`/bundle contract), never prose summaries.
3. The verdict contract is `VerifyVerdict`; refusals and named failures are valid verdicts — do not retry to force `verified`.

## Limits

Verifier-only surface: no producer seams. If no doctor is installed, the honest answer is a plan gap (`forge-install`), not self-verification by the producer.
</instructions>
