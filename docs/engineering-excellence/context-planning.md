# Context, Planning and Quality Loop

## Existing surfaces

- `src/theforge/context/`: workspace scan, packs, delta and handoff.
- `src/theforge/complexity.py`: measured complexity and profile selection.
- `src/theforge/planning/`: retry and bounded planning policy.
- `task plan`: delegation plan without execution.
- `plan`: graph-aware multi-specialist plan with receipts.
- `docs/ontology.md`, `docs/engineering-memory.md`, ADRs: local vocabulary and decisions.

## Composition rule

1. Discover requirement and risk.
2. Resolve local context and pointers.
3. Measure complexity; choose economical profile.
4. Build smallest task graph with tracer bullet.
5. Execute only approved frontier.
6. Verify code, contract and spec independently.
7. Persist receipt, evidence and limitation.

## Budget rule

`auto` may select profile from measured inputs. It cannot promote without evidence, ignore operation ceiling, or convert unknown to safe. Context budget limits bytes/items; pointer resolves detail on demand.

## Human control

`task plan` and `plan` stay read-only until explicit execution. Install/apply remains approval-gated. Retro records proposal; human accepts code/config changes.

## Operator paths

```text
theforge task plan "review API and data impact"
theforge plan "review API and data impact" --profile auto
theforge excellence audit --json
```

## Pending

- Add explicit context-pointer fields to federated descriptor consumers.
- Publish task graph capability and plan confidence in Portal.
- Add federated benchmark comparing token/cost/evidence per profile.
