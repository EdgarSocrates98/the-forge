# Profiles — install, gateway and runtime budget

Three different "profile" vocabularies share the CLI. They answer
different questions and do not substitute for each other:

| vocabulary | flag | values | decides |
|---|---|---|---|
| install profile | `--profile` on `install apply` / `install auto` / `setup` | `minimal` · `recommended` · `full` | which asset kinds land in the target |
| gateway profile | `--gateway-profile` on `setup` / `install apply` / `install auto` / `ask --auto-install` | `economy` · `balanced` · `deep` | the persisted execution budget of The Forge router |
| runtime budget profile | `--profile` on `ask` / `plan` / `capabilities discover` | `auto` · `economy` · `balanced` · `max` | context budget, negotiation and verification per run |

## Install profiles — what gets written

`--profile` selects the asset *kinds* the forge's installer writes
(`profile_asset_kinds` in the installkit). Core kinds — `config`,
`marker`, `state` — are always installed.

| profile | asset kinds installed | skipped |
|---|---|---|
| `minimal` | `config`, `mcp`, `marker`, `state` | skills, agents, knowledge, rules, evals |
| `recommended` | minimal + `skill`, `agent`, `knowledge`, `rules`, `evals` | — |
| `full` | same asset-kind set as `recommended` today | — |

Honest note: `recommended` and `full` currently resolve to the same
asset-kind set — the profile is a coarse default, and the real
granularity lives in `--components`. The wizard maps them to Economy /
Balanced / Full labels with the same component defaults; a future
divergence lands here first.

`--components LIST` narrows or extends the profile's set. Selectable
components: `skills`, `agents`, `mcp`, `knowledge`, `rules`, `evals`
(map to asset kinds) plus `tui` and `graph-studio` (runtime flags
persisted to `components.json`, not files). Unknown names are
`FORGE-INSTALL-PROFILE-UNKNOWN`. The selection is persisted and
defaults to everything enabled.

Per-forge honesty: the orchestrator propagates `--profile` /
`--components` only to registered forges whose declared surface lists
them (`install.flags`/`install.profiles` in the manifest); a forge that
does not declare them is `unsupported-capability`, never silently
re-flagged.

## Gateway profiles — the persisted router budget

`--gateway-profile` is chosen at install time (`economy`, `balanced`,
`deep`) and persisted into the install's options as the execution
profile The Forge router runs under; the value is carried in the
install receipt (`execution_profile`) and delegated to sibling forges
that declare the flag.

| gateway profile | wizard label | intent |
|---|---|---|
| `economy` | Economy (lowest context cost) | cheapest governed path |
| `balanced` | Balanced (recommended) | default trade-off |
| `deep` | Deep (maximum verification) | maximum verification effort |

## Runtime budget profiles — per-run behavior

`--profile` on `ask`, `plan` and `capabilities discover` selects the
`ContextProfile` used by the Context Broker and the orchestrator — the
single table in `src/theforge/profiles.py` (no other module defines
budgets, timeouts or negotiation rounds).

| profile | budget | max files | tiers | negotiation rounds | max providers | health fallback | verification | execute timeout |
|---|---|---|---|---|---|---|---|---|
| `economy` | 64 KiB | 16 | metadata, reference | 0 | 1 | no | minimal | 60 s |
| `balanced` | 256 KiB | 64 | all four | 1 | 1 | yes | conditional | 180 s |
| `max` | 1 MiB | 256 | all four | 2 | 4 | yes | strong | 600 s |

- `auto` (the default) lets the complexity assessment decide; until it
  resolves — and when it cannot run — the assumed profile is
  `balanced`.
- On `capabilities discover` the same names mean *how eagerly remote
  sources are consulted*: `economy` only when no local capability
  exists, `balanced` (default) when nothing local fully satisfies the
  requirement, `max` always compares remote claims.
- `deep` (install time) and `max` (runtime) are different vocabularies
  for adjacent concepts — they are not aliases; each surface accepts
  exactly its own set.

## Selecting

```bash
theforge setup --profile minimal --gateway-profile economy --yes
theforge install apply --profile recommended --components skills,agents,mcp --yes
theforge install auto --scope workspace --profile full --gateway-profile deep --yes
theforge ask "task" --profile auto --auto-install --install-profile minimal
theforge capabilities discover --requirement req.json --profile max
```

## Where profiles show up

- `install` receipts carry `profile`, `components` and
  `execution_profile`; the consolidated workspace doc records the
  per-forge declared `profiles` surface.
- Context budgets (`budget_bytes`, `tier_bytes`) are always measured in
  bytes; token counts stay `unknown` in the core unless the host
  supplies measured/estimated telemetry — see
  [context-engineering.md](context-engineering.md) and
  [context-roi.md](context-roi.md).
- `ContextBudgetRecommendation/v1` may *recommend* a profile budget from
  measured history — advisory only, never auto-applied
  ([ADR 0047](adr/0047-context-roi-advisory.md)).
