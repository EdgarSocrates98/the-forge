# Phase 1 installation homologation

No mandatory dependency on Obsidian, Node extraction or a vector database was
introduced. The existing installers remain the installation authority. The
portable installer matrix passed on PowerShell 5.1, PowerShell 7 and Git Bash;
Linux Bash is blocked by the host's missing WSL capability.

The reproducible command is `python scripts/cli_runtime_smoke.py`. It passed
for all 14 repositories: 28/28 commands (`--version` and `--help`) returned
exit code 0, including the Node Forge CLI and Portal CLI. The companion
`python scripts/cli_install_matrix.py --check` also passed 14/14: every
repository has source evidence for both-stream TTY detection, a visual
install/wizard surface, a machine-readable path and a no-TTY guard. This is
the canonical cross-repository contract for the practical CLI experience.

The runtime TTY gate was also executed in a real Windows pseudo-terminal with
`uv run --with pywinpty python scripts/cli_tty_smoke.py --seconds 8`. It passed
14/14 with a visible first screen for every CLI, including the Portal menu and
Forge CLI wizard. Each process was interrupted before a selection or
confirmation; `interrupted_before_mutation=true` for all 14 cases. The JSON
receipt is retained at
`E:\projetos\FORJAS\the-forge\.audit-work\cli-tty-runtime-smoke-current.json`.
This closes the gap between source inspection and an actual TTY surface, but
still does not claim that a mutating install or live cloud action was run.

These checks prove discoverability, help surfaces and the declared interactive
contract. They do not claim that mutating install wizards or live cloud actions
were executed; those remain governed by a real TTY, explicit approval and
provider credentials. A non-interactive invocation must remain deterministic
and must not block waiting for input.

The no-flag cancellation path was also exercised with
`uv run --with pywinpty python scripts/cli_tty_cancel_smoke.py --seconds 3`.
It passed `14/14`: every bare command rendered a visible home surface, accepted
its documented cancel interaction (`q`, `Esc` or `q+Enter` according to the
prompt implementation), and exited before mutation. This is stronger than a
source-only wizard claim, while still intentionally stopping before applying an
installation.

## Installation plan matrix

The installation routes were then invoked in non-mutating plan mode on the
same Windows host. The common Python bootstrap produced a valid
`status=planned`, `manifest_valid=true` plan for 10 repositories:

```text
api-forge, forge-agent-bridge, forge-doctor-api, forge-doctor-data,
forge-lens, platform-forge, product-forge, spark-forge-aws,
spark-forge-azure, the-forge
```

The four repositories with independent installers were checked through their
native route:

| repository | command | result |
| --- | --- | --- |
| code-atlas-forge | `uv run python scripts/install_portable.py --dry-run` | PASS, no files written |
| data-sentinel-forge | `uv run python scripts/install_portable.py --dry-run` | PASS, no files written |
| forge-cli | `node dist/index.js install the-forge --plan --json` | PASS, exit 0, valid JSON |
| forge-portal | `node scripts/install_portable.mjs --dry-run` | PASS, `mutates=false` |

This closes the plan-generation check for all 14 repositories without
pretending to be a mutating install. Applying a plan still requires an
explicit user approval and remains a separate gate.
