---
name: forge-discovery
description: Provider discovery and health in The Forge: executables, manifests, surface fingerprints, health states and staleness. Load when a specialist is missing, broken, stale, or its reported state is in doubt.
---

# forge-discovery

<background_information>
Discovery binds a registry record to a live specialist: executable + manifest + native surface + health. The surface fingerprint is the staleness detector — when a specialist upgrades or changes surface, the fingerprint changes and every policy/preference bound to the old fingerprint is non-authoritative until re-measured.
</background_information>

<instructions>
## States

`AVAILABLE` (installed, healthy, fingerprint current) · `NOT_INSTALLED` (knowledge package exists, no registry record) · `INSTALLED_BROKEN` (record exists, health fails) · `INCOMPATIBLE` (interpreter/OS requirements unmet — e.g. api-forge off Python 3.12) · `UNVERIFIED` (installed but never verified) · `BLOCKED` (policy refuses) · `UNKNOWN` (nothing on record).

## Workflow

1. `theforge registry list` / `registry show <id>` — state, version, trust, manifest sha.
2. `theforge providers health` — live health checks against the recorded argv.
3. `theforge doctor` — environment truth: OS, Python, PATH, writable dirs, per-provider readiness.
4. Compare `surface_fingerprint` in policy/memory records with the live fingerprint; a mismatch = stale, not wrong.
5. `theforge knowledge show <id>` — the bootstrap view (install recipe, verify command) for a missing/broken specialist.

## Boundaries

- Health failures are reported as named states with reasons; never paper over with a retry loop.
- A stale fingerprint invalidates bound policies and preferences, not the provider itself — re-measure, don't reinstall blindly.
- Discovery evidence lives in `.forge/`; it is observable state, not plan.
</instructions>
