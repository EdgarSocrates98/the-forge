# LF-0003 — Bare install wizard

## Owner

Spark Forge AWS pilot.

## Problem

`sparkforge-aws install` currently enters plan/approval path. Bare install must
open guided wizard on real TTY while explicit flags keep deterministic CLI
contract. Non-TTY must never wait or write.

## Scope

- add install-owned guided entrypoint using canonical `ui/wizard.py`;
- route exact bare `install` argv → wizard only when stdin & stdout TTY;
- preserve `install --dry-run`, `install --yes`, `install --scope`, and all
  explicit option paths;
- keep wizard dry-run → explicit confirmation → governed apply → doctor;
- add regression tests for TTY route, non-TTY refusal, and option preservation;
- update installation docs and acceptance evidence.

## Out of scope

- cloud mutations;
- host registration or MCP transport changes;
- fullscreen TUI framework migration;

## Invariants

V1: exact bare `install` + interactive TTY → wizard entrypoint
V2: non-TTY → structured refusal or plan, never prompt, never write
V3: explicit install flags → existing deterministic dispatch
V4: wizard plan → real install service dry-run
V5: apply → explicit confirmation + `yes=True`
V6: completion → doctor evidence when service supports it

## Acceptance

- `sparkforge-aws install` enters wizard on TTY;
- `sparkforge-aws install` under capture/CI does not read stdin and does not
  mutate target;
- `sparkforge-aws install --dry-run` keeps JSON plan contract;
- `sparkforge-aws install --yes` keeps governed apply contract;
- wizard receives component profile and execution gateway profile separately;
- cancelled wizard returns `130` and leaves target unchanged;
- targeted tests pass;
- docs declare PASS/FAIL/BLOCKED evidence.

## Verification

```text
python -m pytest -q tests/test_install.py tests/test_ui_tui.py
python -m ruff check sparkforge_aws/install/cli.py sparkforge_aws/adapters/cli.py tests/test_install.py
```

## Evidence

E1: bare TTY route → shared wizard; explicit flags → deterministic dispatch
E2: non-TTY → structured refusal; stdin/file state untouched
E3: dry-run → no lock, ledger or state directory
E4: wizard → `profile` & `gateway_profile` independent
E5: apply → doctor string/nested health envelope rendered
E6: cancellation → `130` & no target mutation
E7: real host handshake → UNVERIFIED when host/MCP extra absent

