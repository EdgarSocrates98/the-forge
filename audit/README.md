# Forge ecosystem audit

Auditoria evidence-first do ecossistema Forge.

O programa de referência atual é `prompt_evo_auditabilidade.md`, no workspace
pai. A leitura de estado consolidada fica em
`reports/prompt-evo-auditabilidade.md`; ela aplica H0–H7 e mantém
`BLOCKED`/`UNVERIFIED` explícitos.

Este diretório é infraestrutura de validação e documentação. Não é importado
por nenhuma Forge e não participa do runtime de produção.

## Baseline

O baseline é coletado contra `origin/main` de cada repositório, sem trocar o
checkout ativo:

```powershell
python audit/tooling/collect_baseline.py --workspace-root .. --ref origin/main
```

Saídas:

- `baseline/repositories.json`: SHA, branch, runtime, instalação e comandos.
- `baseline/versions.json`: versões declaradas e tags remotas.
- `baseline/capabilities.json`: contratos, entry points, testes e workflows.
- `baseline/dependencies.json`: dependências declaradas e dependências Forge.
- `baseline/workflows.json`: workflows disponíveis por repositório.

Cada registro contém `provenance`, com comando, arquivo/ref e timestamp da
coleta. Ausência de evidência permanece explícita; o relatório não converte
documentação em `PASS`.

## Instaladores

Os sete repositórios Python que distribuem `install.ps1` e `install.sh` são
exercitados em modo seguro, sem alterar HKCU, PATH, perfis de shell ou o
checkout:

```powershell
python audit/tooling/run_installers.py `
  --worktree-root ..\.e2e-worktrees `
  --runtime-root .. `
  --artifact-dir audit/artifacts/installers-YYYY-MM-DD `
  --output audit/reports/installer-matrix.json
```

O runner executa PowerShell 5.1, PowerShell 7 e Git Bash real quando
disponíveis. Linux Bash recebe `BLOCKED` quando não há WSL/distribuição
instalada; `forge-cli` e `forge-portal` são `NOT_APPLICABLE` para esses
scripts e usam seus próprios fluxos npm/browser. A matriz não chama o modo
persistente do instalador, pois esse modo altera variáveis do usuário; o
bootstrap subjacente é validado separadamente em diretórios descartáveis.
O replay persistente de PowerShell 7 fica separado em
`reports/installer-powershell7-actual.json`, com stdout/stderr por repositório.

## Relatórios de homologação

- `reports/THE_FORGE_FULL_ECOSYSTEM_CERTIFICATION.md`: decisão global e
  limites de certificação.
- `reports/installer-apply.json`: aplicação real dos instaladores em conta
  sem administrador.
- `reports/compatibility-matrix.md`: matriz de compatibilidade e estados.
- `reports/manual-results.json`: evidências de suites longas, CLI, TUI,
  Portal, adapters reais e gates bloqueados.
- `reports/unresolved-gaps.md`: gaps priorizados; `BLOCKED` e `UNVERIFIED`
  permanecem explícitos.

O relatório global não converte documentação em evidência. Para reproduzir
aplicação real, use diretório descartável, subprocesso novo para ler HKCU e
preserve o checkout do produto fora do workspace do consumidor.
