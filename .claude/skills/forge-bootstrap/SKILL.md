---
name: forge-bootstrap
description: Onboard a new specialist into The Forge: scaffold the provider skeleton, write its forge-knowledge package, wire the adapter, and reach routing — all through the generic path with zero core conditionals.
allowed-tools: Read, Write, Bash, Grep, Glob
argument-hint: <new-provider-name>
---

# forge-bootstrap

## Overview

A new specialist becomes routable through four artifacts, none of which touches provider names in the core: a provider skeleton (`theforge provider init`), a knowledge package (`forge-knowledge/<id>.json`), an adapter (subprocess + Forge Protocol) and a registry entry. The B25 benchmark proves a synthetic `example-forge` reaches graph + planning with no conditional on its name.

## Workflow

1. `theforge provider init <name>` — stdlib skeleton: manifest template, protocol loop, conformance test, registration guidance.
2. Write `forge-knowledge/<id>.json` — bootstrap facts: purpose, intents, install method (venv-pip/editable), verify command, preferred verifiers. Contract refuses trust grants and capability lists.
3. Implement the adapter under `adapters/<name>/` — stdlib-only, imports the specialist, never `theforge`; bridge module = single subprocess seam.
4. Register in the user `providers.toml` — a `[[providers]]` entry (`id`, `argv` pointing at the specialist venv, `trust`) — then `theforge registry refresh` runs discovery → `describe` → surface fingerprint. Only the user config grants trust.
5. Verify: `theforge ask` with a matching intent routes to it; conformance test passes.

## Boundaries

- The knowledge package is bootstrap metadata: it must NOT enumerate runtime capabilities — `capabilities_source = "runtime_discovery"` is enforced by the contract.
- Deep domain knowledge stays in the specialist repo. The Forge package covers operational facts only.
- Supply chain: pin repo commits/tags and package versions in the package; no floating `latest`.
