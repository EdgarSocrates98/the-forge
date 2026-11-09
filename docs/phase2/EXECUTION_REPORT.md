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
| G5 integridade de sync | PASS local | Product Forge — 259 passed, 1 skipped; plan/baseline/conflict/atomic/rollback/skip/lock | disk full/permission denied reais não executados |
| G6 adapters | PASS fixture | AWS, Azure, API e Platform no runner federado | sem cloud real |
| G7 recuperação agêntica | PARTIAL | processo encerrado durante temporário e recuperação subsequente verificados | disk full e permission denied reais pendentes |
| G8 E2E federado | PASS fixture | `FEDERATED_E2E_EVIDENCE.md` | Portal não dispara o runner em runtime |
| G9 Portal/UX | PASS local | 600 testes frontend; Nova investigação com evidências, plano assinado, execução federada e recibo; gate visual 8/8, axe/overflow/foco = 0; pacote instalado fora do checkout com CLI/TUI/status/start estático e HTTP 200 | Portal ainda não dispara a cadeia Portal → Product Forge/Obsidian em runtime |
| G10 instalação/distribuição | PASS local | matriz Python 12/12 wheel→venv→CLI passou no Windows e Linux WSL2; matriz limpa do wheel The Forge project/workspace/user passou com apply/uninstall; Product Forge wheel/venv/Portal fake passou; `forge-cli` e Portal Node build/pack passaram; matriz TTY/TUI 14/14 e cancelamento 14/14 verdes; MCP handshake real PASS com 15 tools e exit code 0 | OIDC e matriz remota global ainda pendentes |
| G11 performance/regressão | PASS local | benchmark 100/1.000/10.000 e suíte Product Forge | métricas de memória/reindexação ainda não são baseline completo |
| G12 release readiness | BLOCKED | The Forge e Product Forge têm CI remoto verde; base funcional integrada | aceite global ainda depende da matriz instalada de todas as Forjas e dos riscos operacionais descritos em `REMAINING_RISKS.md` |

## Comandos de referência

```powershell
cd E:\projetos\FORJAS\product-forge
uv run pytest -q -rs
# 259 passed, 1 skipped (installed-system lane opt-in)

cd E:\projetos\FORJAS\the-forge
uv run python scripts/phase2_federated_obsidian_e2e.py --repos-root E:\projetos\FORJAS
# fixture_only=true, notes_roundtripped=4, manual_conflict_detected=true
```

O teste ignorado na suíte padrão não foi contado como aprovado; a mesma lane de
composição instalada foi executada separadamente com
`PRODUCT_FORGE_SYSTEM_HARNESS=1` e passou no Windows (`1 passed`).
