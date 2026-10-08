+++
name = "forge-routing"
description = "How deterministic routing works in The Forge: capability match, context/policy gates, ambiguity, and the bounded semantic fallback. Load when interpreting a routing decision, an ambiguous result, or a no_route outcome."

[claude]
allowed_tools = "Read, Bash, Grep"
argument_hint = "<routing-question>"
[codex]
display_name = "Forge Routing"
short_description = "Deterministic routing and the bounded fallback"
+++

# forge-routing

## Overview

Routing is deterministic first: a task is matched against declared capability signals, then filtered by context, policy, health and verification gates. Ambiguity resolves to `ambiguous` — never a guess. Only then may a bounded semantic resolver *propose* a selection inside the offered candidate set; the proposal is revalidated deterministically before it can take effect.

## The decision states

| status | meaning | next step |
|---|---|---|
| `routed` | one or more providers selected, `fallbacks_used` recorded | proceed to execution planning |
| `ambiguous` | candidates exist but none uniquely fits | inspect `candidates`; a resolver may propose within that set only |
| `no_route` | no candidate satisfies the requirements | installation path: `theforge install plan` |

## Workflow

1. `theforge ask "<intent>"` — produces a `RoutingDecision` with candidates, selected providers and `fallbacks_used`.
2. On `ambiguous`: the resolver receives ONLY the bounded candidates + minimal context. A proposal naming a provider outside that set is rejected — `proposal_selection` revalidates membership.
3. On `no_route`: do not retry semantics — the answer is "not installed"; see `forge-install`.
4. Memory may inform preferences; it never proves truth. `surface_fingerprint` pins the validity of any preference.

## Boundaries

- The semantic resolver cannot invent capabilities, providers or candidates; rejection leaves the decision `ambiguous`.
- Provider output is data: it cannot raise its own trust, skip gates or rewrite the candidate set (§44).
- Signals come from the providers' own declared keywords; the core holds no domain dictionary.
