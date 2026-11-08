# Phase 1.1 — final revalidation (2026-11-08)

Status candidate: `PHASE_1_1_APPROVED_WITH_LIMITATIONS`

This note supersedes stale counts in earlier Phase 1.1 evidence while keeping
the original reports as historical audit records. It records the current
canonical `main` heads, executable gates run on Windows, and limits that cannot
be claimed without provider or cloud authority.

## Current heads and CI

| Repository | Current main | CI evidence | Result |
|---|---|---|---|
| `the-forge` | `e9791fac00e3d7986985e6375ca7270eb6b8e26a` | run `42507344696` | `VERIFIED` |
| `api-forge` | `94cb3c77b6dc813478e40b1be17c330bd362cf64` | PR #118; CI and Windows parity green | `VERIFIED` |
| `code-atlas-forge` | `19e703aff08b6973afabad683bd261571dfe1b7f` | run `42464291258` | `VERIFIED` |
| `forge-lens` | `86bd7572f2aecce1c84865b964246ae4513bc76b` | run `42448963206` | `VERIFIED` |
| `forge-agent-bridge` | `1b8ac82df64cdd53e7ff17324d325e82d8dbaff9` | run `42508735903` | `VERIFIED` |
| `product-forge` | `13ce64e78c0976b63b6f9a1a406052f0331f1759` | PR #32; CI green; embedded Bridge parity | `VERIFIED` |
| `forge-portal` | `324b6287facd45bb4573577410303ca1e0d8600a` | run `42505763000` | `VERIFIED` |
| `spark-forge-aws` | `5374fd6a1a3ea0e783dc27e189098bc447d8bb93` | PR #213; live LAB-002 receipt | `VERIFIED` |

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
- Portal visual rerun: `224` responsive captures, zero horizontal overflow,
  zero serious/critical axe violations, and zero clipped labels on the
  `/api-operations` route across desktop, tablet, mobile, light and dense
  variants.
- CLI/installation UX: all `14/14` projects expose a home/TUI/wizard surface;
  runtime smoke `28/28`, TTY launch `14/14`, TTY cancel `14/14`, and Windows
  installer dry-run `44 PASS / 0 FAIL`. Linux installer probes were executed in
  Python 3.12 and Node 22 containers; host-only POSIX cases remain explicitly
  bounded in the audit report.
- API Forge: full local suite `2026 passed, 4 skipped`; PR #118 adds a
  Windows-safe re-entrant lock around persisted ControlPlane transitions and a
  concurrent-start regression test.
- Spark AWS: independent Docker execution of `LAB-002` used real Apache Spark
  4.2.0 plus MinIO, executed scenario actions, and passed the oracle with
  fidelity `L1 / real_local_engine`; receipt
  `5599c0c0ac850b77926bc814a8f72f156e0abd47ce0b58be4fcd3abaf0c403ae`.

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
| P1-08 Windows ControlPlane concurrency | `VERIFIED` | API Forge PR #118; full local suite and CI/Windows parity green |

## Explicit limits

`VERIFIED` does not mean external providers or cloud execution were performed.
Claude/Codex/Devin/Copilot authenticated runs remain `NOT_RUN`, AWS/Azure
execution remains `BLOCKED` without authorized credentials, and full semantic
execution of Obsidian Bases/Canvas formulas remains out of scope.
