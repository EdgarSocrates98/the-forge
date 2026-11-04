# Prompt Evo Mastering Melhorias — current audit

**Decision:** `CERTIFICATION_BLOCKED`

**Prompt:** `E:\projetos\FORJAS\prompt_evo_mastering_melhorias.md`  
**Evidence root:** `audit/baseline/`, `audit/artifacts/`, `audit/reports/`  
**Collection host:** Windows; Python 3.14; PowerShell 5.1/7; Git Bash; Node/npm; GitHub CLI.

## Scope and evidence rule

The workspace currently exposes 14 checkout roots. The prompt describes 13
product/repository targets; the additional `the-forge` control-plane checkout
is included because it owns the orchestration, evidence and certification
artifacts. Every result below is tied to a command, artifact, SHA or remote CI
run. Historical Cycle 10.1 claims are retained only as provenance and do not
close current gates.

## Current baseline

The canonical machine-readable baseline is `audit/baseline/versions.json`.
It records declared versions, contract versions, SHA, latest CI, open PR count,
latest release and explicit `NOT_RUN`/`BLOCKED` states. Regenerate it with:

```text
python audit/tooling/collect_baseline.py --workspace-root .. --ref origin/main
```

The baseline intentionally includes `code-atlas-forge`, `data-sentinel-forge`,
`forge-portal` and `the-forge`, which were omitted from the older nine-root
report.

## Gate matrix

| Gate | Current state | Evidence / limitation |
|---|---|---|
| A — integrity and versions | PASS with findings | baseline JSON and manifest parity; dynamic versions and registry state remain explicit |
| B — static quality and contracts | CONDITIONAL | repository CI/contract evidence exists; final state follows the latest run per SHA |
| C — tests and integration | IN_FLIGHT | current The Forge, Portal, Platform, Product, Code Atlas, Lens, Bridge, API, Doctor Data and Azure CI are green; Doctor API and Spark AWS are still running |
| D — packaging/install | CONDITIONAL | 30 installer PASS, 10 Linux Bash BLOCKED; published duplicate-version gates safely refused overwrite |
| E — interoperability | CONDITIONAL | 19/19 deterministic scenarios, 6/6 MCP handshakes and contract validation pass; external-host and full cross-forge visual evidence remain unverified |
| F — agentic evals/knowledge | CONDITIONAL | product-specific evals and Platform economy receipt pass where run; external host validation remains unverified |
| G — release/provenance | CONDITIONAL | checksums/reports and safe duplicate detection exist; registry post-publish verification is incomplete |
| H — UX/onboarding | CONDITIONAL | bare-install wizard and Windows paths have tests; Linux and CUA visual journeys remain blocked |

## Completed engineering changes

- Normalized package manifests, versions and agent/capability contracts across
  the affected repositories.
- Added current 14-root baseline collection with CI, PR, release, contract and
  test provenance.
- Fixed the Windows installer executable-selection bug across all ten Python
  installers and added a regression test in The Forge.
- Implemented and verified the Spark AWS bare-install wizard contract for TTY,
  non-TTY, dry-run, confirmation, cancellation and doctor paths.
- Made Platform Forge validation invoke its local CLI portably on Windows and
  regenerated the economy receipt; the adversarial closure suite passes.
- Aligned Forge Portal's runtime version with `package.json`, normalized npm 12
  pack JSON, made release summaries ASCII-safe, and fixed the CI Prettier gate.
- Ran the requested PyPI/npm release actions. Existing versions were detected
  as already published, so no package was overwritten.

## Explicit blockers

1. Linux Bash requires a real Linux/WSL runtime; it is not simulated.
2. CUA visual evidence and some external host handshakes require capabilities
   unavailable in this session.
3. Deep security scans are not claimed without their required tools.
4. Certification must be regenerated after the remaining current CI runs and
   must report every failed, skipped, blocked and unverified item.

The artifacts are therefore implementation-complete for the changes executed
in this workspace, but the ecosystem is not certified as fully ready until the
explicit blockers above receive fresh evidence or release-owner acceptance.
