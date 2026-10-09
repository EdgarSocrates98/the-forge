+++
name = "forge-verification"
description = "Independent verification in The Forge: verifier selection, producer/verifier separation, verification requests and verdicts. Load when a plan needs a verify step or a result needs independent confirmation."

[claude]
allowed_tools = "Read, Bash, Grep"
argument_hint = "<verify-question>"
[codex]
display_name = "Forge Verification"
short_description = "Independent verify, producer/verifier split"
+++

# forge-verification

## Overview

Verification is structurally independent: the verifier for a result must not be its producer. The Forge selects verifiers from the capability graph's `can_verify`/`can_review` relations and enforces separation when policy requires it — a proposal cannot waive it.

## Workflow

1. Identify the artifact producer (the specialist in the executed step).
2. Select verifiers via `can_verify` relations compatible with the artifact type — `forge-doctor-data` for data/Spark output, `forge-doctor-api` for API contracts.
3. Emit a verification request (contract, not prose): artifact refs, producer identity, required checks.
4. The verdict is a `VerifyVerdict` contract — `verified`/`refused`/named failure, evidence-linked.
5. Producer ≠ verifier is a hard gate when declared; `theforge knowledge show <id>` lists `preferred_verifiers`.

## Boundaries

- A provider never verifies itself; a doctor that produced nothing today stays a verifier.
- "No compatible verifier installed" is a plan gap → `forge-install`, not a reason to self-verify.
- Verification results are evidence; they feed memory as observations, never as self-asserted trust.
