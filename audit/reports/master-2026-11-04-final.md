# FORGE Ecosystem — Master Delivery Report

Date: 2026-11-04  
Status: **CONDITIONALLY CERTIFIED — local evidence delivered; remote and host gates remain open**  
Evidence: `audit/baseline/master-2026-11-04/` and `audit/release-dumps/2026-11-04-ecosystem-master-v14/`  
Spec: `factory/specs/active/forge-ecosystem-master-2026-11-04.md`

## A. Executive Summary

The current `main` state of all 14 in-scope checkouts was inspected locally.
The changes below are real code, test and packaging changes, not documentation
claims. The ecosystem is not declared fully certified because GitHub remote
queries could not resolve in this session, real external hosts/providers/cloud
sandboxes were not available, and a small Windows-only Bridge subset remains
environmentally incompatible.

The strongest verified outcomes are:

- Product Forge execution violations and denied steps cannot present as
  `completed`; embedded Bridge composition and manifests are aligned.
- Agent Bridge replay is durable-first, ordered, deduplicated and concurrency-
  safe, with redaction preserving usage counters.
- Platform Forge and Doctor Data reject path escapes; Doctor API keeps malformed
  MCP frames isolated from the transport.
- The Forge and Portal preserve honest discovery/MCP states; `ready` registry
  records are exposed as `REGISTERED`, while `UNVERIFIED` and `NOT_APPLICABLE`
  remain visibly unverified/non-applicable.
- Forge CLI and Spark AWS preserve safe non-TTY behavior; lifecycle mutations
  require explicit approval outside a real TTY, while dry-run remains safe.
- Code Atlas release Actions are SHA-pinned; Product Forge portal assets were
  re-vendored from the canonical Portal build and the release dump now passes.

## B. Repository Assessment

| Repository | Inspected SHA | Result |
|---|---|---|
| api-forge | `974a680fb215` | No confirmed change required; remote CI NOT_RUN |
| code-atlas-forge | `f68bb7f0c0e9` | Release workflow SHA pinning; wheel/sdist/install evidence PASS |
| data-sentinel-forge | `8bcc8c9c3f0a` | No new functional change required; focused tests/package evidence PASS |
| forge-agent-bridge | `65af97ab3cdf` | Durable replay and persistence correction; focused tests PASS with Windows FAILs |
| forge-cli | `366882355af4` | Windows test portability; 103 tests/typecheck/build/pack PASS |
| forge-doctor-api | `7da36f5f02c8` | MCP malformed-frame isolation; focused tests PASS |
| forge-doctor-data | `c672dffc6a93` | Snapshot path confinement; 20 focused tests PASS |
| forge-lens | `191cd310aa3b` | MCP single-revision support remains NOT_TESTED against external hosts |
| forge-portal | `f0009f19e76e` | Honest MCP states; 11/11 focused tests and production build PASS |
| platform-forge | `c66b1282ae21` | Run-record path confinement; 8 focused tests PASS |
| product-forge | `79df1b86c338` | Runtime/Bridge fixes plus portal asset refresh; focused tests PASS |
| spark-forge-aws | `7d0b22fb6c68` | Approval-gated lifecycle; 58 focused install/wheel tests PASS |
| spark-forge-azure | `fdb365536981` | No confirmed change required; remote/sandbox checks NOT_RUN |
| the-forge | `fef42b830ccb` | Baseline tooling, portal registry fix, reports/dumps; local gates partial |

## C. Confirmed Findings

