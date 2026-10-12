# Federation Compatibility Matrix

Compatibility means declared adapter surface, not brand recognition. `unknown` never becomes `supported` by fallback.

| Surface | Claude | Codex | Devin | Copilot | Non-TTY |
|---|---|---|---|---|---|
| human CLI | supported | supported | supported | supported | supported |
| guided setup | supported | supported | supported | supported | dry-run/explicit flags |
| skills | declared by profile | declared by profile | declared by profile | declared by profile | files only |
| agents | declared by profile | declared by profile | declared by profile | declared by profile | files only |
| MCP | negotiated | negotiated | negotiated | negotiated | explicit config only |
| full Rui/TUI | ANSI TTY | ANSI TTY | ANSI TTY | ANSI TTY | unavailable; one-shot output |
| JSON audit | supported | supported | supported | supported | supported |
| Portal | browser | browser | browser | browser | browser |

## Scope selection

- `user`: global host integration.
- `workspace`: shared workspace directory.
- `project`: repository/directory-local files.
- `profile=minimal`: MCP + TUI core.
- `profile=recommended`: skills + agents + MCP + TUI + graph studio.
- `profile=full`: all available components; still approval-gated.

## Host behavior

The Forge detects host and adapter capability. Install plan declares changes, permissions and rollback. Unsupported host remains visible with next action. No silent write.

## Terminal behavior

Rui detects TTY, ANSI, color, Unicode, width and height. `NO_COLOR`, `TERM=dumb`, cp1252 and cp65001 are handled explicitly. Resize redraws; too-small view shows recoverable state; pipes receive one-shot output.
