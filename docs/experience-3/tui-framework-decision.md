# TUI framework decision — Forge Experience 3.0 (Cycle 1.3)

Status: decided · 2025 — applies to all 7 Forges.

## Delivery update — 2026-10-11

The stdlib engine remains the portable baseline. The full-screen app now
normalizes `Shift+Tab`, Page Up/Page Down and Home/End, supports a real `/`
filter query with backspace/escape handling, and scrolls text/action panes.
These changes stay dependency-free and preserve the non-TTY refusal contract.

The 2026-10-12 Rui hardening wave adds viewport-aware table allocation,
selected-item visibility for long menus, active-stream resize probing,
byte-safe POSIX CSI parsing, clean EOF handling, and attached execution
output for suspended actions. The seven package-local copies keep the same
behavioral contract; no runtime dependency was added.

Textual remains optional for `api-forge`; no required dependency or platform
migration was introduced during the 0.2 RC freeze. The official Textual
documentation confirms Windows support and headless asyncio/Pilot testing,
while Microsoft ConPTY guidance requires careful channel separation and
resize handling. Those references inform a future optional pilot, not a
claim of real-host verification in this delivery.

References:

- https://textual.textualize.io/getting_started/
- https://textual.textualize.io/guide/testing/
- https://learn.microsoft.com/en-us/windows/console/creating-a-pseudoconsole-session

## Options evaluated

| Option | Footprint | Portability | Fit |
|---|---|---|---|
| **Textual** | +textual, rich, pygments, platformdirs (~15 MB wheel set) | pip-dependent; heavy for portable installs | Already used by `apiforge.tui` as optional extra |
| **Rich only** | +rich (~5 MB) | pip-dependent; no input/event loop — still need raw mode | Rendering lib, not a TUI framework |
| **stdlib screen engine** (chosen) | 0 deps | msvcrt + termios already in `ui/kit.py`; works in pip-less portable installs | Full control, vendored, testable state machines |

## Decision

**A shared stdlib full-screen engine (`ui/screen.py`) is the canonical TUI
for all 7 Forges.** Rationale:

1. **Zero-dependency constraint is real, not aesthetic.** Every Forge ships a
   portable install that must work in pip-less environments (`uv`-only venvs,
   offline runners). A required Textual/Rich dep would break that contract.
2. **The capability already exists.** `ui/kit.py` ships raw mode (Windows
   `msvcrt`, POSIX `termios`/`tty`), ANSI gating, `NO_COLOR`, non-UTF-8
   fallback, `NonInteractive` refusal — a full-screen engine needs alt-screen
   + buffered render + event loop on top, nothing external.
3. **Determinism & testability.** State → Buffer → ANSI string is a pure
   function; we can test 80×24, 60-col and minimum layouts without a PTY.
4. **Identity.** One design system → consistent look, per-Forge accent
   themes; Textual apps diverge by default.

## Non-goals / honest boundaries

- api-forge keeps its **existing** Textual app (`apiforge tui`) as an
  optional power-user path; it is *not* the platform requirement.
- The stdlib engine is not a widget framework — it provides Screen,
  Buffer, Panel, Table, KeyBar, StateView, focus and an event loop.
  Complex compositional UI stays out of scope for v1.
- Mouse input: not implemented (keyboard-only by design).
