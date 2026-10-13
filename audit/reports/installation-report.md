# Installation report

## Applied installers

`audit/reports/installer-apply.json` contém matriz real. Sete repositórios Python passaram `install.ps1` e `install.sh` fora do checkout, com `.venv`, `pip install -e .`, launcher, smoke `--version` e persistência em `HKCU\Environment`. Execução não exigiu administrador.

PowerShell 5.1 e Git Bash foram executados de verdade. PowerShell 7 passou dry-run 7/7. Linux Bash ficou `BLOCKED` por ausência de distribuição WSL; não é convertido em PASS.

## Fixes found during homologation

Aplicação real revelou duas regressões Windows no bootstrap: uso incorreto de `PyHKEY.QueryValueEx` e abertura sem `KEY_QUERY_VALUE`. Corrigidos em `scripts/installkit/forge_bootstrap.py`, cópia vendorizada e teste dedicado. Regressão: nove testes do bootstrap passaram.

## Reproduction

```powershell
python audit/tooling/run_installers.py --worktree-root ..\.e2e-worktrees --runtime-root .. --artifact-dir audit/artifacts/installers-YYYY-MM-DD --output audit/reports/installer-matrix.json
```

Aplicação real deve usar diretório descartável, conta sem privilégios administrativos e processo filho novo para validar variáveis persistidas.
