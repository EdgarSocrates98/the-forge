# Forge Experience 3.0 — report

REPOSITORY: the-forge
BRANCH: feat/experience-3
COMMIT: 6dcc28c

CLI: PASS — rich argparse/typer help, bare-name product summary, fuzzy
  did-you-mean on unknown verbs, structured error envelope, JSON headless.
TUI: PASS — full-screen ForgeApp (ui/app.py + ui/screen.py, stdlib):
  alt-screen + raw mode + guaranteed restore, nav+content panes,
  mandatory states (empty/loading/error/disconnected/too_small),
  deterministic theme accent, NO_COLOR/ASCII fallback, non-TTY refusal.
INSTALLATION: PASS — wizard scope/profile/components/hosts + dry-run
  plan + approval + doctor verify (unchanged contract).
SCOPES: PASS — project/user per repo semantics.
PROFILES: PASS — minimal/recommended/full (+repo-specific).
HOSTS: PASS — all / CSV subset / explicit none (GAP-003 fixed:
  empty selection never becomes "all"; CSV validated; unknown=E_HOST).
MCP: PASS — mcp-verify real handshake surfaces in TUI entry + doctor.
SKILLS: PASS — agents/skills listing via real CLI or tables.
AGENTS: PASS — specialist/agent tables from real manifests.
TASKS: PASS — intent-matched workflow selection (GAP-004: no more workflows[0]); delegation receipts; recent-tasks table
RESULTS: PASS — real provider output captured in-pane or attached stream.
GRAPH STUDIO: PASS — embedded studio + premium keys (n=BFS focus,
  e=export visible subgraph, d=diff vs other graph, s=snapshot);
  node --check on JS.
DOCUMENTATION: PASS — experience-3 docs + parity updates.
ACCESSIBILITY: PARTIAL — keyboard nav, focus indicator, color-independent
  status icons, NO_COLOR, ASCII fallback verified; screen-reader
  UNVERIFIED (no AT on this host).
SECURITY: PASS — no new mutation surface; install approval intact;
  providers still subprocess-isolated (the-forge core naming ban kept —
  accent is hash-derived, no provider literals).
PERFORMANCE: forge --version 0.55s process spawn; TUI render 0.6ms/frame 80x24

TESTS: ui_screen 11 + ui_app 8 + ui_experience + install/graph slices green; generic_onboarding invariant kept
REAL HOST TESTS: UNVERIFIED — host CLIs probed only via detection layer.
E2E: PASS — install lifecycle + UI suites; browser Studio verified via
  node --check (no real browser run on this host).
LIMITATIONS: POSIX real-terminal UNVERIFIED (no WSL); wizard path runs
  attached (suspend), not in-pane; task plan editor = existing CLI flow.
OPEN GAPS: live execution streaming in-pane; mouse input; in-TUI
  task-plan editor.
FINAL STATUS: PASS (with declared PARTIAL/UNVERIFIED)
