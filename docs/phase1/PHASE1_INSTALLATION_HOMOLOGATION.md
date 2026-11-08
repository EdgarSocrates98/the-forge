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
`uv run --with pywinpty python scripts/cli_tty_smoke.py --seconds 12`. It passed
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
