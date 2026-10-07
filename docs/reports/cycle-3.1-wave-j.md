# Cycle 3.1 — Wave J: delta handoff, economia de contexto e terminologia

Escopo: Phases 49 (delta handoff), 50 (context economy), 51 (benchmark
direct vs mesh) e 52 (terminologia protocol-real / specialist-real).

## J.1 — `delta/v1`: handoff incremental (Phase 49)

O `ExecuteRequest` ganhou o campo aditivo `delta: DeltaRequest | None`
(`baseline_ref` opaco + `changed_files` de paths POSIX relativos, ≤256
entradas, sem absolutos/`..`/`\` — validado em `__post_init__`). Contrato em
`src/theforge/contracts/envelope.py`; schema regenerado.

**Quando sai.** `Forger._delta_request` (orchestrator.py) emite a dica somente
quando as duas condições são verdadeiras:

1. o manifest do provider declara `delta/v1` (via `manifest.features`);
2. o `FingerprintStore` tem estado anterior do workspace — capturado no `load`
   (`_prior`), comparado por `changed_surface(current, present)`:
   adicionados/modificados (re-hashados neste run) + removidos (sumiram do
   scan). Primeiro run, cache desligado ou descartado → `delta` ausente.

`baseline_ref=""` pede ao especialista seu baseline mais recente; o core não
interpreta refs nem guarda estado do especialista. A dica atravessa o mesmo
caminho para nós de plano (plan_executor → `forger.ask`).

**Regra de honestidade.** Baseline não resolvido nunca fabrica um delta nem
disfarça um full scan: o documento nativo carrega `delta.unresolved`
explícito e a tradução vira evidência, não silêncio.

## J.2 — Adapters dos Doctors

**Doctor Data** (`data.scan`): o bridge aceita `--delta-baseline` /
`--delta-changed-files`. Com a dica presente ele grava um snapshot do
relatório atual **dentro do stage** (a store real do workspace fica intacta)
e difere contra o baseline de `.forge-doctor-data/history` via
`diff_snapshots`: `older/newer`, `new_findings`, `resolved_findings`,
`entities_added/removed`, `capability_transitions`, `drift_added/resolved`.
Sem baseline: `unresolved` explica por quê.

**Doctor API** (`api.diagnose`): o bridge resolve `baseline_ref` na store
`.forge-doctor/snapshots` do workspace staged (`""`/`latest` → snapshot mais
novo) e passa o `DoctorReport` ao `DoctorBoundary.handle(request,
baseline=...)`, que emite o `DeltaContext` determinístico upstream
(findings/ops/entidades/domains/capabilities ±, `changed_files`,
`protocol_diff`).

Ambos declaram `features: ["delta/v1"]` no manifest e traduzem a seção
`delta` para evidência `id="delta"` com contagens por tipo (`+N findings`,
`~N ops`, …) e `baseline_ref` — deltas, não só "delta present". Hints
malformados viram limitação no draft, nunca recusa nem mentira.

`tests/test_delta_handoff.py` cobre o lado do core (9 testes: primeiro run
sem delta, segundo run com superfície mudada, provider sem a feature,
cache desligado, caps de contrato); `tests/test_adapter_{doctordata,
doctorapi}.py` cobrem argv-building, hints malformados e a evidência de delta
nos cenários de replay `scenarios/delta/` (gravados com as stores de histórico
povoadas).

## J.3 — Benchmark de economia (Phases 50–51)

`scripts/bench/run_context_economy.py` — stdlib, isolado (tmpdir +
`THEFORGE_CONFIG_DIR`/`THEFORGE_CACHE_DIR` próprios), fora da suíte offline.
Dois braços sobre o mesmo workspace determinístico (404 arquivos):

- **direct**: Spark Forge e API Forge, cada um com `targets: ["."]`.
- **mesh**: `forge-doctor-data` sobre `["."]`, depois Spark (`jobs`,
  `requirements.txt`) e API (`api`, `src`) delimitados, com `inputs` no
  doctor — observe → bounded-handoff → engineer.

Medido dos artifacts do run store (só o observável): `provider_calls`,
`files_scanned`, `context_files`, `context_bytes`, `handoff_bytes`,
`evidence_bytes`, `wall_ms` + breakdown por nó; `model_calls` e
`provider_tokens` saem `null` — desconhecido não é zero. Saída
`theforge-economy-bench/v1` com `provider_mode`, `arms`, `comparison`
(`mesh_minus_direct` por métrica) e `unmeasurable`.

Resultado medido nesta máquina (1 repetição, replay): `files_scanned`
808 → 408 (−400: a varredura inteira acontece uma vez, não por especialista);
contexto por engenheiro 165 KB → ~100 B; `context_bytes` total **sobe**
(330 KB → 397 KB) porque a superfície de globs do doctor é mais larga que a
soma dos dois especialistas — o ganho é uma varredura ampla única em vez de
N, e o handoff (138 KB) substitui re-leitura. Documentado em
`docs/performance.md`.

## J.4 — Terminologia (Phase 52)

`docs/real-providers.md` ganhou a tabela "Níveis de real":

| Nível | O que executa |
|---|---|
| `protocol-real` | fixture provider, subprocesso real, Forge Protocol real |
| `specialist-replay` | adapter real + protocolo real + saída nativa gravada |
| `specialist-real` | pacote do especialista vivo, no venv dele |

Regra registrada: `specialist-replay` nunca é apresentado como
`specialist-real`; o bench declara `provider_mode` no relatório.

## Prova

- `test_delta_handoff.py` 9/9; adapters doctor (replay + delta) 100% verdes;
  `test_economy_bench.py` 6/6 (incl. e2e dos dois braços em replay).
- `ruff check .` limpo; `mypy src` e `mypy adapters/*/src` limpos.
- `run_context_economy.py --runs 1` produziu o relatório acima, com
  `provider_mode: specialist-replay` e nulls honestos.

## Arquivos

- Core: `src/theforge/contracts/envelope.py` (`DeltaRequest`),
  `contracts/__init__.py`, `forger/orchestrator.py` (`_delta_request`),
  `context/fingerprints.py` (`_prior` + `changed_surface`),
  `schemas/ExecuteRequest.schema.json` regenerado.
- Adapters: `theforge_doctordata/{bridge,execute,translate,catalog}.py`,
  `theforge_doctorapi/{bridge,execute,translate,catalog}.py`.
- Bench: `scripts/bench/run_context_economy.py` (novo).
- Testes: `tests/test_delta_handoff.py`, `tests/test_economy_bench.py`
  (novos), `tests/test_adapter_{doctordata,doctorapi}.py`,
  `tests/conftest.py` (markers), `tests/fixtures/providers/fixture-delta.json`,
  `tests/fixtures/providers/fixture_forge.py` (eco `delta`),
  `tests/fixtures/native/{doctordata,doctorapi}/scenarios/delta/` (novos).
- Docs: `protocol.md` (campo `delta` + seção Delta), `real-providers.md`
  (níveis de real + bullet delta), `performance.md` (bench de economia).
