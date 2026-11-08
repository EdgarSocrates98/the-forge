# Forge Ecosystem — Phase 1 baseline

Baseline revalidado em **2026-11-08** no Windows 11, após a primeira rodada de
interoperabilidade documental, paridade de instalação e correções de gates.
Os seis repositórios desta fase estão em `main` após PR squash; artefatos locais
não versionados foram preservados e não são tratados como evidência de produto.

| Forge | `main` atual | versão | superfície principal / baseline executado |
|---|---|---|---|
| The Forge | `b4b3e75` | 0.7.4 — control plane, contracts, registry, adapters | CI remoto **10/10 jobs PASS**; package/wheel e suíte offline Linux/Windows Python 3.11–3.14 |
| Code Atlas | `dda7c92` | indexing, search, graph, context packs | suíte completa `1661 passed, 21 skipped` |
| Forge Lens | `a5bba59` | traces, graph, evaluations | suíte completa verde, incluindo smoke de escala |
| Agent Bridge | `83169b3` | 0.2.1 — sessions, context authorization, events | `123 passed`; Ruff e smoke federado PASS |
| Product Forge | `fad0678` | 0.2.2 — product knowledge, FTS, graph, portal adapter | `219 passed, 1 skipped`; Ruff PASS; wheel contém assets Angular |
| Forge Portal | `0cd1bad` | 1.1.1 — Angular UX, Portal API, E2E | build; Angular `589 passed`; Python `199 passed, 15 skipped`; browser `45 passed, 3 skipped`; visual/reflow/axe PASS |

Limitações observadas: Linux Bash não foi executado porque WSL não está
disponível. O Portal foi exercitado com adapter E2E degradado: endpoints
opcionais ausentes permanecem `UNAVAILABLE/UNVERIFIED`, sem dados fictícios; o
gate visual encontrou zero overflow de página, zero clip ruim e zero violação
axe séria/crítica. AWS live não foi afirmado sem credenciais/boto3 resolvidos;
Azure CLI também não está instalado. A prova Spark é local, replay/independente
e explicitamente classificada por fidelidade.
