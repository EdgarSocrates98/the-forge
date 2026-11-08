# Cycle 0.5 revalidation — 2026-11-08

## Executive result

The eight-repository local compatibility baseline is reproducible for the
deterministic surfaces. No new P0 regression was found in the current code.
The status is `IMPLEMENTED_AND_TESTED` for local contracts, discovery,
catalogue routing and the L1 federated lab; provider sessions and cloud runs
remain `UNAVAILABLE` or `PARTIAL` because credentials and CLIs are absent.

## Ownership and compatibility

| Boundary | Canonical owner | Revalidation |
|---|---|---|
| API construction and evolution | API Forge | independent CLI/contracts remain green |
| deterministic API diagnosis | Forge Doctor API | deterministic findings and handoff suite green |
| data workload diagnosis | Data Sentinel Forge | data evidence suite green; no API analyzer added |
| provider discovery/routing/governance | The Forge | catalog, adapters, receipts and help matrix green |
| agent sessions and provider execution | Agent Bridge | session/event/authorization suite green |
| structural code intelligence | Code Atlas Forge | indexing/search/graph suite green |
| execution observability | Forge Lens | trace storage/scale suite green |
| visual federated experience | Forge Portal | real adapter/browser/axe evidence green |

No second router, session broker, OpenAPI engine, code indexer, trace store or
standalone Portal was introduced by this revalidation.

## P0/P1 disposition

| ID | Initial concern | Current state | Evidence / limitation |
|---|---|---|---|
| P0-001 | ownership overlap | `IMPLEMENTED_AND_TESTED` | current ownership docs and repository tests; API Sentinel remains deferred |
| P0-002 | interoperability contracts | `IMPLEMENTED_AND_TESTED` | versioned contracts, strict validation, receipts and compatibility tests |
| P0-003 | federated E2E | `IMPLEMENTED_AND_TESTED` locally | deterministic lab uses real local services and persisted receipts; no external provider fabricated |
| FAB-001/002/003 | Bridge events, retention, sanitization | `IMPLEMENTED_AND_TESTED` | Bridge full suite and lint green; provider authentication remains environment-dependent |
| INT-003 | specialist discovery versus routing | `IMPLEMENTED_AND_TESTED` for local adapters | catalog/adapter conformance and final L1 lab pass; cloud specialists are not claimed as live |
| INT-007 | Portal real data and honest states | `IMPLEMENTED_AND_TESTED` locally | Portal E2E and visual gate; optional external services stay `UNAVAILABLE/UNVERIFIED` |
| installation | cross-platform portability | `PARTIAL` | Windows PowerShell/PTY and 14-project matrix pass; Linux Bash/WSL unavailable |

## Tests and laboratory evidence

- Full local suites: API Forge `2025 passed, 4 skipped`; Doctor API `1945
  passed, 39 skipped`; Data Sentinel `1057 passed, 8 skipped, 1 warning`;
  Agent Bridge `128 passed`; Code Atlas `1663 passed, 21 skipped`; Product
  Forge `225 passed, 1 skipped`; Spark Azure `3180 passed, 9 skipped`; The
  Forge exited 0; Forge Lens exited 0.
- Forge Portal: production build, CLI `3/3`, install `2/2`, browser `45/45`
  executed with `3` skips, visual probe without serious/critical axe findings,
  214 visual captures and zero horizontal overflow pages.
- Federated CLI: install matrix `14/14`, runtime version/help `28/28`, real
  Windows PTY `14/14`, deep command help `1101/1101`.
- The Forge L1 lab: eight scenarios passed, 14/14 participants,
  `receipt_integrity=1.0`; the local provider execution is not presented as a
  cloud or external-agent homologation.

## Remaining risks

1. AWS and Azure cloud identities are absent; no cloud mutation or cloud
   homologation is claimed.
2. No authenticated external Agent Bridge session was created in this
   environment.
3. Linux Bash/WSL and clean-machine install paths still need a runner with the
   corresponding operating systems.
4. Portal visual scale beyond the current local capture set and broader
   semantic provider parity need separate benchmarks.

These limitations are classified explicitly instead of being collapsed into a
single green aggregate.
