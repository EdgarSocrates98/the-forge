# Forge Ecosystem — Phase 1 baseline

Baseline revalidado em 2026-11-07 no Windows 11, após a primeira rodada de
interoperabilidade documental, paridade de instalação e correções de gates.
Os seis repositórios desta fase estão em `main` após PR squash; artefatos locais
não versionados foram preservados e não são tratados como evidência de produto.

| Forge | `main` integrado | superfície principal | baseline executado |
|---|---|---|---|
| The Forge | `a6a13f4` | control plane, contracts, registry, adapters | CI remoto verde; smoke de conhecimento PASS; teste canônico isolado `6 passed` |
| Code Atlas | `dda7c92` | indexing, search, graph, context packs | suíte completa `1661 passed, 21 skipped` |
| Forge Lens | `a5bba59` | traces, graph, evaluations | suíte completa verde, incluindo smoke de escala |
| Agent Bridge | `963e09b` | sessions, context authorization, events | `117 passed` |
| Product Forge | `f9567a1` | product knowledge, FTS, graph, portal adapter | `218 passed, 1 skipped`; coverage gate `80.29%` |
| Forge Portal | `0cd1bad` | Angular UX, Portal API, E2E | build + `589 passed`; browser `45 passed, 3 skipped`; axe sem violações |

Limitações observadas: Linux Bash não foi executado porque WSL não está
disponível; execução Spark live não foi afirmada sem conta/role/região/workspace
autorizados. O resultado local do The Forge sob carga concorrente teve uma
checagem Hypothesis de lentidão; o caso foi reproduzido isoladamente com `6
passed` e o CI remoto da branch integrada está verde.
