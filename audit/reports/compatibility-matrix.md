# Compatibility matrix

Data: 2026-10-12/13. Estado só muda para `PASS` com execução e evidência.

| Área | Estado | Evidência |
|---|---|---|
| Python specialists | PASS | AWS 14913 pass; Azure 3051; API 1887; Doctor API 1787; Doctor Data 2666 |
| The Forge targeted integration | PASS | adapter, provider-conformance e cross-forge real |
| Native AWS surface | PASS | snapshot/catalog reconciliado; aliases old/new resolvidos |
| Native Platform surface | PASS | snapshot regenerado contra runtime 0.1.0 |
| Forge CLI | PASS | 296/296, TUI focused 3/3, build/pack |
| Forge Portal | PASS | 11 browser E2E, 366 i18n, 43 Python, vendor 7/7 |
| install.ps1 | PASS | sete produtos Python aplicados em PowerShell 5.1 |
| install.sh | PASS | sete produtos Python aplicados em Git Bash |
| PowerShell 7 installer | PASS | dry-run 7/7 |
| Linux Bash installer | BLOCKED | sem distribuição WSL disponível |
| CUA visual terminal | BLOCKED | runtime CUA indisponível neste host |
| Portal cross-forge runner | BLOCKED | bounded wait excedido antes da primeira URL |
| Deep security scan | BLOCKED | permission profile gerenciado ausente |
| Snyk SCA | PASS | execução concluída; achados pré-existentes registrados |

## Independence

The Forge não é dependência runtime dos especialistas. Forge CLI e Portal permanecem opcionais. Contratos nativos foram exercitados por adapters sem import circular.

## Known dependency findings

Snyk encontrou `pygments 2.19.2` em quatro fixtures temporárias e `zod 4.6.5` no Portal. Os caminhos são pré-existentes; nenhum foi introduzido nesta onda. O zod high não possui upgrade/patch disponível no scan.
