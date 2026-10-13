# Cycle 2 — relatório final (gate de fechamento)

Fechamento formal do Cycle 2 após o Cycle 2.1 (Closure & Proof, Waves A–I).
Documento de trabalho das waves: [cycle-2.1](cycle-2.1.md); relatório de
consolidação das Waves A–E do ciclo: [cycle-2](cycle-2.md).

- **Branch:** `feat/cycle2.1-cycle3` (11 commits sobre `main` `1eaa285`)
- **Head no fechamento:** `2ecba48` (+ commits de documentação deste relatório)
- **Sibling:** `api-forge` `feat/upstream-facts` `a9ae606` (intake `--upstream`,
  `apiforge/upstream-facts/v1`) — branch pushed; merge é ação humana. O gate
  remoto de providers rodou contra essa ref via input `api_forge_ref`.

## Gate estático

| Check | Resultado |
|---|---|
| `ruff check .` | All checks passed |
| `mypy` | Success: no issues found in 121 source files |
| Schema parity (`python -m theforge.contracts.schema schemas`) | 0 arquivos alterados |
| Agentic audit (`scripts/agentic/audit_assets.py`) | exit 0, nenhum achado de falha |
| Docs consistency (`tests/test_docs_consistency.py`) | 30 passed |

## Gate offline (Windows, Python 3.11)

| Suíte | Resultado |
|---|---|
| Offline completa (default) | **2920 passed, 5 skipped, 0 failed** em 11m43s |
| `-m slow` | 4 passed (wheel+sdist build, zero deps, fresh install) |
| `-m security` | 454 passed |
| Contract / integration / e2e | incluídos na suíte default, todos verdes |

Nota de harness: durante a Wave H, rodar duas sessões pytest com o mesmo
`--basetemp` colidiu e produziu falhas transitórias; re-rodadas isoladas
passaram. É limitação do harness de teste (basetemp é por invocação), não do
produto — registrada para não ser confundida com regressão.

## Gate de packaging

| Check | Resultado |
|---|---|
| `python -m build` | `theforge-0.1.0-py3-none-any.whl` + `theforge-0.1.0.tar.gz` |
| Dependências de runtime | 0 (`dependencies = []`; só extras `dev`) |
| Fresh install do wheel | gate `package` do CI verde em Ubuntu e Windows (run 37277636248) |
| Estado agentic/spec vazado | nenhum no wheel (98 entradas, só `src/theforge`); sdist exclui `.claude`/`.agents`/`.devin`/`.codex`/`.kiro`/`CLAUDE.md`/`AGENTS.md` |

## Gate de CI (remoto, branch `feat/cycle2.1-cycle3`)

| Workflow | Run | Resultado |
|---|---|---|
| `ci` (Ubuntu + Windows × py3.11–3.14 + package) | 37277636248 | ✅ success — 10/10 jobs (8 test + 2 package) |
| `compat` (macOS × py3.11/3.14) | 37262668962 | ✅ success (5m24s) — inclui o fix de flake de `git maintenance.lock` |
| `real-providers` (Ubuntu, Forges reais) | 37277639715 | ✅ success — 18 passed, com `api_forge_ref=feat/upstream-facts` |

## Gate de providers

| Prova | Resultado |
|---|---|
| Spark Forge real | ✅ local (`sparkforge` 0.5.0, Python 3.11.15) e remoto (run 37277639715) |
| API Forge real | ✅ local (`apiforge` 0.1.0, Python 3.12.13) e remoto |
| Cross-Forge real (Spark → API) | ✅ `test_proof_task_runs_across_the_real_spark_forge_and_api_forge`, local e remoto |
| Consumo semântico de handoff | ✅ live: 16 evidence derivadas `upstream:*` com `derived_from` → spark-forge/n1; A/B prova diferença observável; `handoff-provenance: passed` |

## Gate de integridade

Coberto pela suíte e pelos testes real-provider: replay determinístico (incl.
re-derivação de upstream facts a partir do handoff atual), explain com
`installation`, integridade de receipt, classificação física de artifacts
declarados (Wave D), drift de contexto, identidade do provider (manifest hash +
fingerprint) e provenance de handoff (check `handoff-provenance`).

## O que o Cycle 2.1 mudou (Waves A–I)

- **A:** reality check pós-merge documentado (PR #4 mergeado; relatório antigo desatualizado).
- **B:** `real-providers.yml` corrigido (adapters instalados no interpretador do core) e executado verde na branch; `compat.yml` rodado na main e na branch; flake de `git maintenance.lock` removido do harness.
- **C:** `RunStore.read_optional` recusa links (C1); invariante terminal — um recibo terminal por run (C2); `verification` registrada mesmo em erro interno pós-execute (C3).
- **D:** `declared_artifact_problem` classifica fisicamente divergências (missing/escape/não-regular/hash).
- **E:** explain de plano cobre `installation` (teste); drift live estendido ao cenário cross (lado Spark + ids do lado API).
- **F:** handoff semântico real — `api.analyze` consome upstream facts (`accepts_handoff`), evidence derivada com `derived_from` e epistemic preservado; replay re-deriva do handoff atual. Mudança coordenada no sibling `api-forge` (`a9ae606`).
- **G:** `theforge_apiforge.record_execute` — gravação de execute por máquina (workspace copiado sem links, argv via `invocation()`, `--handoff` para upstream, recusa de caminho de máquina, round-trip live→record→replay).
- **H:** todos os 16 follow-ups documentados classificados — 9 OBSOLETE (já corrigidos no merge B–E ou nas Waves C–E), 6 FIX NOW corrigidos (`#L2`, `and/or`, duplicate policy warning, poda de cache por digest, `hash_file` público, dedup de pipe helpers), 1 ACCEPTED LIMITATION (normcase macOS, com reason/impact/mitigation/trigger/target). Inclui o fix da fragilidade basetemp-git do golden de explain.
- **I:** este gate; `ci.yml` ganhou `workflow_dispatch`; `real-providers.yml` ganhou inputs `spark_forge_ref`/`api_forge_ref` (default `main`).

## Benchmarks (invariantes do ciclo, máquina de origem)

`context_1k_cold` 478→61 ms; `context_10k_cold` 3348→196 ms; 0 regressões em
11 budgets ([performance](../performance.md)). Latência real por provider em
produção: não medida (sem fonte — limitação documentada).

## Limitações intencionais remanescentes

As de `cycle-2.md` (isolamento de SO, routing por trust, filtros git globais,
custo do `import apiforge.cli`, verificação independente `not_performed` — C3
Wave G do próximo ciclo —, paridade semântica dos mirrors, budgets por máquina),
mais a ACCEPTED LIMITATION da Wave H (normcase macOS). Nenhuma bloqueia um gate;
todas têm razão, impacto, mitigação e gatilho registrados.

## Ação humana pendente (fora do escopo do gate)

Merge de `api-forge` `feat/upstream-facts` → depois disso `real-providers`
passa na main sem o input `api_forge_ref`. Abertura de PR das branches é
decisão do usuário (o workflow do api-forge impede que agentes abram PR lá).

## STATUS

Cycle 2: **CLOSED** — gates estático, offline, packaging, CI (Ubuntu, Windows,
macOS), providers reais e integridade verdes; a única pendência é externa ao
ciclo (merge do sibling) e está registrada como ação humana.
