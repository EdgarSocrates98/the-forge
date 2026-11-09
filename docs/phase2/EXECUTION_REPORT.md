# Phase 2 — Execution Report

Data: 2026-11-09. Este relatório centraliza a execução do programa de integração
Obsidian/Cycle 2.0–2.6. Evidência local usa fixtures e não autoriza inferência
de execução em cloud ou em vault de usuário.

| Gate | Estado | Evidência principal | Limitação |
|---|---|---|---|
| G0 baseline/arquitetura | PASS | `BASELINE.md`, `OWNERSHIP_MATRIX.md` | índices de código são best-effort |
| G1 correções P0/P1 | PASS local | commits por Forge registrados no baseline | CI remoto dos branches ainda pendente |
| G2 contratos/schemas | PASS | `tests/test_schemas.py` — 22 passed; schemas Obsidian v1 | compatibilidade externa não foi exercitada |
| G3 segurança/autorização | PASS local | traversal, symlink/reparse, hardlink, classificação, raiz autorizada e prompt-safety | permissão real e vault multiusuário não executados |
| G4 formatos | PASS local | Markdown, frontmatter, links, embeds, Canvas/Bases estruturais | não é parser completo do aplicativo Obsidian |
| G5 integridade de sync | PASS local | Product Forge — 256 passed; plan/baseline/conflict/atomic/rollback/skip/lock | processo morto/disco cheio real não executados |
| G6 adapters | PASS fixture | AWS, Azure, API e Platform no runner federado | sem cloud real |
| G7 recuperação agêntica | NOT_RUN | falhas determinísticas cobertas parcialmente | process kill, disk full e permission denied reais pendentes |
| G8 E2E federado | PASS fixture | `FEDERATED_E2E_EVIDENCE.md` | Portal não dispara o runner em runtime |
| G9 Portal/UX | PASS local | 597 testes frontend; gate visual 8/8, axe/overflow/foco = 0 | homologação instalável pendente |
| G10 instalação/distribuição | NOT_RUN completo | MCP The Forge e installers existentes foram preservados | matriz wheel Windows/Linux e Portal instalável pendente |
| G11 performance/regressão | PASS local | benchmark 100/1.000/10.000 e suíte Product Forge | métricas de memória/reindexação ainda não são baseline completo |
| G12 release readiness | BLOCKED | base funcional integrada | CI remoto e gates NOT_RUN impedem aceite final |

## Comandos de referência

```powershell
cd E:\projetos\FORJAS\product-forge
uv run pytest -q -rs
# 256 passed, 1 skipped (installed-system lane opt-in)

cd E:\projetos\FORJAS\the-forge
uv run python scripts/phase2_federated_obsidian_e2e.py --repos-root E:\projetos\FORJAS
# fixture_only=true, notes_roundtripped=4, manual_conflict_detected=true
```

O teste ignorado não foi contado como aprovado: ele é a lane de composição
instalada e requer `PRODUCT_FORGE_SYSTEM_HARNESS=1`.
