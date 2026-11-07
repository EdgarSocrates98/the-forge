# Installation compatibility

The previous ecosystem gate remains the baseline: the CLI install matrix
covered 14 local projects with home/TUI/wizard surfaces, non-TTY guards,
streaming output and JSON/pipeline paths; the runtime smoke covered 28 version
and help invocations. The Forge gates were green at `5ba6753`.

Cycle 0.5 adds an audit rule: a project may satisfy installation compatibility
through a native, declared `<cli> install` command. A shell wrapper is not a
requirement by itself, because it is not portable across PowerShell, Git Bash,
macOS and Linux.

| Case | Evidence | State |
|---|---|---|
| user/project/workspace install contracts | The Forge install receipts and matrix | PASS locally |
| re-run/repair/uninstall/non-TTY | matrix and CLI contract tests | PASS locally |
| path with spaces and Windows PowerShell | Windows CI matrix | PASS in prior gate; keep in every PR |
| missing host / incompatible Python / permission denial | negative contract tests | PASS where covered; federated adapter cases pending |
| new specialist native install declarations | `forge.json:install_command` and CLI help | DECLARED; adapter promotion pending |

No global dependency installation or user file cleanup was performed during the
audit.
