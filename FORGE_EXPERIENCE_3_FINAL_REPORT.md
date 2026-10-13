# Forge Experience 3.0 — Final Report

Program: `prompt_evo_3,0.md` (5 cycles). Branch `feat/experience-3` on all
7 repos. Delivered in waves, one commit per wave per repo.

## Cycle summary

| Cycle | Deliverable | Status |
|---|---|---|
| 0 audit | `docs/experience-3/` — tool inventory, baseline, 9 audits | DONE |
| 1 repair | GAP-002 components propagated (was silently dropped by `**kw` lambda); GAP-003 host `none`/CSV contract ×7 (empty selection never becomes `all`); GAP-004 intent-matched workflow selection (no `workflows[0]`) | DONE |
| 1 design | `tui-framework-decision.md` — stdlib screen engine (zero deps; Textual stays optional in api-forge); `design-system.md` v1 | DONE |
| 2 TUI | Full-screen `ui/screen.py` + `ui/app.py` + `ui/tui.py` ×7; `run_home` routes ANSI→TUI, dumb→inline kit, non-TTY→`NonInteractive` | DONE |
| 2 CLI | Already super (rich help, bare summaries, fuzzy suggestions, structured errors, JSON headless) — verified ×7 | DONE |
| 3 Command Center | 10 entries bound to real providers: workspace status, specialists, capabilities, run-a-task, hosts, mcp status, graph studio, install wizard, health, recent tasks | DONE |
| 4 Graph Studio | n=BFS-2 focus, e=subgraph export, d=diff (+added ~changed −removed), s=snapshot/restore; `n=neighbors` footer lie removed; JS `node --check` ×7 | DONE |
| 5 polish | Perf measured; a11y partial; headless verified; limitation list honest | DONE |

## Parity matrix (per-repo evidence: `docs/reports/experience-3.md`)

| Surface | the-forge | api | aws | azure | platform | d-data | d-api |
|---|---|---|---|---|---|---|---|
| Super CLI | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Full-screen TUI | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Install wizard | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | script |
| Host none/CSV | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| MCP verify | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Graph Studio keys | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Intent workflow routing | ✓ | n/a | n/a | n/a | n/a | n/a | n/a |

## Real bugs found & fixed this program

- `install_fn` `lambda **kw` → signature probe never passed `components`
- `_hosts` variants: empty/`none` → `all` (silent full-host install)
- `manifest.workflows[0]` — intent ignored
- `_MENU` bare-string/list pair (`Graph Studio`) broke inline select ×6
- `n=neighbors` footer hint with no implementation (fake control)
- `_ACCENTS` named real providers in the-forge core → hash-derived accent

## Verified numbers

- `forge --version`: 0.55 s cold process spawn (Windows 11, uv env)
- TUI frame render 80×24: 0.6 ms (pure Buffer→ANSI, no I/O)
- Test evidence: the-forge 19 ui tests + slices green; siblings `test_ui_tui` 4/4 ×6 + install lifecycle suites

## Declared limitations (not hidden)

- POSIX real-terminal behavior: UNVERIFIED (no WSL on this host)
- Screen-reader interaction: UNVERIFIED (no AT present)
- Browser Graph Studio: JS syntax-gated via `node --check`; no real
  browser session captured
- Task plan editor: existing suspend-to-CLI flow, not in-pane
- Mouse input: not implemented (keyboard-only, by design)
- Live execution streaming in-pane: not implemented (attached suspend)

## FINAL STATUS

PASS with declared PARTIAL/UNVERIFIED items — no fake buttons, no
invented metrics, no weakened tests.
