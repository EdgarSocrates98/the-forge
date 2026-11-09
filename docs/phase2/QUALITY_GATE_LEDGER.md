# Phase 2 — Quality Gate Ledger

Ledger de auditoria do `prompt_evo_obs_implement.md`. Os estados abaixo são
deliberadamente separados entre prova local, fixture e dependência externa.

| Gate | Commit(s) relevante(s) | Comando/prova reproduzível | Ambiente | Evidência observada | Limitação | Estado |
|---|---|---|---|---|---|---|
| G0 baseline/arquitetura | `21ef446` | `git show --stat`; leitura de `BASELINE.md`, `OWNERSHIP_MATRIX.md` | Windows local | ownership e contratos centralizados no The Forge | índices de código são best-effort | PASS |
| G1 correções P0/P1 | `d9d34ee`, `9cea23f`, `a561530`, `172f4ef` | suítes focadas de Platform/Azure/Product + gates AWS | Windows local | gateway, applicability, freshness, claims e ledger corrigidos | CI global dos especialistas não consolidado | PASS local |
| G2 contratos/schemas | `fad8122` e contratos Phase 2 | `uv run pytest -q tests/test_schemas.py tests/test_fuzz_contracts.py` | Windows local | schemas Obsidian v1 e envelopes versionados | compatibilidade externa não exercitada | PASS |
| G3 segurança/autorização | `2e38343`, `d9d34ee` | `uv run pytest -q -m "not benchmark" -rs` no Product Forge | Windows local | traversal, symlink/reparse, hardlink, classificação, raiz autorizada e redaction | multiusuário/OIDC real pendente | PASS local |
| G4 formatos | `172f4ef` | testes Obsidian + `forge_obsidian` wheel/sdist | Windows local | Markdown/frontmatter/wikilinks/embeds/Canvas/Bases validados | Canvas não é runtime completo; fórmulas não são avaliadas | PASS local |
| G5 sync | `172f4ef` | `uv run pytest -q tests/test_obsidian.py tests/test_api_surface_coverage.py` | Windows local | plan, baseline, conflito, atomic write, receipt, rollback, lock e recovery | faults reais de disco/permissão pendentes | PASS local |
| G6 adapters | `4e4661f`, `9cea23f`, `029b9aa`, `34486fa` | projeções focadas dos quatro especialistas | Windows local | AWS 11, Azure 4, Platform 9 e API 23 testes passando | sem cloud real | PASS fixture/local |
| G7 recuperação agêntica | `172f4ef` | testes de process-kill e fault injection de escrita | Windows local | recuperação estruturada e rollback verificáveis | ainda não substitui ensaio operacional real | PARTIAL |
| G8 E2E federado | `21ef446` | `uv run python scripts/phase2_federated_obsidian_e2e.py --repos-root E:\projetos\FORJAS` | Windows local | 4 notas round-tripped, contratos, Atlas/Lens/Bridge e conflito manual | fixture-only; não é cloud/vault de usuário | PASS fixture |
| G9 Portal/UX | `1e85c28` | suíte frontend, gate visual e API de investigação | Windows local | 603 testes, gate visual 8/8, axe/overflow/foco zero e handoff governado | materialização Obsidian requer sync revisado | PASS local |
| G10 instalação | `9587e13`, `d023e73` | `cli_install_matrix.py --check`; TTY/cancel smoke; `theforge install mcp-verify --json` | Windows + WSL2 | TTY 14/14, cancel 14/14, MCP 15 tools PASS, matriz Python 12/12 | OIDC/CI remoto pendentes | PASS local |
| G11 performance | `172f4ef` | benchmark observability `--sizes 100,1000,10000` | Windows local | scan/import/wikilinks/export/search/context/citations e ledger medidos | provider real NOT_RUN; tracemalloc não é RSS | PARTIAL |
| G12 release readiness | `21ef446` | `FINAL_ACCEPTANCE.md` + `REMAINING_RISKS.md` | Windows local + CI parcial | riscos e bloqueios externos explicitamente registrados | matriz global remota e operação real pendentes | BLOCKED externo |

## Regra de interpretação

`PASS local` não significa produção. `PASS fixture` prova o contrato e as
fronteiras com dados controlados. `PARTIAL` e `BLOCKED externo` permanecem
abertos até existir a evidência correspondente; nenhum desses estados é
convertido em sucesso por documentação.
