# Cycle 3.1 — Wave I: CI workflows + ecosystem contract tests

Escopo: Phases 44 (adapter drift workflow), 45 (release compatibility), 46
(four-provider real CI), 47 (no silent skips) e 48 (ecosystem contract tests).

## I.1 — `provider-surface-drift.yml` (Phase 44)

Workflow semanal + `workflow_dispatch` que instala a main de cada especialista
num venv próprio (Spark/Doctors em 3.11, API em 3.12) com o adapter deste
checkout e roda `python -m theforge_<adapter>.record --check` — a superfície
nativa viva contra o snapshot gravado no adapter.

O `--check` agora classifica em três estados, em vez do binário anterior:

- `none` — snapshot idêntico à superfície viva;
- `additive` — tools/seams/capabilities novos, request kinds novos ou bump de
  versão sem mudança de superfície (compatível; exit 0, reportado no log);
- `breaking` — item gravado removido ou alterado, request kind removido,
  versão de contrato movida (exit 1; job vermelho).

Implementado nos quatro `record.py`: `classify_drift(packaged, fresh)` +
`--check` novo no apiforge e no sparkforge; os dois Doctors tinham `--check`
binário (fingerprint) e foram promovidos à mesma classificação. O snapshot
nunca é re-gravado nem auto-mergido pelo CI.

## I.2 — `release-compat.yml` (Phase 45)

Workflow semanal + `workflow_dispatch` cross-repo: instala a main de cada
especialista no seu interpretador declarado e roda
`theforge provider check -- <venv>/bin/python -m theforge_<adapter>` — a
bateria de conformidade do Forge Protocol, independente de versão de pacote.

## I.3 — `ecosystem-real.yml` (Phase 46)

`real-providers.yml` renomeado para o nome pedido pelo Phase 46; o conteúdo já
era o de cinco ambientes separados (core 3.11 + Spark 3.11 + API 3.12 +
Doctor Data 3.11 + Doctor API 3.11, cada um com especialista + adapter) desde
o Wave E.3.

## I.4 — No silent skips (Phase 47)

`tests/real_providers.py` aceita agora o alias `THEFORGE_ECOSYSTEM_REQUIRED=1`
além de `THEFORGE_REAL_PROVIDERS_REQUIRED=1`: em modo required, pré-requisito
ausente **falha** o teste em vez de pular. O workflow exporta a variável
específica; a alias cobre quem orquestra pelo nome do ecossistema.

## I.5 — Ecosystem contract tests (Phase 48)

`tests/test_ecosystem_contracts.py` — os seis fluxos de fronteira, offline,
com os quatro adapters reais em `--replay` (mesma fronteira subprocess/JSON):

| Fluxo | Prova |
|---|---|
| Doctor Data bundle → Forge | `data.scan` → `ExecutionResult` com `native/handoff.json` (`forge-contracts/1`), hashes verificam |
| Doctor API bundle → Forge | `api.diagnose` idem |
| Forge handoff → Spark Forge | `forge-doctor-data → spark-forge`: Handoff válido entregue e **consumido** (facts `upstream:` no resultado) |
| Forge handoff → API Forge | `forge-doctor-api → api-forge`: idem |
| Spark receipt → Forge | `ExecutionReceipt` estrito com fingerprint + versões + surface fingerprints |
| API receipt → Forge | `provider_receipt` `{ref: case:<id>, sha256}` atravessa ao receipt |

### Correção de replay no adapter sparkforge

Regravar `scenarios/cross` com `record_execute --handoff` (intake upstream real)
exigiu espelhar a semântica que o apiforge já tinha: em replay, as facts
`upstream:` do output gravado são **descartadas** quando a requisição não traz
handoff, e **re-derivadas** do handoff da requisição quando traz —
`_upstream_replay` em `execute.py`, com a provenance sempre do run atual. Sem
isso, o spark replay vazava facts upstream gravadas em runs sem handoff.

## Prova

- `test_ecosystem_contracts.py`: 6/6 verdes
- `test_cross_forge_replay.py` + adapters: suíte focada toda verde
- `test_ci_workflows.py`: estrutura dos três workflows coberta (hardening,
  checkouts com token, venvs, ordens de passos, `--check`/`provider check`)
- `record --check` verificado ao vivo nos venvs `.venv-spark`/`.venv-api`/
  `.venv-dd`/`.venv-da`: `surface drift: none` nos quatro

## Arquivos

- `.github/workflows/provider-surface-drift.yml`, `release-compat.yml` (novos);
  `real-providers.yml` → `ecosystem-real.yml` (rename)
- `adapters/*/src/theforge_*/record.py` — `--check`/`classify_drift`
- `adapters/sparkforge/src/theforge_sparkforge/execute.py` — `_upstream_replay`
- `tests/test_ecosystem_contracts.py` (novo), `tests/real_providers.py`
  (alias), `tests/test_ci_workflows.py`, `tests/test_adapter_*.py`,
  `tests/test_cross_forge_replay.py` (docstring), `tests/conftest.py`
- `tests/fixtures/native/sparkforge/scenarios/cross/` — regravado com handoff
- `docs/real-providers.md`, `docs/architecture.md`, este relatório
