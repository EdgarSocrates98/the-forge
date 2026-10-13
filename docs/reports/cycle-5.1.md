# Cycle 5.1 — Reality Synchronization, Benchmarking & Feature Freeze

**Status:** IMPLEMENTATION COMPLETE / LOCAL_GATES_GREEN /
REMOTE_VALIDATION_BLOCKED (GitHub Actions quota — owner decision; not a code
failure). Fechamento formal aguarda CI remota em `main`.

Data do fechamento local: 2026-10-08 · branch `devin/cycle5-final` · merge em
`main` via PR.

## 1. Executive Summary

O Cycle 5.1 não adicionou features — **provou o que o Cycle 5 entregou** e
formalizou o Feature Freeze. Três achados reais de drift foram detectados,
classificados e um corrigido (schema upstream-facts do adapter Spark); quatro
especialistas foram re-sincronizados com manifest machine-readable; o ROI de
memória foi medido (87.6% de bytes de contexto economizados); a suite oficial
B01–B15 passa 15/15; a regressão adversarial cobre os 18 vetores do §50; e o
release 1.0 foi explicitamente adiado até evidência de dogfooding.

## 2. Repository State

```text
The Forge SHA:   (HEAD da branch no momento do relatório — ver evidence manifest)
package:         0.4.0
Python:          >= 3.11 (medido: 3.11.15 win32)
tests:           4328 coletados offline (39 desselecionados: slow/real_provider)
contracts:       67 exportados (39 closed/core-only)
schemas:         67 — paridade 1:1, regen determinística limpa
docs raiz:       33 (+ feature-freeze.md, dogfooding.md)
ADRs:            51
runtime deps:    0 (stdlib-only — preservado)
```

## 3. Specialist Reality

Manifest: [`cycle-5.1-reality.json`](cycle-5.1-reality.json) (gerado por
`scripts/reality/collect.py`).

| Specialist | SHA instalado | Versão | Surface hash | Relação c/ origin/main | Drift snapshot | Status |
|---|---|---|---|---|---|---|
| Spark Forge AWS | `828827d7` (`feat/upstream-facts-v1`) | 0.5.0 | `49f6db89cea5` | diverged (feature branch; upstream-facts já na main publicada) | none | snapshot_fresh_install_diverged |
| API Forge | `1745f872` (detached, pré-squash) | 0.1.0 | `b2be601baaab` | diverged (conteúdo = squash `07459a2` na main) | none | snapshot_fresh_install_diverged |
| Doctor Data | `3a8d7a56` (`main`) | 1.0.0rc1 | `1e2b1f4293da` | same | none | **fresh** |
| Doctor API | `035b635` (`main` local) | 0.2.0 | `ad03aa4f33d7` | diverged (local à frente / história distinta da publicada `e916a110`) | none | snapshot_fresh_install_diverged |

Leitura honesta: `record --check` verde ×4 — os snapshots empacotados casam com
os especialistas **instalados**. Três dos quatro checkouts divergem da
`origin/main` publicada: Spark roda a feature branch do intake upstream-facts
(o schema foi renomeado na main → adapter adaptado, ver abaixo); API Forge roda
o commit pré-squash equivalente; Doctor API roda `main` local divergente da
publicada. Divergência classificada e documentada — não escondida.

### Drift real corrigido neste ciclo

O adapter Spark emitia `sparkforge/upstream-facts/v1` (pré-rename) enquanto a
main publicada do especialista declara `sparkforge_aws/upstream-facts/v1`.
`native_pkg.upstream_schema()` agora resolve o schema do pacote instalado com
fallback legado — o adapter segue o especialista instalado, não uma suposição.

## 4. Changes Implemented (waves)

| Commit | Wave | Conteúdo |
|---|---|---|
| `4f2fea4` | W0+W1 | reality manifests + matriz de staleness (`entry_fresh`, `relation_fresh`, policies, observations) |
| `7724281` | W2 | conformance federada: describe×4 → graph determinístico + fix upstream-facts schema |
| `5bea6b7` | W3 | `pack_stats` + benchmark Memory ROI |
| `6c9c67d` | W4 | suite oficial B01–B15 + hot-paths Cycle 5 |
| `2967bd3` | W5 | replay-attack suite §29 (10 casos) + collision test + security evidence report |
| `75a0032` | W6 | fechamento operacional: docs/ADR audit, status normalization, contract classification, package build |
| (HEAD) | W7 | Feature Freeze + dogfooding + scorecard + evidence manifest + release report + bump 0.4.0 |

## 5. Memory ROI (§14–§17)

Benchmark: `scripts/bench/run_memory_roi.py` → [`cycle-5.1-memory-roi.json`](cycle-5.1-memory-roi.json) · relatório [`cycle-5.1-memory-roi.md`](cycle-5.1-memory-roi.md).

```text
memory_off_bytes:   260 874
memory_on_bytes:     32 457
context_saved:      228 417 bytes  → 87.56% de economia
```

