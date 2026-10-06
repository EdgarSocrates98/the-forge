# Cycle 3.1 — Wave E: relações de capability, observe→engineer e verify pipelines

Escopo: Phases 13–16 e 36–40 do `prompt_evo_cycle3_1.md`. O core já tinha a
mecânica inteira (grafo de capabilities, planner `produces → consumes`, handoff
bus, verificação independente automática); o Wave E declara as relações nos
adapters e adiciona o op `verify` nos Doctors — **zero mudanças no core** até
Phase 37 (nested receipts, contrato aditivo).

## E.1 — verify ops + relações de catálogo (Phases 13/14, provider side)

- **`theforge_doctordata`**: novo `verify_op.py` — audit determinístico de
  coerência do `VerifyRequest` (findings↔evidence, `hash` exige `location`,
  artifacts do handoff exigem hash, `epistemic` exigido em itens de
  evidência/finding/constraint). Veredito `passed`/`failed` com `details` +
  `basis`; payload inválido → `refused` (`ADAPTER-REQUEST-INVALID`), specialist
  ausente → `refused` (`*-ADAPTER-UNAVAILABLE`). Nunca promove epistemic.
- **`theforge_doctorapi`**: `verify_op.py` espelhado (mesmo audit; o strict-parse
  de documentos continua na capability `api.verify` — o `handoff` do
  `VerifyRequest` é o envelope `theforge/Handoff/v1`, não um documento nativo).
- **Catálogos** (Phases 13/14 — declare, não compute):
  - `data.scan`/`api.diagnose` → `produces: data.diagnostic-evidence` /
    `api.diagnostic-evidence` (tipo do artefato que o bus entrega ao consumidor).
  - `data.verify` → `can_verify: spark-forge/<16 capabilities>`;
    `api.verify` → `can_verify: api-forge/{api.analyze, api.change-control}` —
    refs que deixarem de resolver ficam registradas no grafo, nunca descartadas.
  - `api-forge/api.analyze` → `consumes: (api.diagnostic-evidence,
    data.diagnostic-evidence)` — intake real via `--upstream`
    (`apiforge/upstream-facts/v1`, estável na main desde o PR #34).
  - `ops` dos dois Doctors incluem `verify`; `verify/v1` é implícito pelo op
    (`_FEATURE_BACKING` já cobre).
- **Core, sem mudança**: `select_verifier` exige provider distinto +
  `relations.can_verify` resolvendo; `refused`/`error`/malformed do verificador
  viram `not_performed` (nunca prova contra o produtor); `failed` demove o run
  para `partial` com `independent verification failed: <provider>`.
- **Fixtures de teste**: `fixture_forge.py` ganhou `hash_evidence` (evidence com
  `hash` sem `location` — legal no contrato, não-verificável semanticamente) e
  três manifests-aliases (`fixture-sparkforge`, `fixture-sparkforge-hash`,
  `fixture-apiforge`) que se apresentam com os ids reais dos providers para os
  refs `can_verify` resolverem.
- **Testes**: ops/relations nos manifests dos dois Doctors; verify op
  (passed/failed/refused/malformed/handoff); e2e com adapters reais em
  `--replay` — Doctor Data verifica run do `spark-forge` (passed e failed→
  partial), Doctor API verifica `api-forge` (passed); `OPS` do shell test ganha
  `verify`.
