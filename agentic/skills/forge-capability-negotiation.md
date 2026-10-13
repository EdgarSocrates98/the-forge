+++
name = "forge-capability-negotiation"
description = "Capability requirements vs offers: how the negotiation contract matches a CapabilityRequirement against manifest offers and the capability graph, and what negotiable means. Load when a task fails routing on capability shape rather than provider identity."

[claude]
allowed_tools = "Read, Bash, Grep"
argument_hint = "<capability-question>"
[codex]
display_name = "Capability Negotiation"
short_description = "Requirement ↔ offer matching"
+++

# forge-capability-negotiation

## Overview

Negotiation matches a `CapabilityRequirement` (what the task needs) against `CapabilityOffer`s (what manifests declare) through `negotiate_all` — producing a `CapabilityNegotiationResult`. It only chooses among registry/manifest/graph candidates; it cannot invent a capability that no provider exposes.

## Workflow

1. `theforge capabilities list` / `capabilities search <term>` — the declared surface.
2. `theforge capabilities negotiate` — evaluate a requirement document against live offers.
3. Read the result: matched offers, gaps (required inputs no offer provides), and the winning candidates with their reasons.
4. A capability gap is a `no_route` input, not a prompt for invention — route to `forge-install` or descope.

## Boundaries

- Offers come from manifests and the capability graph — the graph is built from real `describe` output, replayed or live.
- Negotiation is a matching function with an auditable result; it does not execute and it does not relax requirements silently.
- `can_verify`/`can_review` relations are ordered: a verifier that produced the artifact under review is not independent.
