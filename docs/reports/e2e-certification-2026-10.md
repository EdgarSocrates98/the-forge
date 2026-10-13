# E2E certification — 2026-10

Auditoria operacional baseada em `prompt_evo_e2e.md` e
`prompt_evo_homolog_e2e.md`.

## Resultado

Estado: `CERTIFIED_WITH_LIMITATIONS` candidate. Não há `CERTIFIED` enquanto
CI central, Linux Bash, CUA visual, Portal cross-forge e demais itens de
`audit/reports/unresolved-gaps.md` não fecharem.

## Evidência

O relatório executável está em
[`audit/reports/THE_FORGE_FULL_ECOSYSTEM_CERTIFICATION.md`](../../audit/reports/THE_FORGE_FULL_ECOSYSTEM_CERTIFICATION.md).
Matrizes, comandos e artefatos ficam em `audit/`. Estados permitidos:
`PASS`, `FAIL`, `BLOCKED`, `UNVERIFIED`, `NOT_APPLICABLE`.

## Instalação de conta

Sete produtos Python passaram aplicação real de `install.ps1` e `install.sh`
em conta sem administrador. Cada caso confirmou venv, `pip install -e .`,
launcher e variáveis `*_HOME`, `*_INSTALL_ROOT`, `*_VENV`, `*_PYTHON`,
`*_CLI`, `*_LAUNCHER` em HKCU. PowerShell 7 também passou replay persistente
7/7. Ver
[`audit/reports/installer-apply.json`](../../audit/reports/installer-apply.json).

## Reprodução segura

1. Execute baseline contra `origin/main`.
2. Use worktrees/diretórios temporários.
3. Nunca faça cloud apply/deploy.
4. Rode instalador real apenas em conta de teste.
5. Valide variáveis em processo filho novo.
6. Anexe stdout, stderr, duração, SHA e exit code.
7. Preserve `BLOCKED` quando runtime externo faltar.