| ID | Severity | Classification | Finding | Fix / evidence |
|---|---|---|---|---|
| FORGE-AUDIT-0001 | P1 | VERIFIED_FIXED | Remote baseline collection could hang when GitHub DNS/API was unavailable. | `collect_baseline.py --offline`, 15s `gh` timeout, regression test PASS. |
| FORGE-AUDIT-0002 | P1 | VERIFIED_FIXED | Dynamic Python versions were omitted from baseline metadata. | Static resolution from declared attr/path; versions now match source files. |
| FORGE-AUDIT-0003 | P0 | VERIFIED_FIXED | Product Forge could classify policy-violating/denied execution as complete. | Explicit failed-step/violation derivation; 21 focused tests PASS. |
| FORGE-AUDIT-0004 | P0 | VERIFIED_FIXED | Bridge replay/persistence needed durable-first ordering and concurrency protection. | 37 portable tests reported PASS; Windows permission/process subset FAIL. |
| FORGE-AUDIT-0005 | P0 | VERIFIED_FIXED | Product Forge embedded Bridge surface could drift from standalone distribution. | Embedded manifests, module invocation and parity regressions added. |
| FORGE-AUDIT-0006 | P1 | VERIFIED_FIXED | Registry state `ready` was not promoted to Portal `REGISTERED`. | The Forge portal regression test and 31-test portal suite PASS. |
| FORGE-AUDIT-0007 | P1 | VERIFIED_FIXED | Portal could collapse honest MCP states into implied verification. | Typed/UI/i18n states `UNVERIFIED` and `NOT_APPLICABLE`; 11/11 PASS. |
| FORGE-AUDIT-0008 | P1 | VERIFIED_FIXED | Path-based run/snapshot persistence allowed unsafe locations. | Platform/Doctor Data adversarial focused tests PASS. |
| FORGE-AUDIT-0009 | P1 | VERIFIED_FIXED | Doctor API malformed frames could terminate the MCP transport. | 26 focused MCP tests PASS. |
| FORGE-AUDIT-0010 | P1 | VERIFIED_FIXED | Product Forge vendored Portal production assets were out of parity. | Canonical `vendor.py` refresh; release dump `vendor-integrity [OK]`. |
| FORGE-AUDIT-0011 | P1 | VERIFIED_FIXED | Compatibility catalog versions for Spark AWS, Forge CLI, Portal, Lens and Bridge were stale against current package manifests. | Catalog updated; `test_declared_versions_match_project_files` PASS. |

## D. Architectural Changes

- Kept responsibilities separated: CLI lifecycle, Bridge lifecycle/events,
  specialists, The Forge discovery/registry, Lens observation and Portal UI.
- Added/retained explicit evidence states instead of treating discovery as
  verification.
- Kept Product Forge standalone-compatible while making the embedded Bridge
  invocation module-based and manifest-backed.
- Made baseline tooling local-first and deterministic when remote metadata is
  unavailable.

## E. Agentic Engineering

The runtime correction now derives terminal status from violations and step
outcomes. Bridge event envelopes retain session identity, sequence, IDs and
redacted payloads; durable replay is used before the hot in-memory path. Real
provider/host homologation was not performed, so no external-provider success
is claimed.

## F. Installation & Packaging

- Forge CLI: 103 tests, typecheck, build and npm pack reported PASS.
- Spark AWS: 58 focused installation/wheel tests PASS; lifecycle mutation is
  approval-gated outside TTY and dry-run remains non-mutating.
- Code Atlas: wheel/sdist and clean-install evidence PASS; release Actions are
  SHA-pinned.
- Data Sentinel: 113 focused tests and clean wheel/sdist evidence reported PASS;
  no functional correction was necessary in this cycle.
- Product Forge: portal assets refreshed and vendor parity PASS.
- PyPI/npm publication: **NOT RUN by policy**; this prompt did not grant a new
  per-distribution publication approval.

## G. Security

Verified local corrections cover path traversal/drive/UNC/NUL/symlink defenses,
snapshot confinement, MCP malformed input isolation and default-deny lifecycle
approval. Portal `npm ci` reported six existing vulnerabilities; `npm audit fix`
was intentionally not run. Secret/cloud/provider red-team and remote dependency
scans remain NOT_RUN.

## H. Performance

No new same-case performance claim was made. Bridge replay avoids using the
memory buffer as an authoritative source and appends under a lock; large-scale
Code Atlas and cross-cloud benchmarks remain NOT_RUN in this cycle.

## I. Interoperability

| Integration | Status | Evidence |
|---|---|---|
| Product Forge ↔ Bridge | PASS locally | parity/manifests/replay focused tests |
| The Forge ↔ Portal | PASS locally | registry state regression + Portal build/tests |
| Portal MCP state rendering | PASS locally | 11/11 focused UI tests |
| Doctor API MCP boundary | PASS locally | 26 focused tests |
| Bridge ↔ real Claude/Codex/Devin/Copilot | NOT_RUN | external host/credentials unavailable |
| Cloud Spark AWS/Azure sandboxes | NOT_RUN | no authorized sandbox evidence |
| Lens MCP external client matrix | NOT_RUN | only local implementation inspected |

