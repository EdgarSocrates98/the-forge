# Certificação final do ecossistema The Forge

**Revisão atual:** 2026-11-04  
**Programa:** `prompt_evo_mastering_melhorias.md`  
**Estado:** `CERTIFICATION_BLOCKED`

Este documento substitui a decisão histórica `CERTIFIED` baseada em nove
repositórios e em SHAs de outubro. A fonte atual de evidência é
[`audit/reports/prompt-evo-mastering-melhorias.md`](../../audit/reports/prompt-evo-mastering-melhorias.md),
com baseline reproduzível em `audit/baseline/`.

## Estado atual

- 14 checkouts foram incluídos no baseline atual.
- A matriz de instaladores tem 30 `PASS` e 10 `BLOCKED`: os bloqueios são os
  caminhos Linux Bash, indisponíveis neste host Windows.
- As correções de instalador, Platform Forge, Forge Portal e o wizard do Spark
  AWS foram implementadas e possuem testes locais/CI correspondentes.
- As ações de release PyPI/npm foram executadas com proteção contra overwrite;
  versões já publicadas foram recusadas como duplicadas.
- Linux/WSL, CUA visual, alguns hosts externos, deep scan e a execução completa
  do runner cross-forge ainda não possuem evidência atual suficiente.

## Regra de decisão

Nenhuma ausência de runtime, job em andamento, artefato histórico ou teste
ignorado é tratado como sucesso. A certificação só pode mudar para
`CONDITIONALLY_CERTIFIED` ou `CERTIFIED` depois de a matriz atual ser
regenerada, os bloqueios serem fechados ou aceitos formalmente pelo release
owner, e todos os artefatos apontarem para os SHAs atuais.

Os relatórios históricos de `docs/certification/cycle-10.1/` permanecem
consultáveis como proveniência, mas não são a decisão vigente.
