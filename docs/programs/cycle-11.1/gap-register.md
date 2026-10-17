# Cycle 11.1 — gap register

Estados: OPEN · IN_PROGRESS · FIXED_UNVERIFIED · VERIFIED · BLOCKED_EXTERNAL · NOT_APPLICABLE

| ID | Prioridade | Problema | Evidência | Correção | Teste | Estado |
|---|---|---|---|---|---|---|
| P0-001 | P0 | Publicação npm sem OIDC (job `if:false`, sem gates) | `publish-npm.yml` anterior | workflow validate→publish, environment `npm`, SHA-pin, provenance, smoke, `verify-version.mjs` | `tests/release-workflow.test.ts` (7 asserts) + gate real `version-exists` no 0.1.0 | FIXED_UNVERIFIED — publicação real depende de setup npm + environment (BLOCKED_EXTERNAL até o mantenedor) |
| P0-002 | P0 | `--plan` persistia cache TTL PyPI (mutação oculta) | snapshot sha256 divergia | `resolveRelease.ephemeral` — zero escrita em plan/check | `tests/plan-purity.test.ts` (install --plan, update --check, uninstall needsYes: hash idêntico) | VERIFIED |
| P0-003 | P0 | Transações/rollback/integridade de state | já coberto no Cycle 11 (hash verify, quarentena `.rejected`, writes atômicos, `.corrupt` backup, history/rollback) | sem nova mutação necessária nesta rodada | `tests/registry-*.test.ts` existentes (hash-mismatch, venv fail, corrupt state) | VERIFIED (escopo existente) |
| P1-001 | P1 | README priorizava clone; registry não era apresentado como recomendado | README anterior | npm install primeiro; seção PyPI marcada recomendada | revisão de docs | VERIFIED |
| P1-002 | P1 | `mcp --verify` era só `--version` — não provava protocolo | Cycle 11 gap register | `src/mcp/handshake.ts`: JSON-RPC initialize + tools/list, níveis, erros nomeados, sem tools/call | 4 testes com server fake real (ok/garbage/crash/badinit) | VERIFIED |
| P1-003 | P1 | Portal sem operações registry (plan→confirm→execute via CLI) | escopo prompt §8 | não implementado nesta rodada | — | OPEN — próxima rodada (portal ops + plan token) |
| P1-004 | P1 | Python floor vs CI matrix (platform/spark ≥3.10) | workflow por-repo | não auditado em profundidade | — | OPEN — spark-forge-aws CI main já está falhando (baseline) |
| P1-005 | P1 | Forge Lab interpreter/extras SKIPPED | escopo prompt §10 | não implementado | — | OPEN |
| P1-006 | P1 | Patches 0.x.1 e provenance PyPI por repo | escopo prompt §11 | não preparado (sem mudança distribuível nos repos ainda) | — | OPEN — depende de releases autorizados |
| P2-001 | P2 | Offline: deps transitivas sem pin de hash | gap Cycle 11 | não implementado | — | OPEN |
| P2-002 | P2 | Native installer fora da wheel (doctor-api) | gap Cycle 11 | documentado como skip honesto; decisão de produto (packaged CLI vs source-only) pendente | — | BLOCKED_EXTERNAL (decisão do mantenedor) |
| P2-003 | P2 | Hosts/skills/agents E2E em hosts reais | escopo prompt §14 | não executado — requer hosts reais | — | OPEN |
| P2-004 | P2 | Polish TUI/preflight/.env/erros/a11y/perf | escopo prompt §15 | parcial (bench já existe; erros nomeados cresceram) | — | OPEN |
| P2-005 | P2 | GitHub metadata/docs finais | escopo prompt §16 | doc de release criada | — | OPEN (restante: metadata dos repos) |

## Nota de honestidade

Este ciclo fechou os P0 tecnicamente executáveis localmente (publicação npm
pronta para aprovação, plan puro com prova por hash, protocolo MCP real) e
deixou P1/P2 restantes explicitamente OPEN — nenhum foi convertido em PASS
sem evidência.
