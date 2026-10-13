# Cycle 3.1 — Wave C: adapters nas mains, intake upstream estável, core sem domínio

Escopo: Phases 4–8 e 35 do `prompt_evo_cycle3_1.md`. Premissa do audit
(`cycle-3.1-audit.md`): a prova cross-forge dependia da branch `feat/upstream-facts`
do api-forge — o intake `--upstream` não existia na `main`.

## O que mudou

- **API Forge main com intake upstream** (repo `api-forge`, PR
  [#34](https://github.com/EdgarSocrates98/api-forge/pull/34), mergeado em `1745f87`):
  cherry-pick de `a9ae606` sobre a main (`0759b4c`) + endurecimento (`4deaa85`) —
  recusa `AF-UPSTREAM-FORBIDDEN` de chaves imperativas/de roteamento/prompt
  (recursiva), namespaces `upstream:`/`upstream.` obrigatórios, extractor nativo
  `apiforge` proibido em facts upstream (anti-laundering), tetos 128 facts/256 KiB,
  `attrs.upstream` com `provider`/`run_id`/`node`/`item`. Facts upstream são
  persistidos com provenance e nunca entram no modelo julgado local.
- **`theforge_apiforge` 0.2.0**: `manifest_payload` declara `features:
  ["handoff/v1"]`, `adapter_version` e `native_surface_fingerprint` (sha256 do
  snapshot canônico menos `recorded_at`). `native_matrix.json` regravado contra
  `apiforge` main `1745f87`: 21 capabilities, conteúdo idêntico, `provenance` agora
  `"recorded"`. `record.py` ganha `--environment <dir>` (grava `environment.json` +
  `health.json` do cenário, espelhando o gravador Spark).
- **`theforge_sparkforge` 0.2.0**: `native_fingerprint` no catálogo + manifest
  emite `adapter_version`/`native_surface_fingerprint`. Snapshot regravado contra
  `sparkforge-aws` main `5a46aa9`: 136 tools idênticas — `recorded_at` retido, sem
  diferença de superfície. Sem `features`: o Spark produz evidência; o handoff é
  montado pelo core, não consumido por ele.
- **Fixtures regravadas**: `scenarios/cross/api.analyze.analyze.json` agora sai de
  `record_execute --handoff` real (`provenance: "recorded"`, com a fact upstream
  `upstream:9f92946be0de7b17` e `derived_from`); `environment.json`/`health.json` dos
  cenários `default` e `cross` saem dos gravadores. Resta `hand-built` apenas
  `default/api.change-control.run.json` — o verbo embute caminhos de máquina e o
  gravador o recusa (documentado; destrava quando o verbo portabilizar paths).
- **Docs**: `real-providers.md` (intake na main pós-#34, tetos corrigidos para
  32 itens/32 KiB no adapter, fixtures regravadas), `protocol.md` (bound correto do
  intake), `versioning.md` (linha 0.2.0 com adapters 0.2.0), READMEs dos adapters.

## Phase 8 — prova em mains puras

`tests/test_cross_forge_real.py` com `.venv-spark` (sparkforge-aws `5a46aa9`) e
`.venv-api` (apiforge `1745f87`): **2/2 passam**. `tests/test_real_providers.py`:
**16/16 drift checks**. O plano Spark→API roda `pyspark.static-analysis` →
`api.analyze` com handoff real consumido via `--upstream`; evidência upstream chega
com provenance e `derived_from`; A/B com e sem handoff difere; replay e explain
convergem.

## Phase 35 — core sem domínio

Audit de `src/theforge`: zero referências a spark/api/domínio fora de comentários;
zero capability-ids de especialista hardcoded. Nada a remover — a separação
control-plane/especialista já estava íntegra e segue íntegra.

## Gates (local — GitHub CI fora de cota)

- `pytest -q`: suíte completa verde (pins de versão `0.1.0→0.2.0` dos adapters e
  asserções `hand-built→recorded` atualizados em `test_adapter_shell.py`,
  `test_adapter_apiforge.py`, `test_adapter_sparkforge.py`,
  `test_cross_forge_replay.py`).
- `ruff check .`: limpo. `mypy src` + adapters: limpo.
- Cross-forge real: 2/2. Real-provider drift: 16/16. Replay cross: verde.
- api-forge (repo irmão): 10/10 upstream-focused, ruff e mypy limpos antes do merge.

## Decisões

- O adapter declara `features: ["handoff/v1"]` explicitamente (não depende do
  leitor derivar de `accepts_handoff`); `native_surface_fingerprint` exclui
  `recorded_at` — regravação idêntica preserva o fingerprint.
- Bump dos adapters para 0.2.0: superfície do manifest mudou (campos novos) —
  releases independentes por ADR 0014, matriz de `versioning.md` atualizada.
- `change-control` continua `hand-built` por recusa legítima do gravador
  (caminho de máquina) — preferido a enfraquecer a proteção anti-path.

## Gaps / próximos passos

- Doctors (Data/API) ainda sem adapters — Wave D.
- `semantic-handoff`/`delta`/`graph-refs` seguem declaráveis sem consumidor —
  waves E/F/J.
- CI do GitHub indisponível (cota esgotada): gates locais são a evidência.
