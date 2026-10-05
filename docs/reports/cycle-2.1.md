# Cycle 2.1 — Closure & Proof (relatório de trabalho)

- Branch: `feat/cycle2.1-cycle3`
- Início: 2026-10-05
- Status: IN PROGRESS
- Fonte de requisitos: `prompt_evo_cycle2_cycle3.md` (arquivo local, fora do git por `.gitignore`).

Este documento acompanha o Cycle 2.1 onda a onda. Cada onda registra: objetivo, arquivos
alterados, contratos criados/evoluídos, decisões arquiteturais, testes adicionados, testes
executados, resultados, benchmarks, security findings, limitações, dívida criada e próximos
passos.

## Reality check da `main` (Fase 1)

Auditoria feita em 2026-10-05 sobre `main` = `1eaa285` (merge do PR #4), Windows,
Python 3.14.6, antes de qualquer alteração. Fontes: leitura do código, `git log`,
`gh run view`, execução da suíte offline.

| Requirement | Claimed state (cycle-2.md, 2026-10-04) | Actual implementation | Tests | Remote evidence | Gap | Required action |
|---|---|---|---|---|---|---|
| Waves B–E na `main` | branches só locais, `main` em `b1d9ec7` | mergeadas no PR #4 (`1eaa285`) | — | `gh pr view 4`; run 37255244389 | relatório desatualizado | Wave A |
| CI pós-merge | "nenhum run depois da Wave A" | verde: 10 jobs (Ubuntu+Windows × py3.11–3.14, package ×2) | — | runs 37254645706 (PR), 37255244389 (main) | relatório desatualizado | Wave A |
| Suíte offline | 2719+5 (Wave D) | 2859 passed, 5 skipped, 0 failed | 77 arquivos | — | contagem desatualizada | Wave A |
| `real-providers.yml` | nunca executado | workflow completo; `THEFORGE_REAL_PROVIDERS_REQUIRED=1`; seleção vazia falha (exit 5 propaga) | `test_real_providers*.py` | dispatch 37260501716 em `main` | prova remota pendente | Wave B |
| `compat.yml` | nunca executado | `workflow_dispatch`, macOS × py{3.11, 3.14} | `test_compat_matrix.py` | dispatch 37260503904 em `main` | prova remota pendente | Wave B |
| `RunStore.read_optional` | "segue `<name>.json` simbólico" (follow-up aberto) | confirmado: `path.is_file()` segue symlink; `persisted_sha256`/`read`/`read_contract` idem | nenhum sobre symlink | — | escape de leitura via symlink | Wave C1 |
| `_finish` duplo | follow-up aberto | confirmado: erro não-persistência dentro de `_finish` (ex.: `IntegrityError` do `validate_receipt`) reentra `_finish` via `except Exception` | nenhum | — | re-terminalização | Wave C2 |
| Verification pós-erro interno | follow-up aberto | confirmado: exceção entre execute e `_record_verification` deixa run sem `verification` apesar de provider ter executado | nenhum | — | evidência perdida | Wave C3 |
| Artifacts declarados | "só conferido de forma léxica" (follow-up) | parcial: `explain` usa `lexists` (`hashcheck.work_artifacts`), mas `diverged_artifacts` do execute só compara hash | `test_verification.py` | — | classificação física (missing/broken/escape) | Wave D |
| Explain de `installation` | "falta teste" (follow-up) | `PlanSection.installation` existe e `hashcheck` cobre `plan.installation_sha256` | sem teste dedicado | — | só teste | Wave E1 |
| Drift live no cenário cross | follow-up aberto | `test_cross_forge_real` compara gravações parcialmente; sem check de drift live dedicado | — | — | Wave E2 | Wave E2 |
| Consumo de handoff | "adapters não declaram `accepts_handoff`" | confirmado: `execute_reply` do `theforge_apiforge` ignora `payload["handoff"]` | `test_cross_forge_replay.py` (limitação esperada) | — | transporte sem consumo | Wave F |
| `record_execute` do API Forge | "gravações montadas à mão" | `theforge_apiforge.record` só grava snapshot; cenários de execute são hand-built (`"provenance": "hand-built"`) | — | — | gravador ausente | Wave G |
| Follow-ups listados | 15+ itens abertos | confirmados por leitura: taskkill fallback, `GetLastError` ordering, cache pruning, policy flatten warning, `gethostbyname*`, `lexists` de artifacts, normcase macOS, pipe helpers, `hash_file`, `#L2`, `and/or`, verification pós-erro, `_finish` duplo, explain de installation, drift cross, symlink de artifact | — | — | classificação pendente | Wave H |
| Gate final do ciclo | STATUS CLOSED ausente | — | — | — | relatório final | Wave I |

Itens fora do escopo do Cycle 2.1 (pertenecem ao Cycle 3): routing semântico, execução
`delegate`/`parallel`/`debate`, scheduler/resume, verificação independente (`verify`),
economy avançada, `.forge/` project intelligence, tracing, provider SDK.

## Gap matrix → ondas

| Gap | Onda | Tipo |
|---|---|---|
| Documentação pós-merge desatualizada | A | docs |
| `real-providers.yml`/`compat.yml` sem run remoto | B | evidência CI |
| `RunStore` segue symlink | C1 | segurança |
| `_finish` reentrante | C2 | invariante |
| Verification ausente em erro pós-execute | C3 | integridade |
| Classificação física de artifacts declarados | D | integridade |
| Explain/cross-drift sem cobertura | E | testes |
| Handoff transportado mas não consumido | F | feature delimitada |
| `record_execute` do API Forge ausente | G | tooling |
| Follow-ups não classificados | H | processo |
| Gate final + relatório de fechamento | I | processo |

## Wave A — Post-Merge Validation Update

- **Objetivo:** registrar em `cycle-2.md` o estado pós-merge sem apagar o histórico.
- **Arquivos alterados:** `docs/reports/cycle-2.md` (nota de estado na geração + seção
  `Post-Merge Validation Update`), `README.md` (linha de status aponta o encerramento),
  `docs/reports/cycle-2.1.md` (este documento).
- **Contratos:** nenhum.
- **Decisões arquiteturais:** a atualização vive numa seção nova no fim do relatório, com
  tabela "estado na geração × estado validado"; o README deixa de dizer "concluído" até a
  Wave I declarar CLOSED.
- **Testes adicionados:** nenhum (mudança documental coberta pelos checkers existentes).
- **Testes executados:** `python -m pytest tests/test_docs_consistency.py` — 30 passed.
- **Resultados:** commit `022be38` na branch `feat/cycle2.1-cycle3`; push inicial criou
  `origin/feat/cycle2.1-cycle3` (necessário para `workflow_dispatch --ref`).
- **Benchmarks:** n/a.
- **Security findings:** nenhum.
- **Limitações:** os runs de `real-providers.yml`/`compat.yml` despachados sobre `main`
  provam a funcionalidade do workflow no estado mergeado; a prova sobre o conteúdo final da
  branch fica para a Wave B/relatório final.
- **Dívida criada:** nenhuma.
- **Próximos passos:** Wave B recolhe os resultados dos dispatches e reexecuta os workflows
  sobre a branch.

## Wave B — Workflows remotos (`real-providers.yml`, `compat.yml`)

- **Objetivo:** prova remota de integração real (Spark Forge + API Forge) e da matriz
  macOS, via `workflow_dispatch`.
- **Arquivos alterados:** `.github/workflows/real-providers.yml` (o interpretador do core
  passa a instalar os adapters), `tests/test_ci_workflows.py` (regressão exige a linha de
  instalação com adapters), `tests/test_context_git.py` (flake fix, abaixo).
- **Contratos:** nenhum.
- **Decisões arquiteturais:** os venvs dos especialistas continuam isolados; o interpretador
  que roda `pytest -m real_provider` precisa dos pacotes `theforge_*` importáveis porque os
  testes de adapter importam o adapter diretamente.
- **Execuções:**
  - `main`: `real-providers` run `37260501716` — **failure** na coleta
    (`ModuleNotFoundError: theforge_apiforge`/`theforge_sparkforge`): o workflow instalava
    os adapters só nos venvs dos especialistas. Fix: `python -m pip install -e .[dev]
    -e ./adapters/sparkforge -e ./adapters/apiforge` (commit `d96eb3b`).
  - `main`: `compat` run `37260503904` — **success** (macOS × py3.11 + py3.14).
  - branch (commit `d96eb3b`): `real-providers` run `37261291846` — **success**:
    17 passed, 2868 deselected; ubuntu-latest; core py3.11, Spark venv py3.11,
    API venv py3.12; `theforge 0.1.0`, `theforge-sparkforge-adapter 0.1.0`,
    `theforge-apiforge-adapter 0.1.0`; checkout real de `spark-forge-aws` e `api-forge`
    (main de cada repo).
  - branch (commit `d96eb3b`): `compat` run `37261294177` — **failure** apenas em
    `macos-latest / py3.14`: `test_control_plain_status_would_have_written` falhou com
    `FileNotFoundError` em `.git/objects/maintenance.lock` — race entre `rglob`/`lstat`
    do helper `_snapshot` e a auto-maintenance do git. Flake do harness (não do produto),
    presente também na `main`.
  - **Fix do flake (commit seguinte):** `_init` desliga `gc.auto`/`maintenance.auto` no
    repo de teste e `_snapshot` tolera entradas que somem entre o `rglob` e o `lstat`
    (um arquivo removido continua detectável por diferença de chaves entre snapshots).
  - Re-dispatch de `compat` após o fix: pendente (registrado aqui quando concluir).
- **Testes adicionados/alterados:** `test_ci_workflows.py` passa a exigir a linha de
  instalação com adapters antes de `pytest -m real_provider`.
- **Testes executados:** `pytest tests/test_ci_workflows.py` — 18 passed;
  `pytest tests/test_context_git.py` — 40 passed.
- **Resultados:** prova remota real dos dois Forges alcançada; compat depende do
  re-dispatch após o fix de flake.
- **Benchmarks:** n/a.
- **Security findings:** nenhum (o workflow expõe apenas repos públicos; sem secrets novos).
- **Limitações:** a prova live usa os `main` dos repos irmãos no momento do run; versões
  exatas ficam registradas no relatório final (Wave I).
- **Dívida criada:** nenhuma.
- **Próximos passos:** re-dispatch de `compat`; Wave C.

## Wave C — RunStore symlink hardening + invariante de terminalização + verification pós-erro

- **Objetivo:** (C1) artifact de run nunca é lido/escrito através de link;
  (C2) um run tem no máximo um caminho de terminalização e um receipt;
  (C3) um run que executou provider registra `VerificationResult` mesmo quando o core
  falha depois.
- **Arquivos alterados:** `src/theforge/runs/store.py`, `src/theforge/forger/orchestrator.py`,
  `src/theforge/forger/plan_executor.py`, `tests/test_runs_state.py`,
  `tests/test_finalize.py` (novo), `tests/conftest.py` (FILE_MARKERS).
- **Contratos:** nenhum (mudança de enforcement, não de schema).
- **Decisões arquiteturais:**
  - `RunStore._artifact_file` usa `lstat` (nunca segue o último componente) +
    `realpath` containment contra `runs_dir`: link simbólico (válido, quebrado ou
    apontando a outro run), diretório e run-dir linkado para fora viram `PERSIST_READ`
    controlado; ausente continua `None` (sem oráculo novo). `_read_bytes` abre com
    `O_NOFOLLOW` onde existe (fecha a janela TOCTOU POSIX); no Windows a pré-checagem
    permanece — limitação documentada, sem sandbox de OS.
  - `write()` recusa sobrescrever um path existente que não é arquivo regular e confere
    containment antes de `tmp.replace` (run-dir linkado para fora não recebe escrita).
  - `_Trace.terminal`/`_PlanTrace.terminal`: `open -> finalizing -> finalized`; `_finish`
    reentrante é `PERSIST_WRITE`; uma falha interna dentro do `_finish` (ex.:
    `ContractError` do `validate_receipt`) vira `PersistenceError` de "terminalization
    failed" — nunca um segundo `_finish` silencioso.
  - `Forger._late_verification`: ao terminalizar, se o provider executou e ainda não há
    `verification`, grava o que se sabe (`response_status`, `result_seen` capturados logo
    após o execute/negociação); checks que não rodaram ficam `not_performed`; falha de
    contrato na gravação vira limitação `verification-unavailable` (o receipt terminal
    não se perde); falha de persistência propaga, como todo artifact.
- **Testes adicionados:** 7 casos hostis de artifact em `test_runs_state.py` (link externo,
  link para outro run, diretório, link de diretório, link quebrado, run-dir linkado para
  fora, escrita sobre link) e `test_finalize.py` com 9 casos (double `_finish`, falha de
  escrita de receipt, falha de persistência, erro interno pré/pós-execute, provider crash,
  falha de telemetria, falha de graph, falha de receipt em plan).
- **Testes executados:** `pytest tests/test_finalize.py tests/test_runs_state.py` —
  61 passed; suíte relacionada (`test_forger`, `test_forger_binding`, `test_plan_flow`,
  `test_hashcheck`, `test_replay`, `test_verification`, `test_security`) — 192 passed.
- **Resultados:** os três follow-ups C1/C2/C3 fechados com evidência; `hashcheck` reporta
  artifact linkado como divergência `unreadable` (compatível com a nova store).
- **Benchmarks:** leitura de artifact agora faz `lstat` + `realpath` + `os.open`: custo
  adicional desprezível por leitura (medido junto ao gate de performance, Wave I).
- **Security findings:** fechado o escape de leitura de artifact via symlink (segredo fora
  do runs dir nunca é servido como artifact); residual TOCTOU no Windows documentado.
- **Limitações:** `O_NOFOLLOW` indisponível no Windows — a janela TOCTOU residual entre
  `lstat` e `open` permanece lá; `realpath` containment ancora no runs dir físico.
- **Dívida criada:** nenhuma nova.
- **Próximos passos:** Wave D (integridade física de artifacts declarados).

## Wave D — Integridade física de artifacts declarados

- **Objetivo:** classificar fisicamente por que um `Artifact` declarado não verifica:
  escape lexical, ausência, link (quebrado ou apontando fora), não-regular, hash divergente.
- **Arquivos alterados:** `src/theforge/context/verify.py` (nova
  `declared_artifact_problem`), `src/theforge/forger/verification.py` (nova
  `artifact_problems`; `diverged_artifacts` delega; detalhe do check `artifact-hashes`
  ganha a razão por artifact), `tests/test_verification.py`.
- **Contratos:** nenhum — a limitação `FORGE-RESULT-ARTIFACT-HASH: <path>` não muda;
  só os `details` do check ficam mais precisos.
- **Decisões arquiteturais:** classificação em ordem estrita (lexical → existência →
  resolução física → regular → hash), sem stat fora de `work/`; link cujo alvo permanece
  dentro de `work/` verifica por conteúdo. `hashcheck` mantém sua semântica própria de
  divergência (`missing`/`modified`/`unreadable`), já adequada ao explain.
- **Testes adicionados:** broken symlink, diretório declarado como artifact, link interno
  que verifica por conteúdo, e uma tabela de classificação cobrindo missing / not-regular /
  hash-differs / link-outside / broken-link / `..` / absoluto — 4 testes novos.
- **Testes executados:** `pytest tests/test_verification.py` — 19 passed; ruff e mypy limpos.
- **Resultados:** a verificação de artifacts agora diz *por que* cada path falhou.
- **Benchmarks:** n/a (mesma leitura de antes, mais dois `stat` por artifact divergente).
- **Security findings:** nenhum novo; a ordem lexical→física garante que nenhum stat
  acontece fora de `work/` (alinhado com `hashcheck`).
- **Limitações:** razão de link-escape e broken-link compartilham a mesma string
  ("unresolvable or a link resolving outside work/") — distinguir os dois exigiria
  resolver o prefixo pai; não vale o custo.
- **Dívida criada:** nenhuma.
- **Próximos passos:** Wave E (explain de `installation` + drift live cross-forge).

## Wave E — Explain/hashcheck de `installation` + drift live do cenário cross

- **Objetivo:** (E1) provar que um plan run com `installation.json` é integralmente
  verificável e explicável — o receipt ancora `plan.installation_sha256`, o hashcheck o
  confere e o explain expõe os itens; (E2) levar ao cenário cross a mesma checagem de
  drift live que o cenário default já tinha.
- **Arquivos alterados:** `tests/test_hashcheck.py` (helper `_installation_run` + teste),
  `tests/test_explain_report.py` (teste do explain do run recusado),
  `tests/real_providers.py` (helpers de drift promovidos a utilitários compartilhados:
  `run_native`, `left_in`, `id_shape`, `id_shapes`, `top_keys`, `NATIVE_TIMEOUT`,
  `ID_KEYS`), `tests/test_real_providers.py` (usa `rp.*`; helpers locais removidos),
  `tests/test_cross_forge_real.py` (id formats nos case files da API + teste novo do
  lado Spark Forge).
- **Contratos:** nenhum.
- **Decisões arquiteturais:**
  - Nenhum follow-up de produção existia: `hashcheck` já mapeia `installation` via
    `PlanRefs.installation_sha256` e `report.py` já digita `PlanSection.installation`.
    O gap era de **evidência** — nenhum teste exercitava o caminho. Fechado com um plan
    run `refused` real (provider `invalid-manifest`): hash verificado no estado limpo,
    divergência `modified` ao alterar, `missing` ao apagar, leitura estritamente read-only
    (snapshot idêntico + `Popen` interditado) e explain com os itens
    (`provider`/`state`/`source`/`nodes`/`reason`, `planning_only`), válido contra o
    schema publicado.
  - Os helpers de drift saíram de `test_real_providers.py` para `real_providers.py` —
    o módulo de harness já compartilhado pelos dois arquivos `real_provider` — em vez de
    duplicar lógica ou importar módulo de teste de outro (sem precedente no repo).
  - E2 cobre os dois lados do cenário cross: API compara `case_files` por top-level keys
    **e** `id_shapes` (antes só keys); Spark ganha um drift próprio — `record_execute`
    re-executa `pyspark.static-analysis/pyspark` ao vivo sobre o workspace cross montado
    com os mesmos argumentos da gravação (`path=data-pipeline/jobs`) e compara `tool`,
    `arguments`, top-level keys de `recording`/`output`/`judge`/`judge.output` e os
    formatos de id nativos.
- **Testes adicionados:** `test_plan_run_checks_the_installation_artifact_its_receipt_records`,
  `test_refused_plan_run_surfaces_the_installation_items`,
  `test_spark_cross_recording_matches_the_live_native_output`; extensões de asserção no
  bloco de drift da API do teste de prova cross.
- **Testes executados:** `pytest tests/test_hashcheck.py tests/test_explain_report.py` —
  26 passed; `pytest tests/test_real_providers_env.py` — 38 passed;
  `pytest tests/test_compat_matrix.py tests/test_docs_consistency.py
  tests/test_ci_workflows.py` — 57 passed; ruff + mypy limpos nos arquivos tocados.
  **Live local:** `.venv-spark` (py3.11) e `.venv-api` (py3.12) recriados a partir de
  worktrees limpos das `main` dos irmãos (`spark-forge-aws` `5a46aa9` = `origin/main`;
  `api-forge` `daae355` = `origin/main`, os mesmos refs do CI) —
  `pytest -m real_provider tests/test_real_providers.py tests/test_cross_forge_real.py`
  = **18 passed** (17 anteriores + o novo teste Spark).
- **Resultados:** integridade do `installation` provada de ponta a ponta (receipt →
  hashcheck → explain); o cenário cross agora detecta drift de execute dos dois Forges,
  não só do API.
- **Benchmarks:** n/a.
- **Security findings:** nenhum; as leituras continuam read-only e contidas.
- **Limitações:** a prova live depende dos refs dos irmãos no momento do run (o snapshot
  drift test falhou localmente contra a branch de dev `codex/evo-agentic-economy` —
  comportamento correto do detector; validado contra `origin/main`). Detalhes internos
  abaixo das top-level keys dos outputs nativos continuam fora do escopo do drift check.
- **Dívida criada:** worktrees locais `E:/projetos/.sibling-main/{spark-forge-aws,
  api-forge}` e `.venv-spark`/`.venv-api` são ambiente de desenvolvimento (fora do git);
  remover ao final do ciclo ou documentar em `docs/real-providers.md` se ficarem
  permanentes.
- **Próximos passos:** Wave F (consumo semântico de handoff no adapter do API Forge).

## Wave F — True Semantic Handoff (consumo real, não só transporte)

**Status:** concluída — `64b253e` (the-forge) + `a9ae606` (api-forge `feat/upstream-facts`).

- **Gap encontrado:** o core já persistia e entregava o `Handoff` em todo
  `ExecuteRequest`, mas o adapter do API Forge ignorava o campo — `accepts_handoff`
  não existia e o `analyze` nativo não tinha intake. Declarar a flag sem superfície
  seria fingimento; a wave exigiu mudança real no especialista.
- **Especialista (repo irmão `api-forge`, branch `feat/upstream-facts`, worktree
  `E:/projetos/.sibling-f`, commit `a9ae606`):** `analyze` ganhou `--upstream
  <arquivo>` com documento `apiforge/upstream-facts/v1` bounded (32 itens, 64 KiB);
  `analyze_project` aceita `upstream=` e persiste as facts no `facts.json` do caso.
  Recusas expõem `AF-ANALYZE-UPSTREAM-{INVALID,LIMIT,PROVENANCE}` (documentados em
  `docs/catalog-contract.md`). `capabilities verify` + `sdd check` verdes.
- **Contrato:** `Evidence.derived_from: EvidenceSource{provider, run_id, item,
  node?, plan_run?}` — provenance estruturada da evidência derivada. Schemas
  regerados (`python -m theforge.contracts.schema schemas`).
- **Adapter:** `catalog.py` marca `accepts_handoff` só em `api.analyze`
  (`VerbSpec.upstream`); novo `handoff.py` traduz `Handoff` → upstream-facts com
  provenance completa (`provider`, `run_id`, `node`, `plan_run`, `item`,
  `epistemic` **verbatim**, `claim`, `location`), bounds próprios e limitações
  honestas; `execute.py` grava `upstream-facts.json` no cwd nativo, passa
  `--upstream`, e remove o arquivo no cleanup. Probe `_upstream_supported()`
  detecta o intake por assinatura — especialista antigo degrada a `ok`/`partial`
  + limitação, nunca inventa evidência. `translate.py` emite `Evidence` com id
  `upstream:<hash>` e `derived_from` para facts `extractor=theforge/handoff`;
  facts sem provenance são puladas com limitação.
- **Replay:** `_upstream_replay` re-deriva as upstream facts do handoff **da
  requisição** — a tradução é determinística e vive no adapter, então o replay
  não chama o especialista mas reproduz o comportamento: provenance sempre do
  run atual; sem handoff, as facts upstream gravadas são descartadas (senão a
  gravação vazaria provenance de outro run e o check `handoff-provenance`
  falharia — detectado em teste).
- **Verificação:** novo check `handoff-provenance` em `verification.py` — todo
  `derived_from` deve nomear um item do handoff entregue (provider, run, item,
  node/plan_run) e não pode elevar o status epistêmico do item de origem.
- **Testes adicionados:** adapter — manifest declaração, tradução/bounds/
  determinismo/malformado, evidência derivada, sem-provenance pulada, argv
  `--upstream` + cleanup, limitação sem intake, 2 de replay (handoff atual /
  drop sem handoff); core — 4 de `handoff-provenance` em `test_verification.py`;
  replay cross — consumo real com provenance + `handoff-provenance: passed`;
  live cross — provenance **exata** (run/plan ids do run corrente) + epistemic
  verbatim + **A/B obrigatório**: o `execute` do n2 reconstruído do `context`+
  `handoff` persistidos roda duas vezes no adapter real — com handoff produz
  evidência `upstream:` derivada e facts upstream no caso; sem handoff, nenhuma.
- **Live local provado:** plan cross real → n2 com 16 evidências derivadas,
  `derived_from` → `spark-forge`/n1/run-n1/plan correto, `handoff-provenance:
  passed (16 derived evidence)`, sem `handoff-use-undeclared`; A/B com diferença
  observável (evidence count e `facts.json` persistido).
- **Resultados:** o handoff deixou de ser envelope ignorado — é insumo semântico
  do especialista com provenance verificável, epistemic preservado e replay
  compatível.
- **Limitações:** provenance em replay vive na requisição (a gravação não carrega
  provenance do run original — decisão correta, registrada nos testes); intake
  limitado a 32 itens/64 KiB por enquanto; só `api.analyze` consome.
- **Dívida criada:** `test_onboarding_flow` e 2 testes de contexto dependem do
  tmp do pytest estar dentro de um git toplevel limpo (o addopts já fixa
  `--basetemp=.pytest_tmp` dentro do repo — fora dele `read_git_state` emite
  `git: not a repository` e `git:changed` em sinais); fragilidade do harness,
  classificar na Wave H. O intake do especialista vive na branch
  `feat/upstream-facts` do irmão até merge — worktree `.sibling-f/api-forge`.

## Wave G — API Forge execute recorder

**Status:** implementado; commit pendente.

- **Gap encontrado:** as gravações de execute do API Forge eram montadas à mão
  (`"provenance": "hand-built"`) — frágeis a drift do formato de caso e sem
  provenance mecânica.
- **Implementado:** `theforge_apiforge.record_execute`
  (`adapters/apiforge/src/theforge_apiforge/record_execute.py`), equivalente
  conceitual ao do Spark: copia o workspace sem links para `stage/` num
  temporário (o original nunca é escrito), valida `--arg NAME=PATH` contra os
  inputs do verbo, monta o argv por `invocation()` — o mesmo do execute real —,
  roda a CLI pública com `APIFORGE_CACHE=off`, normaliza `--out-dir` absoluto a
  `<cwd>/...`, captura o `case_files` completo, recusa gravação com caminho de
  máquina e serializa canonicamente. `--handoff FILE` alimenta o intake
  `--upstream` pelo mesmo `translate_handoff` do adapter. Falha nativa grava
  `{exit_code, stderr}` em `<cap>.<act>.error.json`. Roda no interpretador do
  especialista (`live_environment_problem` primeiro).
- **Testes adicionados (offline):** round-trip live→record→replay com equivalência
  semântica (evidence/findings/artifacts iguais ao replay da gravação de origem),
  workspace intacto (hash antes/depois), recusa de caminho de máquina, error
  recording, intake `--upstream`, recusa de capability sem intake, validação de
  inputs (unknown/missing/fora-do-workspace/ação inexistente).
- **Teste live:** `test_cross_forge_real.py` regrava `api.analyze` no workspace
  cross montado com o `handoff.json` persistido do n2 e compara top-level keys e
  formatos de id com a gravação do cenário — a mesma disciplina de drift já usada
  para o lado Spark.
- **Resultados:** o ciclo live→record→replay do API Forge é fechado por máquina,
  não por transcrição manual; `provenance: "recorded"` substitui `"hand-built"`
  nas gravações futuras.
- **Limitações:** o gravador roda no interpretador do especialista (Python 3.12 +
  apiforge); gravações existentes seguem `hand-built` até a primeira regravação
  (o teste live já prova a equivalência de shape); `--handoff` só vale para
  capabilities com intake.
- **Dívida criada:** nenhuma nova — remove a dívida "API recording hand-built".
