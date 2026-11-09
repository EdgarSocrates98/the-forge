# Phase 2 — Quality Gate Ledger

Ledger de auditoria do `prompt_evo_obs_implement.md`. Os estados abaixo são
deliberadamente separados entre prova local, fixture e dependência externa.

| Gate | Commit(s) relevante(s) | Comando/prova reproduzível | Ambiente | Evidência observada | Limitação | Estado |
|---|---|---|---|---|---|---|
| G0 baseline/arquitetura | `21ef446` | `git show --stat`; leitura de `BASELINE.md`, `OWNERSHIP_MATRIX.md` | Windows local | ownership e contratos centralizados no The Forge | índices de código são best-effort | PASS |
| G1 correções P0/P1 | `d9d34ee`, `8e074a5`, `a561530`, `172f4ef`, `e669526`, `1490ff3` | suítes focadas de Platform/Azure/Product + gates AWS | Windows local | gateway, applicability, freshness, claims, ledger, perfil S3 nomeado e pipeline standalone protegida por teste estrutural corrigidos | CI global dos especialistas não consolidado | PASS local |
| G2 contratos/schemas | `fad8122` e contratos Phase 2 | `uv run pytest -q tests/test_schemas.py tests/test_fuzz_contracts.py` | Windows local | schemas Obsidian v1 e envelopes versionados | compatibilidade externa não exercitada | PASS |
| G3 segurança/autorização | `2e38343`, `d9d34ee` | `uv run pytest -q -m "not benchmark" -rs` no Product Forge | Windows local | traversal, symlink/reparse, hardlink, classificação, raiz autorizada e redaction | multiusuário/OIDC real pendente | PASS local |
| G4 formatos | `172f4ef` | testes Obsidian + `forge_obsidian` wheel/sdist | Windows local | Markdown/frontmatter/wikilinks/embeds/Canvas/Bases validados | Canvas não é runtime completo; fórmulas não são avaliadas | PASS local |
| G5 sync | `172f4ef` | `uv run pytest -q tests/test_obsidian.py tests/test_api_surface_coverage.py` | Windows local | plan, baseline, conflito, atomic write, receipt, rollback, lock e recovery | faults reais de disco/permissão pendentes | PASS local |
| G6 adapters | `4e4661f`, `8e074a5`, `029b9aa`, `34486fa`, `e669526` | projeções focadas dos quatro especialistas + smoke S3 real | Windows local + AWS us-east-1 temporário | AWS 11, Azure 4, Platform 9 e API 23 projeções; `collect parquet-footer` leu 1 Parquet de 749 bytes com `--profile/--region`, `status=ok`, 2 linhas/2 colunas; bucket e objeto removidos e verificados ausentes | Glue/EMR/Athena/CloudWatch e cenários de produção não exercitados; full suite AWS teve 6 gates derivados regenerados e a bateria direcionada terminou verde | PASS fixture + smoke cloud |
| G7 recuperação agêntica | `172f4ef` | testes de process-kill e fault injection de escrita | Windows local | recuperação estruturada e rollback verificáveis | ainda não substitui ensaio operacional real | PARTIAL |
| G8 E2E federado | `21ef446` | `uv run python scripts/phase2_federated_obsidian_e2e.py --repos-root E:\projetos\FORJAS` | Windows local | 4 notas round-tripped, contratos, Atlas/Lens/Bridge e conflito manual | fixture-only; não é cloud/vault de usuário | PASS fixture |
| G9 Portal/UX | `1e85c28`, `02c3501` | `npm test -- --no-watch --no-progress`; `npm run build`; `python -m pytest -q e2e/test_browser_homologation.py -k test_theforge_federated_flow` | Windows local | 57 arquivos/624 testes Angular, build de produção e browser E2E real `1 passed`; federação, Graph Studio, catálogos, recibo MCP e retorno ao grafo | materialização Obsidian requer sync revisado | PASS local |
| G10 instalação | `9587e13`, `d023e73`, `02c3501` | `cli_install_matrix.py --check`; TTY/cancel smoke; `theforge install mcp-verify --json`; teste de cleanup MCP | Windows + WSL2 | TTY 14/14, cancel 14/14, MCP 15 tools PASS, matriz Python 12/12; `.cmd` não deixa stderr/filhos bloquearem a requisição | OIDC/CI remoto pendentes | PASS local |
| G11 performance | `172f4ef` | benchmark observability `--sizes 100,1000,10000` | Windows local | scan/import/wikilinks/export/search/context/citations e ledger medidos | provider real NOT_RUN; tracemalloc não é RSS | PARTIAL |
| G12 release readiness | `21ef446` | `FINAL_ACCEPTANCE.md` + `REMAINING_RISKS.md` | Windows local + CI parcial | riscos e bloqueios externos explicitamente registrados | matriz global remota e operação real pendentes | BLOCKED externo |

## Regra de interpretação

`PASS local` não significa produção. `PASS fixture` prova o contrato e as
fronteiras com dados controlados. `PARTIAL` e `BLOCKED externo` permanecem
abertos até existir a evidência correspondente; nenhum desses estados é
convertido em sucesso por documentação.
