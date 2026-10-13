# Design system v1 — Forge Experience 3.0 (Cycle 1.4)

Shared contract for every Forge TUI. Implemented in `ui/screen.py` +
`ui/kit.py`; this doc is the normative description.

## Canvas & layout

```
┌─ header ───────────────────────────────────────────┐  2 rows
│  FORGE NAME · screen title            env · status │
├─ body ─────────────────────────────────────────────┤  h-4 rows
│  panels / tables / trees / state views             │
├─ footer ───────────────────────────────────────────┘  2 rows
│  key bar: ↑↓ navigate · enter select · q quit        │
```

- Minimum usable: **60×16** — below that the whole body becomes the
  `too_small` state view (never a broken layout).
- Layout contract: header/footer fixed, body is the only scroll region.
- All drawing goes through `Buffer`; business state never touches stdout.

## Themes & identity

Each Forge has an accent color; state colors are invariant across Forges:

| Token | ANSI | Meaning |
|---|---|---|
| `accent` | per-Forge | title bars, selected option marker |
| `ok` | 32 green | success state, healthy checks |
| `warn` | 33 yellow | degraded, warnings |
| `err` | 31 red | failures, refusals |
| `info` | 36 cyan | informational labels |
| `dim` | 2 | secondary text, hints |
| `focus` | reverse video | focused element (keyboard nav) |

Accent defaults: the-forge `33` (gold), api-forge `34` (blue),
spark-forge-aws `35` (magenta), spark-forge-azure `36` (cyan),
platform-forge `32` (green), forge-doctor-* `37` (silver).

`NO_COLOR` or `TERM=dumb` → all styling off; status must still read
from text + icon, never from color alone.

## State vocabulary (mandatory coverage)

Every screen must render — from real state, never hardcoded:

`empty` · `loading` · `ready`/`success` · `error` · `disconnected` ·
`too_small`

`StateView` renders each with icon + title + detail + recovery hint.
States are color-independent: `OK`/`FAIL`/`…`/`!` text icons always
accompany color.

## Interaction contract

- **Keys:** `↑/k` up · `↓/j` down · `enter` select · `space` toggle ·
  `tab` next pane · `q`/`esc` back or quit · `?` help · `/` search
  (where applicable).
- Focus is always visible (reverse video or `>` marker in ASCII mode).
- Event loop polls input at ≤50 ms; render is dirty-only on state
  change + resize (`SIGWINCH`/Windows `kbhit` poll of size).
- `q` from the root screen exits; `esc`/`q` inside a pane goes back.

## Lifecycle & safety

- `Screen` context manager: enter → alt screen + cursor hide + raw
  mode; exit → **always** restore (try/finally), even on exception or
  SIGINT — no terminal left in alt screen.
- Non-TTY: no alt screen ever; commands degrade to one-shot
  `dashboard()`/`status_table()` output or `NonInteractive` refusal —
  never escape garbage on pipes.
- stdout is the only UI channel; diagnostics/log lines go to stderr.

## Unicode & fallback

| Capability | Box | Icons | Cursor |
|---|---|---|---|
| UTF-8 + ANSI | `─│┌┐└┘` | `● ○ ▶ ✓ ✗` | `>` |
| ASCII only | `-|++++` | `o . > + x` | `>` |

Chosen once in `UIContext.detect()`; never mixed within a screen.
