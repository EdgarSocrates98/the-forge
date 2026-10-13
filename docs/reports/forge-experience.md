# Forge Experience — cycle report

Branch `feat/forge-experience`, 7 repos. Format §13; status only with
executed evidence.

```text
CYCLE: 1+3+4 (foundation, command center, ecosystem parity)
SCOPE: interactive CLI, install wizard, command center, headless contract
REPOSITORIES: all 7
IMPLEMENTED:
  - theforge/ui kit: stdlib ANSI interaction (msvcrt/termios), zero deps,
    capability-detected (tty/color/unicode/width), i18n pt/en
  - Command Center: bare `theforge` TTY → dashboard (real specialists
    lifecycle, hosts evidence, recent delegations) + menu of real actions
  - Install wizard: env check → scope → profile → hosts → real dry-run
    review → confirm → governed apply → doctor; drives the real install
    service per repo (script-backed in forge-doctor-api)
  - Per-forge homes: menu entries resolve real CLI argv (installed
    launcher else checkout cli_entry) and subprocess them; verbs validated
    against commands.generated.json
  - docs/experience/ ×5 per repo (interactive-cli, installation-wizard,
    automation-mode, accessibility, themes)
CLI: PASS — bare invocation opens home on TTY, keeps summary/help off-TTY
TUI: PASS — interactive kit implemented + unit-tested (20 tests, scripted
     key sequences through the real select/multi_select loops)
INSTALLATION: PASS — wizard drives real install service; plan is the
             real dry-run receipt; apply is the governed --yes path
PROFILES: PASS — Balanced/Economy/Full mapped to recommended/minimal/full
HOSTS: PASS — wizard env-check probes real binaries; Command Center uses
       evidence-based host_detect
MCP: PASS(decl) — mcp-verify menu entry runs the real handshake verb
SKILLS/AGENTS: PASS — explorer entries run the repo's real agents verb
TASK EXECUTION: PASS — "run a task" in the-forge home delegates via real
                argv and records to .forge/delegations/
HEALTH: PASS — doctor entries call each repo's real doctor
DOCUMENTATION: PASS — check_docs 0 problems in all 7 repos (~2800 files)
ACCESSIBILITY: PASS(decl) — keyboard-first, NO_COLOR/TERM=dumb degrade,
               non-UTF8 ASCII glyphs, no animation, headless linear
               equivalent; screen-reader TUI support UNVERIFIED
SECURITY: PASS — wizard applies only after explicit confirm; non-TTY
          install is a usage error, never an implicit yes; vendored code
          exempted via per-file-ignores (installkit convention)
UNIT TESTS: PASS — 24 tests (kit, i18n, wizard, home, parity)
INTEGRATION TESTS: PASS — parity gate: byte-identical vendored kit +
                   bare-entry wiring + menu-verb inventory validation
REAL PROVIDER TESTS: PARTIAL — argv resolution tested; per-menu live
                     execution exercised for the-forge delegation path
REAL HOST TESTS: UNVERIFIED — no PTY available on Windows CI-less env;
                  interactive loop covered by scripted-key unit tests
E2E TESTS: PARTIAL — bare non-TTY paths verified; full TTY session E2E
           requires a real terminal (unit tests drive the same code path)
CROSS-PLATFORM: PARTIAL — msvcrt path unit-tested; termios path covered
                by POSIX _read_key; real POSIX terminal UNVERIFIED
PERFORMANCE: PASS — kit is ~450 LOC stdlib; bare import adds no deps;
             subprocess argv runs only on user selection
KNOWN LIMITATIONS:
  - Full-screen TUI (alt-screen, mouse, live widgets) is a deliberate
    non-goal for v1 — summon-choose-exit inline menus; Textual remains
    api-forge's optional extra for its task TUI
  - Menu actions stream subprocess output inline; long-running verbs
    show native output, not a TUI progress widget
  - FORGE_LANG covers UI chrome; domain output keeps each forge's own
    language
REMAINING GAPS:
  - Results explorer / run-history browser beyond the recent-tasks list
  - Execution visualization (handoff graph) — data exists in receipts,
    renderer not yet built
  - Real-terminal acceptance on POSIX + Windows Terminal pending
FINAL STATUS: PASS (with declared UNVERIFIED/PARTIAL)
```
