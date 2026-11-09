# Phase 2 — Quality Gate Ledger

Ledger de auditoria do `prompt_evo_obs_implement.md`. Os estados abaixo são
deliberadamente separados entre prova local, fixture e dependência externa.

| Gate | Commit(s) relevante(s) | Comando/prova reproduzível | Ambiente | Evidência observada | Limitação | Estado |
|---|---|---|---|---|---|---|
| G0 baseline/arquitetura | `21ef446` | `git show --stat`; leitura de `BASELINE.md`, `OWNERSHIP_MATRIX.md` | Windows local | ownership e contratos centralizados no The Forge | índices de código são best-effort | PASS |
| G1 correções P0/P1 | `d9d34ee`, `8e074a5`, `a561530`, `172f4ef`, `e669526`, `74bbbab`, `e68555f`, `6ca5ffd`, `5d96989` | suítes completas/focadas dos especialistas e Product + gates AWS + auditoria de Actions + CI manual The Forge/Agent Bridge | Windows local + GitHub Actions | gateway, applicability, freshness, claims, ledger, persistência atômica Windows, perfil S3 nomeado, pipeline standalone, classificação determinística de imports e stubs `jsonschema` corrigidos; 15 repositórios/50 workflows/335 Actions externas sem refs mutáveis; The Forge `42688316906` verde em Linux/Windows Python 3.11–3.14 e Agent Bridge `42687526019` verde | CI global das matrizes AWS/Azure/API/Platform não consolidado | PASS local + CI parcial |
| G2 contratos/schemas | `fad8122` e contratos Phase 2 | `uv run pytest -q tests/test_schemas.py tests/test_fuzz_contracts.py` | Windows local | schemas Obsidian v1 e envelopes versionados | compatibilidade externa não exercitada | PASS |
| G3 segurança/autorização | `2e38343`, `d9d34ee` | `uv run pytest -q -m "not benchmark" -rs` no Product Forge | Windows local | traversal, symlink/reparse, hardlink, classificação, raiz autorizada e redaction | multiusuário/OIDC real pendente | PASS local |
| G4 formatos | `172f4ef` | testes Obsidian + `forge_obsidian` wheel/sdist | Windows local | Markdown/frontmatter/wikilinks/embeds/Canvas/Bases validados | Canvas não é runtime completo; fórmulas não são avaliadas | PASS local |
| G5 sync | `e68555f` | Product Forge `uv run pytest -q` + Ruff + CI remoto `42686444553` | Windows local + GitHub Actions | 290 passed/1 skipped; plan, baseline, conflito, atomic write, receipt, rollback, lock e recovery; lint/testes remotos verdes | faults reais de disco/permissão pendentes | PASS local + CI |
| G6 adapters | `4e4661f`, `8e074a5`, `74bbbab`, `34486fa`, `e669526` | suítes completas dos quatro especialistas + E2E federado + smoke S3 real | Windows local + AWS us-east-1 temporário | AWS `15128 passed/14 skipped`, Azure `3190/9`, API `2028/4`, Platform terminou sem falhas; Code Atlas `1667/21`, Bridge `130`; projeções Obsidian e `collect parquet-footer` com 2 linhas/2 colunas; bucket e objeto removidos e verificados ausentes | Glue/EMR/Athena/CloudWatch e cenários de produção não exercitados; CI remoto dos branches não consolidado | PASS local + fixture + smoke cloud |
| G7 recuperação agêntica | `172f4ef` | testes de process-kill e fault injection de escrita | Windows local | recuperação estruturada e rollback verificáveis | ainda não substitui ensaio operacional real | PARTIAL |
| G8 E2E federado | `21ef446` | `uv run python scripts/phase2_federated_obsidian_e2e.py --repos-root E:\projetos\FORJAS` | Windows local | 4 notas round-tripped, contratos, Atlas/Lens/Bridge e conflito manual | fixture-only; não é cloud/vault de usuário | PASS fixture |
| G9 Portal/UX | `1e85c28`, `02c3501` | `npm test -- --no-watch --no-progress`; `npm run build`; `python -m pytest -q e2e/test_browser_homologation.py -k test_theforge_federated_flow` | Windows local | 57 arquivos/624 testes Angular, build de produção e browser E2E real `1 passed`; federação, Graph Studio, catálogos, recibo MCP e retorno ao grafo | materialização Obsidian requer sync revisado | PASS local |
| G10 instalação | `9587e13`, `d023e73`, `02c3501`, `6ca5ffd` | `cli_install_matrix.py --check`; TTY/cancel smoke; `theforge install mcp-verify --json`; teste de cleanup MCP; CI `42688316906` | Windows + WSL2 + GitHub Actions | TTY 14/14, cancel 14/14, MCP 15 tools PASS, matriz Python 12/12; `.cmd` não deixa stderr/filhos bloquearem a requisição; pacote The Forge Linux/Windows e testes Python 3.11–3.14 verdes remotamente | OIDC/CI global dos especialistas pendentes | PASS local + CI parcial |
| G11 performance | `172f4ef` | benchmark observability `--sizes 100,1000,10000` | Windows local | scan/import/wikilinks/export/search/context/citations e ledger medidos | provider real NOT_RUN; tracemalloc não é RSS | PARTIAL |
| G12 release readiness | `21ef446` | `FINAL_ACCEPTANCE.md` + `REMAINING_RISKS.md` | Windows local + CI parcial | riscos e bloqueios externos explicitamente registrados | matriz global remota e operação real pendentes | BLOCKED externo |

## Regra de interpretação

`PASS local` não significa produção. `PASS fixture` prova o contrato e as
fronteiras com dados controlados. `PARTIAL` e `BLOCKED externo` permanecem
abertos até existir a evidência correspondente; nenhum desses estados é
convertido em sucesso por documentação.
