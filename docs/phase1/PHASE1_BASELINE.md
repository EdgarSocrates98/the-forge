# Forge Ecosystem — Phase 1 baseline

Baseline revalidado em 2026-11-06/07 no Windows 11, antes da fatia de
interoperabilidade documental. Os seis repositórios foram integrados em `main`
por PR squash e os artefatos locais não versionados foram preservados.

| Forge | `main` integrado | superfície principal | baseline executado |
|---|---|---|---|
| The Forge | `d76781d` | control plane, contracts, registry, adapters | gates 11/11 + suíte completa verde |
| Code Atlas | `b0e19dd` | indexing, search, graph, context packs | suíte completa `1658 passed, 21 skipped` |
| Forge Lens | `416a8cb` | traces, graph, evaluations | suíte completa `1658 passed, 21 skipped` |
| Agent Bridge | `c4cd23f` | sessions, context authorization, events | `115 passed` |
| Product Forge | `d1e99db` | product knowledge, FTS, graph, portal adapter | `177 passed, 1 skipped` |
| Forge Portal | `ba8dfd3` | Angular UX, Portal API, E2E | build + `583 passed`; browser `35 passed, 1 skipped`; axe sem violações |

Limitações observadas: o teste AWS completo segue em execução longa; Linux Bash
não foi executado porque WSL não está disponível; execução Spark live não foi
afirmada sem conta/role/região/workspace autorizados.
