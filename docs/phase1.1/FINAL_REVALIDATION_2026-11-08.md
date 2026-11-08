# Phase 1.1 — final revalidation (2026-11-08)

Status candidate: `PHASE_1_1_APPROVED_WITH_LIMITATIONS`

This note supersedes stale counts in earlier Phase 1.1 evidence while keeping
the original reports as historical audit records. It records the current
canonical `main` heads, executable gates run on Windows, and limits that cannot
be claimed without provider or cloud authority.

## Current heads and CI

| Repository | Current main | CI evidence | Result |
|---|---|---|---|
| `the-forge` | `301ca662ec90c89c970d795906fa1091b72f902a` | run `42507344696` | `VERIFIED` |
| `code-atlas-forge` | `19e703aff08b6973afabad683bd261571dfe1b7f` | run `42464291258` | `VERIFIED` |
| `forge-lens` | `86bd7572f2aecce1c84865b964246ae4513bc76b` | run `42448963206` | `VERIFIED` |
| `forge-agent-bridge` | `1b8ac82df64cdd53e7ff17324d325e82d8dbaff9` | run `42508735903` | `VERIFIED` |
| `product-forge` | `79b3a50ea4b4aafc7b5e8baedd8e6e3a523cb0c9` | run `42462885912` | `VERIFIED` |
| `forge-portal` | `324b6287facd45bb4573577410303ca1e0d8600a` | run `42505763000` | `VERIFIED` |

The Bridge fix bounds provider catalog discovery. `GET /providers` no longer
invokes external CLIs in the HTTP request thread; explicit diagnostics still
perform provider probes.

## Executed gates

- Product Forge: `225 passed, 1 skipped`; URL/Defuddle/parity focused suite:
  `25 passed`; canonical-to-embedded Bridge parity: `VERIFIED`.
- Code Atlas: knowledge adapter and federated-search focused suite:
  `11 passed`; current CI is green and the recorded full suite is
  `1663 passed, 21 skipped`.
- The Forge: Knowledge interoperability and schema suite: `23 passed`; merged
  CI is green. The federated local lab and Cycle 0.5.1 evidence remain the
  source for the process-level E2E receipt.
- Agent Bridge: full suite: `129 passed`; focused provider matrix plus catalog
  regression: `23 passed`; Ruff clean. A previous full local run exposed one
  intermittent provider-probe timeout; merged `1b8ac82` removes that request-
  path hazard.
- Portal: production build, `592` frontend tests, `45` browser E2E passes and
  `3` skips; visual/accessibility probe found no serious/critical axe issue,
  no invisible focus ring, and no horizontal overflow on audited routes.

## Findings closure

| Finding | State | Evidence |
|---|---|---|
| P0-01 Bridge CI | `VERIFIED` | PR #14 merged as `1b8ac82`; core/security green; Ruff and 23 focused tests |
| P0-02 context authorization | `VERIFIED` | workspace/product/source/item/revocation tests |
| P0-03 URL SSRF/rebinding | `VERIFIED` | validated DNS + IP-pinned transport, 25 focused tests |
| P0-04 embedded Bridge parity | `VERIFIED` | dedicated canonical checkout gate, local parity receipt |
| P1-01 context contract | `VERIFIED` | canonical v1 schema, typed inline provenance, round-trip tests |
| P1-02 identity/cache safety | `VERIFIED` | Code Atlas identity regression and snapshot-scoped cache |
| P1-03 Defuddle bounds | `VERIFIED` | bounded concurrent drains, timeout and overflow tests |
| P1-04 Obsidian | `VERIFIED` within declared scope | Markdown safe I/O; Canvas/Bases structural validation only |
| P1-05 federated search | `VERIFIED` for measured corpus | deterministic FTS/ranking and 100/1k/10k benchmark |
| P1-06 evidence freshness | `VERIFIED` after this update | machine-readable manifest and current heads |
| P1-07 federated E2E | `PARTIAL` | local fake-provider path passes; cloud/external providers not run |

## Explicit limits

`VERIFIED` does not mean external providers or cloud execution were performed.
Claude/Codex/Devin/Copilot authenticated runs remain `NOT_RUN`, AWS/Azure
execution remains `BLOCKED` without authorized credentials, and full semantic
execution of Obsidian Bases/Canvas formulas remains out of scope.
