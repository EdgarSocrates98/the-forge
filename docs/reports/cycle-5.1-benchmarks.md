# Cycle 5.1 — Benchmark report (§37-40, §64-66)

Três camadas, todas reproduzíveis, offline, stdlib-only:

| Camada | Script | Artefato |
|---|---|---|
| Hot paths (latência) | `scripts/bench/run_bench.py` | `docs/reports/cycle-5.1-hotpaths.json` |
| Cenários oficiais B01–B15 | `scripts/bench/run_scenarios.py` | `docs/reports/cycle-5.1-scenarios.json` |
| Memory ROI | `scripts/bench/run_memory_roi.py` | `docs/reports/cycle-5.1-memory-roi.{json,md}` |

## Hot paths — baseline medido (máquina de origem, `--quick`, 3 reps)

21 medições, **0 regressões** contra `scripts/bench/budgets.json` (baselines
Cycle-3 preservados; budgets novos só para as medições novas, fator 1,5).

| Medição | Mediana (ms) | O que mede |
|---|---:|---|
| `cli_startup` | 462 | `--help` em subprocesso |
| `registry_cold` / `registry_warm` | 421 / 6 | discovery de providers |
| `scan_1k` / `scan_10k` | 444 / 4 363 | varredura de workspace |
| `routing_10k` | 291 | routing determinístico |
| `context_*_{cold,warm}` | 51–187 | montagem de contexto |
| `persist_run` | 13 | gravação de artifacts do run |
| `graph_build` | 0,10 | capability graph federado |
| `graph_refresh_warm` | 37 | refresh incremental de intel |
| `plan_validate` | 0,12 | `check_plan` de 32 nós |
| `replay_verify` | 7,4 | verificação de hashes do run |
| `explain_build` | 19 | explainability report |
| `memory_pack` | 54,7 | retrieval escopado (240 entries) |
| `plan_simulate` | 1,8 | simulação pré-execução |
| `target_negotiate` | 0,03 | negociação provider×target |
| `receipt_validate` | 0,05 | binding de receipt remoto |
| `observation_write` | 6,3 | append de observação |

### Leitura honesta

- `memory_pack` (~55 ms) é o hot path mais caro das camadas Cycle 5: o bound
  de bytes exige serializar o que casa. Sem índice semântico (§18) isso é ≈
  scan; o ganho de memória está em **bytes entregues**, medido no ROI.
- `plan_simulate`/`target_negotiate`/`receipt_validate` são sub-2 ms —
  custo desprezível nas decisões do planner.
- `observation_write` (6,3 ms) é append+bound; não há N log-synchronous writes.

## Cenários B01–B15 — 15/15 pass

Cada cenário exercita uma superfície do Cycle 5 pela API real e falha se o
comportamento divergir (não é só timing). Resultados e evidências por cenário
em `docs/reports/cycle-5.1-scenarios.json`. Destaques medidos:

- **B02**: cadeia real `data.scan → data.diagnostic-evidence →
  pyspark.static-analysis/api.analyze` validada pelo `check_plan`.
- **B08**: federação declara `can_verify` (anúncio) mas **nenhum**
  `verified_by` (binding do paciente) — um nó `verification_required` degrada
  para `forge` com limitação nomeada. Não é bug: a direção da declaração é o
  contrato correto (o paciente declara quem o verifica). Fica registrado como
  limitação de superfície: a federação atual não tem independent verification
  *endereçável* sem manifests declararem `verified_by`.
- **B09**: autoridade global (policy/budget/user) domina qualquer sinal —
  `verification_required` pendente bloqueia stop por evidência, nunca reabre
  após stop de autoridade; o campo fica registrado na decisão.

## Determinismo e estabilidade de IDs

- B01 prova `check_plan` idêntico e `sha256(plan)` estável entre repetições.
- B05 + suite `test_memory_roi.py`: `pack_stats` determinístico, ids de memória
  content-derived (`sha256(kind|scope|subject|claim)`) — re-registro é
  reaffirmação, não duplicata.
- `test_federation_conformance.py`: build do grafo federado idêntico entre
  invocações.

## Reproducibilidade (§66)

Todos os artefatos carregam `environment` (OS, Python, máquina), `commit_sha`,
`specialist_shas` e `surface_hashes` lidos de
`docs/reality/specialist-reality.json`. Sem isso os números decaem rápido.
