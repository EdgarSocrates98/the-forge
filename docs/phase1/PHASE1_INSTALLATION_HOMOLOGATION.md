# Phase 1 installation homologation

No mandatory dependency on Obsidian, Node extraction or a vector database was
introduced. The existing installers remain the installation authority. The
portable installer matrix passed on PowerShell 5.1, PowerShell 7 and Git Bash;
Linux Bash is blocked by the host's missing WSL capability.

The safe runtime entry-point smoke also passed for all 14 repositories: 28/28
commands (`--version` and `--help`) returned exit code 0, including the Node
Forge CLI and Portal CLI. This proves installed entry-point discoverability and
help surfaces; it deliberately does not claim that mutating install wizards or
live cloud actions were executed.
