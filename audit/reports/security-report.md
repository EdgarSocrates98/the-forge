# Security and supply-chain report

| Controle | Estado | Nota |
|---|---|---|
| Snyk SCA | PASS | 13 projetos analisados; resultado salvo em `snyk-sca.json` |
| Deep scan | BLOCKED | ferramenta exigiu permission profile gerenciado inexistente |
| Instalador sem admin | PASS | HKCU only; sem escrita em HKLM |
| Caminhos e checkout | PASS | testes em worktrees/diretórios descartáveis |
| Cloud mutation | PASS | nenhuma AWS/Azure apply/deploy/migração executada |
| Branch protection | PASS | `branch-protection.json`: nove main rulesets ativos; owner review/bypass |
| Dependency findings | UNVERIFIED_FOR_RELEASE | quatro fixtures com Pygments medium; Portal zod high sem patch |

Achados Snyk são mantidos como risco de release, não ocultados. Não houve dependência nova introduzida pelas correções desta homologação.
