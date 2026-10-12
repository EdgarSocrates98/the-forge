---
id: lf-0004
title: Harden Rui cross-forge terminal experience
agent: codex
risk: medium
grill: completed
verification:
  - python -m pytest tests/test_ui_screen.py tests/test_ui_app.py
  - python -m pytest tests/test_ui_tui.py
---

# Grill Gate

- Owner: repository operator.
- Problem: Rui TUI must stay legible, responsive, recoverable across terminal sizes, shells, encodings, ANSI modes, and closed input.
- Out of scope: new product flows, mouse support, required runtime dependencies, provider behavior.
- Review failure: clipping essential content, hidden navigation, blocking EOF/resize path, broken ANSI/ASCII fallback, suspended action corrupting terminal state, docs claiming unverified host support.
- Riskiest assumption: stdlib screen engine remains canonical across seven Forjas with package-local copies.
- Smallest acceptable: shared-behavior hardening, regression matrix, docs parity, per-repository commits.

# Context

Rui uses seven package-local copies of stdlib UI kit + screen engine. Existing base covers TTY gating, alternate screen, raw mode, ANSI/Unicode fallback, and minimum layout. Audit found edge failures at narrow widths, long menus, POSIX key bursts, EOF, and suspended action output.

# Acceptance Criteria

- All seven TUIs preserve non-TTY refusal and headless CLI fallback.
- Layout adapts at 60x16, 80x24, 100x30, 120x40, and 160x50; essential labels remain visible or receive explicit scroll/truncation feedback.
- Tables allocate widths within viewport; navigation window keeps selected entry visible.
- POSIX ANSI sequences, Windows extended keys, Ctrl-C, and EOF normalize without infinite loops.
- Resizes refresh dimensions from active output stream without crashing.
- Suspended actions restore terminal state before execution and after return; attached output remains attached.
- `NO_COLOR`, `TERM=dumb`, non-UTF-8, PowerShell, Windows Terminal, SSH, and pipe behavior remain explicit in capability detection/docs.
- Regression tests cover pure render, boundary dimensions, key normalization, suspended execution, and non-TTY behavior.
- Accessibility docs state keyboard-first, color-independent states, ASCII fallback, and screen-reader limitation honestly.

# Constraints

- No required third-party runtime dependency.
- Keep package-local public imports stable.
- No provider, install, MCP, credential, or mutation policy changes.
- Do not overwrite pre-existing unrelated worktrees.
- Real external PTY/ConPTY validation remains `UNVERIFIED` unless executed observably.

# Review Notes

- Compare behavior across all seven copies; reject drift in key/layout contracts.
- Inspect cleanup on exceptions, Ctrl-C, EOF, resize, and subprocess return.
- Verify docs match measured tests; do not promote host claims without evidence.