`pack_stats` instrumenta o pipeline real de `memory_pack`: entries terminais
foram **contadas mas nunca entregues**; surfaces desconhecidas/divergentes não
são fresh; retrieval determinístico. Caminho de influência real e governado:
`memory → failure_patterns → experiment → StrategyPolicy (approval_sha256) →
preferred_providers` — sem mutação automática de routing.

## 6. Planner & Graph Benchmarks

Suite oficial: `scripts/bench/run_scenarios.py` → [`cycle-5.1-scenarios.json`](cycle-5.1-scenarios.json) — **15/15 verdes**.

| Cenário | Resultado |
|---|---|
| B01 deterministic simple plan | pass |
| B02 artifact-aware multi-specialist plan | pass |
| B03 semantic ambiguity fallback | pass |
| B04 stale specialist surface | pass |
| B05 memory-assisted repeated task | pass |
| B06 poisoned memory | pass |
| B07 restricted remote target | pass |
| B08 independent verification | pass |
| B09 Global Stop optional nodes | pass |
| B10 strategy policy preference | pass |
| B11 graph conflict | pass |
| B12 unavailable specialist | pass |
| B13 fake remote receipt | pass |
| B14 A2A unverified target | pass |
| B15 cross-project memory import | pass |

Conformidade federada: `test_federation_conformance.py` — replay describe dos 4
adapters, manifests válidos, ids namespaced, graph build determinístico,
cadeias produces→consumes e `verified_by` resolvidos.

## 7. Economy

`unknown != zero` protegido (economia nunca inventa zero para o que não mediu);
métricas novas Cycle 5 (`memory_pack`, `plan_simulate`, `target_negotiate`,
`receipt_validate`, `observation_write`) adicionadas ao runner canônico.

## 8. Performance — hot-path baseline

[`cycle-5.1-hotpaths.json`](cycle-5.1-hotpaths.json) — `run_bench.py --check`,
baseline Cycle 5.1, fator 1.5, **0 regressões em 21 medições**:

```text
memory_pack        median 54.730 ms   p90  58.781 ms
plan_simulate      median  1.835 ms   p90   1.862 ms
target_negotiate   median  0.032 ms   p90   0.064 ms
receipt_validate   median  0.051 ms   p90   0.059 ms
observation_write  median  6.306 ms   p90   6.408 ms
```

Proveniência do benchmark: máquina, OS, Python, versão do Forge, commit e
estado do worktree registrados no próprio output (§65/§66).

## 9. Security — adversarial suite

Mapa completo §50 → evidência: [`cycle-5.1-security.md`](cycle-5.1-security.md).
18 vetores cobertos; suíte dedicada de replay §29 (`test_remote_replay.py`, 10
casos); data-classification com cap estrutural (`unknown`/`restricted`/
`confidential` nunca saem do boundary); A2A permanece `unverified` até política.

## 10. Test Matrix Final (§93)

| Domain | Unit | Contract | Integration | Reality | Adversarial | Benchmark |
|---|---:|---:|---:|---:|---:|---:|
| Memory | 2 | 0 | 1 | 0 | 1 | `run_memory_roi` |
| Graph | 4 | 0 | 3 | 0 | 0 | `graph_build` |
| Planner | 12 | 1 | 10 | 0 | 2 | B01–B04, B09, B11, B12 |
| Simulation | (em Planner) | — | — | 0 | 0 | `plan_simulate` |
| Targets | 1 | 0 | 1 | 0 | 1 | `target_negotiate` |
| Remote trust | 6 | 2 | 4 | 0 | 4 | B07, B13, B14 |
| Strategy | 3 | 3 | 3 | 0 | 0 | B10 |
| Economy | 1 | 0 | 2 | 0 | 0 | `run_bench` economy |
| Trace | 4 | 1 | 3 | 0 | 0 | — |
| A2A | (em Remote) | — | — | 0 | — | B14 |
| MCP | 1 | 1 | 1 | 0 | 1 | — |
| Specialists | 4 | 7 | 11 | 2 (`real_provider`) | 1 | replay conformance |
| Security | 5 | 0 | 3 | 0 | 5 | B06 |

(Totais por arquivo de teste e marker — `FILE_MARKERS` em `tests/conftest.py`.)

## 11. CI

```text
local:   GREEN — pytest offline 100%, ruff, mypy (203 arquivos), schema parity,
         pytest -m slow (package build + fresh install, 4/4)
remote:  REMOTE_BLOCKED — quota de GitHub Actions esgotada; jobs sobem sem
         steps; nenhum resultado falsificado
```

## 12. Definition of Done (§100) — respostas com evidência