## J. UX/UI

The install surface retains the full-TTY rule for interactive paths; non-TTY
paths do not silently prompt. Forge CLI and Spark AWS expose approval/dry-run
semantics visibly. Portal MCP labels now distinguish “Não aplicável” and “Não
verificado” in Portuguese and equivalent English states.

## K. Quality Gates

| Gate | Status | Notes |
|---|---|---|
| Integrity / manifests | PASS | release dump and checksums pass |
| Local code quality | CONDITIONAL | changed-file checks pass; pre-existing broad lint debt remains |
| Focused regression tests | PASS | all listed local focused suites pass except explicit Windows Bridge cases |
| Packaging | PASS | wheels/sdists/npm pack/clean-install evidence from focused audits |
| Interoperability | CONDITIONAL | local contracts pass; real hosts/cloud NOT_RUN |
| Evals / agentic runtime | NOT_RUN | no provider-host eval run |
| Performance | NOT_RUN | no new benchmark baseline |
| Experience | PASS locally | TTY/TUI/approval and Portal focused journeys |
| Release readiness | CONDITIONAL | artifacts are prepared; publication intentionally withheld |
| Full The Forge pytest gate | FAIL | `5437 passed`, `23 skipped`, `186 deselected`, `19 failed`, `7 errors` in `3373.44s`; failures are recorded below |

Explicit Windows Bridge failures: POSIX file-mode assertions are not portable
to NTFS, and the fake provider spawn test requires a POSIX `sleep` executable.
They remain visible failures, not skips or false passes.

Full-suite failure clusters: seven Playwright Portal setup/navigation timeouts;
Spark adapter tests could not exercise the expected specialist intake in the
current Windows checkout environment; two registry tests observed `ready` where
the legacy fixture expected `invalid`; and the compatibility test found
`ecosystem-compatibility.json` declaring Spark AWS `0.7.1` while its current
`pyproject.toml` declares `0.7.2`. These are open findings, not accepted gates.

## L. Changed Files

Changed-file inventories are authoritative in each commit and in the release
dump. Main groups:

- `the-forge`: baseline collector/tests, master spec/reports, registry mapping,
  release dump.
- `product-forge`: runtime/portal/embedded Bridge and vendored Angular assets.
- `forge-agent-bridge`: replay, durable store, ordering, redaction and tests.
- `forge-cli`: Windows portable test executable.
- `code-atlas-forge`: release Action SHA pinning.
- `spark-forge-aws`: approval-gated lifecycle and tests.
- `platform-forge`, `forge-doctor-data`, `forge-doctor-api`: path/MCP fixes.
- `forge-portal`: MCP state typing, rendering, translations and tests.

## M. Commits & Pull Requests

All 14 working trees are clean and synchronized with `origin/main` after push.
The 11 repositories with changes were pushed successfully to `main`; the three
unchanged repositories were already synchronized. No pull request was created,
and no force-push or merge was performed. GitHub reported branch-protection
warnings (required PR/checks/signatures) while accepting the direct pushes; the
warnings are recorded rather than treated as CI success.

## N. Remaining Risks

- Full The Forge pytest completion still needs to be observed and recorded.
- Windows Bridge ACL/process portability needs a platform-native follow-up.
- Lens MCP support needs a formal tested revision matrix; current support is not
  expanded merely by changing an identifier.
- External provider, host, cloud, dependency and supply-chain gates remain open.

## O. External Blockers

1. Query remote CI, PR and release status against the exact post-change SHAs;
   the pushes succeeded, but those remote gates were not promoted to PASS here.
2. Provide authorized real-provider/host credentials and sandboxes for E2E
   homologation; no credentials were requested or exposed here.
3. Give separate explicit approval per PyPI/npm distribution before publishing.

## P. Release Readiness

Candidates are locally buildable and evidence-dumped for Forge CLI, Code Atlas,
Data Sentinel, Product Forge, Spark AWS, and the modified Python components.
They are **not approved for public publication** in this cycle. PyPI/npm
publication remains pending explicit authorization and remote release-gate
verification.
