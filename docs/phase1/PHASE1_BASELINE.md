# Forge Ecosystem — Phase 1 baseline

Baseline revalidado em **2026-11-08** no Windows 11, após a rodada de
interoperabilidade documental, paridade de instalação, homologação visual do
Portal e fechamento da matriz de CLIs. Os seis repositórios desta fase estão em
`main` após PR squash; artefatos locais não versionados foram preservados e não
são tratados como evidência de produto.

| Forge | `main` atual | versão | superfície principal / baseline executado |
|---|---|---|---|
| The Forge | `4d132ed` | 0.7.4 — control plane, contracts, registry, adapters | CI do PR #183 verde; matriz real de ajuda `1101/1101` comandos, 0 falhas |
| Code Atlas | `19e703a` | 1.1.1 — indexing, search, graph, context packs | suíte completa `1663 passed, 21 skipped` |
| Forge Lens | `86bd757` | 0.2.1 — traces, graph, evaluations | suíte completa verde, incluindo smoke de escala |
| Agent Bridge | `1c56054` | 0.2.1 — sessions, context authorization, events | suíte completa `128 passed`; Ruff verde |
| Product Forge | `79b3a50` | 0.2.2 — product knowledge, FTS, graph, portal adapter | suíte completa `225 passed, 1 skipped` |
| Forge Portal | `4f906af` | 1.1.1 — Angular UX, Portal API, E2E | build; CLI `3/3`; instalação `2/2`; browser `45 passed, 3 skipped`; axe e visual gate PASS |

Limitações observadas: Linux Bash não foi executado porque WSL não está
disponível. O Portal foi exercitado com adapter E2E degradado: endpoints
opcionais ausentes permanecem `UNAVAILABLE/UNVERIFIED`, sem dados fictícios; o
gate visual atual registrou 214 capturas, zero overflow horizontal e zero
violação axe séria/crítica. AWS live não foi afirmado sem credenciais; Azure
CLI também não está instalado. A prova Spark local é real, reproduzível e
explicitamente classificada por fidelidade.

O ecossistema também passou a ter uma matriz transversal de instalação em
14 projetos (`14/14`), smoke de versão/ajuda (`28/28`) e smoke em PTY Windows
(`14/14`). A matriz de ajuda profunda exercitou todos os comandos publicados
disponíveis nos inventários gerados (`1101/1101`, sem mutação).