| Pergunta | Resposta | Evidência |
|---|---|---|
| Quais versões de cada especialista foram validadas? | Spark 0.5.0 / API 0.1.0 / DoctorData 1.0.0rc1 / DoctorAPI 0.2.0 | reality manifest |
| Quais surfaces exatas? | surface_sha256 por especialista | `cycle-5.1-reality.json` |
| Como sabemos que os adapters são fresh? | `record --check` ×4 exit 0 | drift.status `none` |
| O que acontece quando um especialista muda? | surface fingerprint diverge → evidência bound vira stale; políticas velhas ficam neutras | `test_surface_staleness.py` |
| Engineering Memory ajuda? | Medido: 87.6% bytes de contexto economizados; influência governada | `run_memory_roi.py` |
| Quanto contexto a memória economiza? | 228 417 / 260 874 bytes no corpus do benchmark | memory-roi.json |
| Graph v2 reduz planos inválidos? | produces/consumes/requires/conflicts viram ordem e ambiguidade explícita | B02, B11 + conformance |
| Quando o semântico é útil? | Só como fallback quando determinismo esgota — ambiguidade nunca vira chute | B03 + ADR 0028 |
| Detecta evidência stale? | Sim — unknown ≠ fresh; fingerprint divergente = stale | test_surface_staleness |
| Dado restricted vai remoto? | Não — cap estrutural no contrato de request | §27 matrix |
| Receipts podem ser reexecutados? | Não — `request_sha256` binda task+context+budget+surface+target | `test_remote_replay.py` |
| Provider se declara trusted? | Não — self-declared = `unverified`; promoção só por política | B14 + test_a2a |
| LLM pode inventar capability? | Não — routing só aceita manifest-declared; edge inventada é dado, não verdade | fake-graph-edge test |
| StrategyPolicy passa por cima dos gates? | Não — preferência só depois dos hard gates | B10 + adversarial |
| Global Stop pula verificação? | Não — `verification_required` nunca é podado | B09 + e2e |
| Memória vaza entre projetos? | Não — escopo `project`/`workspace` recusado no import | B15 + testes |
| Surface mudada reusa política velha? | Não — política bound a fingerprint exato | stale-policy test |
| Benchmarks reproduzíveis? | Ambiente + SHAs + config no output | §66 fields |
| Run reconstruível? | Sim — receipt liga plan/simulation/evidence/verification/observation/trace | §83 + `replay` |
| Provado localmente? | 4328 testes + gates + benchmarks | §99 |
| Provado remotamente? | Nada — `REMOTE_BLOCKED` declarado | §57 |
| Bloqueado? | CI remota (quota) | — |
| Deferido? | remote transport, marketplace, reputation, Sigstore/in-toto completo, counterfactual runtime | security report |

## 13. Acceptance Criteria (§99)

- **Repository**: main limpa pós-merge; sem drift gerado (schemas verdes);
  package build válido (`pytest -m slow` 4/4). ✅
- **Specialists**: 4 revalidados, SHAs + surfaces + drift classificados. ✅
- **Compatibility**: conformance federada verde; divergências documentadas. ✅
- **Memory**: ROI instrumentado, on/off medido, influência com proveniência. ✅
- **Graph**: relações corretas + staleness regressions. ✅
- **Planner**: determinístico + fallback + validator soberano + simulação. ✅
- **Targets**: locality/trust/classification regressions. ✅
- **Remote**: trust model validado; replay protection testada; transporte
  **deferred** (não implementado — decisão). ✅
- **Strategy**: approval binding validado; auto-promoção inexistente. ✅
- **Economy**: benchmark produzido; unknown≠zero protegido. ✅
- **Trace**: federation validada (`correlation_id`/`parent_run`). ✅
- **Verification**: independência comprovada (B08, executor≠verifier). ✅
- **A2A**: external/unverified defaults preservados (B14). ✅
- **MCP**: integração atual validada, sem expansão. ✅
- **Security**: suíte adversarial verde. ✅
- **Performance**: hot-path baseline capturado. ✅
- **CI**: local verde; remoto `REMOTE_BLOCKED` corretamente marcado. ✅
- **Documentation**: reality-aligned; limitações explícitas; status corrigido. ✅
- **Freeze**: formalizado em `docs/feature-freeze.md`. ✅
- **Dogfooding**: guia + taxonomia em `docs/dogfooding.md`. ✅

## 14. Versioning decision (§98)

`0.3.0 → 0.4.0` (minor aditivo): novas APIs públicas (`entry_fresh`,
`pack_stats`), coletor de realidade, suite B01–B15, correção do adapter Spark.
Nada breaking; `1.0` **não** é emitido — decisão adiada para depois do
dogfooding real (§75, scorecard).

## 15. Known limitations (declaradas, não escondidas)

- **Remote transport**: deferido — `remote.py` é só política+contratos (§30).
- **Marketplace / public registry**: deferido (ADR 0036).
- **Reputation engine**: deferido — observações são dados, não ranking.
- **Sigstore/in-toto completo**: future hardening documentado.
- **Counterfactual planning**: contract-only — `FOUNDATION_ONLY`.
- **CI remota**: bloqueada por quota; os gates locais acima são a prova atual.
- **3/4 checkouts de especialistas divergem da origin/main publicada** —
  classificado no reality manifest; snapshots casam com o que está instalado.
