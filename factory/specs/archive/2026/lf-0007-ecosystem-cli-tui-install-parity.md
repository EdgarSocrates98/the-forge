---
id: lf-0007
title: ecosystem CLI, TTY/TUI and install parity
agent: codex
risk: high
grill: completed
verification:
  - python scripts/cli_install_matrix.py --check
  - python scripts/cli_install_smoke.py --check
  - python scripts/dump_all.py --check
---

# Ecosystem CLI, TTY/TUI and install parity

## Owner

Ecosystem operator / FORJAS maintainers.

## Problem

The FORJAS projects are intended to feel like one product family, but their
CLI entry points and installers do not yet expose one auditable interaction
contract. Some projects have the canonical arrow-key UI kit and a guided
installer, while others still enter through plain Typer prompts or return
machine-shaped output even on a human terminal. The user specifically requires
TTY/TUI behavior in the CLIs and a visual, intuitive, practical install flow
matching `sparkforge-aws install`.

## Scope

- Audit all 14 repositories in the FORJAS release train.
- Define and record the capability matrix for CLI, bare install, guided install,
  human rendering, JSON/pipeline fallback, cancellation and no-argument UX.
- Close the highest-impact parity gaps without changing provider/domain logic or
  breaking existing flags and subcommands.
- Preserve deterministic automation: non-TTY never prompts or writes unless
  explicitly approved, `--dry-run` remains read-only, and `--json` remains
  parseable on stdout.
- Document intentional surface differences, especially the browser-only
  `forge-portal`, and add executable evidence for the contract.

## Out of scope

- Replacing the Portal web application with a terminal UI.
- Introducing a new runtime UI dependency where the existing stdlib or
  `@clack/prompts` implementation already satisfies the contract.
- Changing cloud/provider integrations, install semantics, or public command
  names merely for visual consistency.

## Acceptance criteria

1. A checked-in matrix covers all 14 repositories and classifies their visual
   surface: full home/TUI, guided installer, human renderer, JSON/pipeline
   fallback, or intentional web-only surface.
2. Every CLI installer follows the same gate: bare `install` on both a real
   stdin and stdout TTY enters a visual guided flow; non-TTY never prompts or
   writes without explicit approval; `--dry-run` previews without writes; cancel
   exits cleanly without writes; JSON mode does not mix human decoration into
   stdout.
3. Python projects use their canonical UI kit/wizard or a documented equivalent.
   Any plain prompt path reachable by bare install is removed or made unreachable
   on the guided route.
4. The TypeScript `forge-cli` keeps its `@clack/prompts` visual flow and explicit
   stdin/stdout TTY checks while preserving quiet/JSON output.
5. `forge-portal` is explicitly classified as a web visual surface, with the
   CLI/install contract documented rather than falsely claiming TUI support.
6. Specialist CLIs either provide a visual no-argument home/dashboard or clearly
   document the next action; no silent mutation occurs on an empty invocation.
7. Automated smoke checks cover real-TTY routing, pipe/CI safety, JSON purity,
   cancellation, packaging entry points, and matrix completeness.
8. Review evidence is recorded under `the-forge/audit/reports` and the final
   ecosystem dump includes the contract and test results.

## Review gate

Use existing repository tests and the canonical UI drift checks as evidence.
Review must distinguish a true capability from a file that merely exists, and
must not claim full-screen TUI support where the project only has a guided
installer or web surface.
