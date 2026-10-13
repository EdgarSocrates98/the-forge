# Account-scoped installation

Run `install.sh` (POSIX) or `install.ps1` (Windows) from this checkout. Installer performs `pip install -e .` into an isolated account runtime under `~/.forge/installs/the-forge/.venv`. It does not create a virtual environment inside a project workspace.

Installer publishes user-scoped variables:

- `THE_FORGE_HOME`: source checkout used by editable install.
- `THE_FORGE_INSTALL_ROOT`: account runtime root.
- `THE_FORGE_VENV`: isolated Python environment.
- `THE_FORGE_PYTHON`: runtime interpreter.
- `THE_FORGE_CLI`: real CLI executable.
- `THE_FORGE_LAUNCHER`: PATH launcher when available.

Names use underscores because POSIX shells reject hyphens. Windows also receives compatibility aliases such as `THE-FORGE-HOME`, without administrator permission.

POSIX installer writes `~/.config/forjas/env.sh` and a guarded shell-init line. Open a new shell or run `source ~/.config/forjas/env.sh`. Windows processes opened after installation receive HKCU variables.

`setup.sh`/`setup.ps1` remains compatibility mode for wheel-style installation. `theforge doctor` validates published account paths. Portal exposes same check at `/api/v1/environment`.

## Homologação

O fluxo foi validado com os sete instaladores Python em PowerShell 5.1 e Git
Bash, sem privilégio administrativo. PowerShell 7 passou aplicação persistente
real 7/7; Linux Bash depende de uma distribuição WSL disponível. Evidências e gaps
atuais ficam em
[`audit/reports/THE_FORGE_FULL_ECOSYSTEM_CERTIFICATION.md`](../../audit/reports/THE_FORGE_FULL_ECOSYSTEM_CERTIFICATION.md).
