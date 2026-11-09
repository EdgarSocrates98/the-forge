# Phase 2 — Execution Report

Data: 2026-11-09. Este relatório centraliza a execução do programa de integração
Obsidian/Cycle 2.0–2.6. Evidência local usa fixtures e não autoriza inferência
de execução em cloud ou em vault de usuário.

| Gate | Estado | Evidência principal | Limitação |
|---|---|---|---|
| G0 baseline/arquitetura | PASS | `BASELINE.md`, `OWNERSHIP_MATRIX.md` | índices de código são best-effort |
| G1 correções P0/P1 | PASS | commits por Forge registrados no baseline; Product regression local 82,62%; The Forge CI `42564466899` e release-gates `42564466922` verdes | branches sem workflow publicado e demais branches especialistas ainda não têm um único run global consolidado |
| G2 contratos/schemas | PASS | `tests/test_schemas.py` — 22 passed; schemas Obsidian v1 | compatibilidade externa não foi exercitada |
| G3 segurança/autorização | PASS local | traversal, symlink/reparse, hardlink, classificação, raiz autorizada e prompt-safety | permissão real e vault multiusuário não executados |
| G4 formatos | PASS local | Markdown, frontmatter, links, embeds, Canvas/Bases estruturais | não é parser completo do aplicativo Obsidian |
| G5 integridade de sync | PASS local | Product Forge — 276 passed, 1 skipped; `forge_obsidian` distribuível sem dependência do runtime Product Forge; wheel/sdist `forge-obsidian` construídos pelo fluxo wheel-from-sdist; plan/baseline/conflict/atomic/rollback/skip/lock, índice seguro de paths e importação governada de investigação; fault injection explícito para disk full e permission denied | publicação remota/pin pelos adapters e falhas reais de filesystem ainda não executados |
| G6 adapters | PASS fixture | AWS, Azure, API e Platform no runner federado | sem cloud real |
| G7 recuperação agêntica | PARTIAL | processo encerrado durante temporário e recuperação subsequente verificados; falhas disk full/permission denied estruturadas e testadas por fault injection | falhas reais de filesystem pendentes |
| G8 E2E federado | PASS fixture | `FEDERATED_E2E_EVIDENCE.md`; 4 notas, round-trip, Atlas, Lens, Bridge e conflito manual | não é homologação cloud/vault de usuário; runner de fixtures é separado do endpoint de investigação |
| G9 Portal/UX | PASS local | 603 testes frontend; Nova investigação com evidências, plano assinado, execução federada, recibo e handoff explícito para índice Product Forge; conhecimento com conexão, descoberta body-free de paths, preview, import/export, conflitos, histórico e deep link Obsidian; gate visual 8/8, axe/overflow/foco = 0; pacote instalado fora do checkout com CLI/TUI/status/start estático e HTTP 200 | gravação no Obsidian continua sendo sync revisado e explícito; produção/OIDC pendentes |
| G10 instalação/distribuição | PASS local | matriz Python 12/12 wheel→venv→CLI passou no Windows e Linux WSL2; matriz limpa do wheel The Forge project/workspace/user passou com apply/uninstall; Product Forge wheel/venv/Portal fake passou; `forge-cli` e Portal Node build/pack passaram; matriz TTY/TUI 14/14 e cancelamento 14/14 verdes; MCP handshake real The Forge PASS com 15 tools e exit code 0; Product Forge publica 17 tools, incluindo índice Obsidian read-only | OIDC e matriz remota global ainda pendentes |
| G11 performance/regressão | PASS local | benchmark 100/1.000/10.000 e suíte Product Forge | métricas de memória/reindexação ainda não são baseline completo |
| G12 release readiness | BLOCKED | The Forge e Product Forge têm CI remoto verde; base funcional integrada | aceite global ainda depende da matriz instalada de todas as Forjas e dos riscos operacionais descritos em `REMAINING_RISKS.md` |

## Comandos de referência

```powershell
cd E:\projetos\FORJAS\product-forge
uv run pytest -q -rs
# 268 passed, 1 skipped (installed-system lane opt-in)

cd E:\projetos\FORJAS\the-forge
uv run python scripts/phase2_federated_obsidian_e2e.py --repos-root E:\projetos\FORJAS
# fixture_only=true, notes_roundtripped=4, manual_conflict_detected=true
```

O teste ignorado na suíte padrão não foi contado como aprovado; a mesma lane de
composição instalada foi executada separadamente com
`PRODUCT_FORGE_SYSTEM_HARNESS=1` e passou no Windows (`1 passed`).
