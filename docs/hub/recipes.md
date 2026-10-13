# Recipes — problema → solução por forja

Cada forja tem `docs/learn/recipes/` com receitas no padrão didático
(o quê/por quê/quando/quando não, pré-requisitos, saída esperada,
verificação, limitações, erros comuns, uso por agentes).

## the-forge

| Problema | Receita |
|---|---|
| delegar intent ao especialista certo | [../learn/recipes/delegate-task.md](../learn/recipes/delegate-task.md) |
| descobrir qual forja atende um requisito | [../learn/recipes/discover-capability.md](../learn/recipes/discover-capability.md) |
| instalação governada plano→aprovação | [../learn/recipes/governed-install.md](../learn/recipes/governed-install.md) |

## Forjas irmãs

| Forja | Receitas (em `<repo>/docs/learn/recipes/`) |
|---|---|
| api-forge | analyze-contract · contract-diff · governed-case |
| spark-forge-aws | analyze-pyspark · scan-repo · doctor-extras |
| spark-forge-azure | analyze-pyspark · doctor · migration-assessment |
| platform-forge | inspect-repo · judge-policy · graph-deps |
| forge-doctor-data | scan-project · checks-profiles · explain-finding |
| forge-doctor-api | scan-contract · contract-diff · diagnose-explain |

## Guias completos

- [The Forge do zero à execução multi-especialista](../learn/zero-to-multi-specialist.md)
  — evidência real de ponta a ponta.
