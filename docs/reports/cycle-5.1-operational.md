# Cycle 5.1 — fechamento operacional (§55–§63, §76–§88)

Auditoria executada na branch `devin/cycle5-final` sobre a `main` real.
Resultados medidos, não assumidos.

## §55 — auditoria de realidade da documentação

Varredura de `README`, `docs/`, ADRs, contratos, schemas, exemplos e release
notes por linguagem que supera a prova (`implemented` onde só há foundation,
`secure`/`production safe`/`guaranteed` sem delimitação).

**Achados e correções aplicadas nesta wave:**

- `README.md` marcava `Cycle 5: COMPLETE`, `Cycle 4: COMPLETE`,
  `Cycle 4.1: IN PROGRESS`, `Cycle 3.1: PARTIAL` — taxonomia imprecisa enquanto
  a CI remota está bloqueada. Normalizado para `CLOSED_LOCALLY /
  REMOTE_VALIDATION_BLOCKED` (§56). `Cycle 3: CLOSED` permanece: foi fechado
  quando a CI remota ainda rodava.
- `test_release_metadata.py` reforçado: o gate agora exige a taxonomia precisa
  e rejeita `COMPLETE`/`CLOSED` nu para ciclos bloqueados.
- Nenhuma ocorrência de `production safe`, `fully trusted`, `guaranteed` ou
  `secure` sem delimitação em docs/ e README (§87 limpo).
- Nenhum ADR encontrado descrevendo decisão posteriormente alterada; a
  convenção `superseded` está documentada no índice (`docs/adr/README.md`) e
  ADR 0032 (interop) não pinava versão de A2A — continua correto após o
  refresh para `a2a/1.0` (§63).

## §56 — status histórico normalizado

Taxonomia adotada (já usada nos relatórios de ciclo, agora uniforme no README):

```text
IMPLEMENTATION COMPLETE   — código e docs entregues
LOCAL_GATES_GREEN         — suíte offline + gates locais verdes
CLOSED_LOCALLY            — fechado no que é validável sem CI remota
REMOTE_VALIDATION_BLOCKED — fechamento formal aguarda Actions (quota)
```

Regra: um ciclo só vira `CLOSED` quando a CI remota passar em `main`. Nenhum
ciclo dependente de prova remota foi fechado artificialmente.

## §57 — remote CI

```text
status:        REMOTE_BLOCKED
reason:        GitHub Actions quota esgotada na conta (decisão do owner)
run id:        n/a — jobs sobem sem steps (observado no merge de ciclos anteriores)
jobs created:  workflows prontos em .github/workflows (ci.yml, ecosystem-real.yml)
steps:         não executados
```

Nenhum resultado foi falsificado para contornar o bloqueio.

## §58 — reprodutibilidade offline

Suíte principal executável sem network/LLM/registry remoto/SaaS:

- `pytest` (addopts exclui `slow` e `real_provider`) — 100% verde
- `scripts/bench/run_bench.py` e `run_scenarios.py` — stdlib-only, workspaces
  sintéticos determinísticos
- `scripts/reality/collect.py` — coleta local por venvs; sem rede
- session-level network block em `conftest.py` garante que nenhum teste offline
  vaze para a rede (`allow_network` só por marker explícito)

## §59 — package build

Gate `pytest -m slow` executado nesta branch (4/4 verde):

```text
test_ci_gates_pass_on_built_wheel                     ok
test_built_wheel_excludes_adapters_and_has_no_runtime_dependency  ok
test_built_sdist_excludes_adapters_and_has_no_runtime_dependency  ok
test_ci_gates_fail_on_artificial_runtime_dependency   ok (rejeita dep injetada)
```

Cobre sdist+wheel, exclusão dos adapters, zero dependências de runtime e o
gate de fresh-install metadata.

## §60 — CLI freeze review

| Eixo | Estado |
|---|---|
| naming | kebab/verb-noun consistente; `forge` é alias documentado de `theforge` |
| flags | `--json` universal; `--approve`/`--target`/`--allow-unverified` uniformes em `ask`/`plan` |
| exit codes | conjunto fechado `{0,1,2,3,4,5,6,70,130}` documentado em `docs/cli.md` |
| JSON output | `cmd_render`/`render.py` centraliza; todo comando novo (`targets`, `remote`, `memory`) emite JSON e texto |
| error taxonomy | prefixos `theforge: error:`/`persistence error:`/`internal error:`/`integrity divergence:` canônicos |
| deprecated | capability deprecation é `deprecated`/`replaced_by` no manifest — nenhum comando CLI deprecated neste ciclo |

Exit codes distinguem: `0` success · `3` validation/ambiguous/no_route · `4`
policy denial/refused · `1/5/6/70` runtime+integrity · `2` uso inválido ·
`130` interrupção (§82 satisfeito: automação diferencia sucesso, validação,
policy, runtime e dependência bloqueada).

## §61 — contract freeze review

Classificação documentada em [versioning.md § Estabilidade de contratos](../versioning.md):
23 stable candidates OPEN + 5 experimental (Cycle 5: `SemanticPlanProposal`,
`ExecutionTarget`, `TargetRequirement`, `RemoteExecutionRequest`,
`RemoteExecutionReceipt`) + 39 internal (`CLOSED_SCHEMAS`). Nenhum esquema de
versionamento novo criado — a regra de campo opcional existente basta.

## §62 — schema parity

`python -m theforge.contracts.schema schemas` → `git diff` limpo: 67 contratos
↔ 67 schemas, 1:1, sem órfãos (gate contínuo em `test_docs_consistency.py`).

## §76 — tech debt classification

```text
src/theforge/scaffold.py:67   "TODO: real work"            → safe debt (template de scaffold gerado — placeholder intencional)
src/theforge/scaffold.py:140  "TODO: what this capability" → safe debt (mesma razão)
```

Nenhum `FIXME`/`XXX`/`HACK` no core. Os dois TODOs são texto de scaffold
emitido para projetos novos — não débito do runtime.

## §77 — dead code

- Nenhum modelo/contrato exportado sem uso: todos os 67 `EXPORTED` têm schema
  gerado e consumidor (validação `test_contracts_*` + runtime).
- `CounterfactualPlanComparison` é contrato sem runtime — **FOUNDATION_ONLY**
  declarado ([security report](cycle-5.1-security.md)), não removido: é
  surface de API com schema publicado.
- Nenhum feature flag morto identificado; adapters obsoletos: nenhum.

## §78–§80 — determinismo e identidade

- Schemas regenerados de forma determinística (diff limpo, ordem estável).
- `test_federation_conformance.py::test_graph_build_is_deterministic` — grafo
  idêntico entre builds.
- `memory_entry_id` content-derived (claim+scope+subject+kind+producer) —
  reafirmação dedupe, rerun não infla ids; coberto em `test_memory.py` +
  `test_memory_roi.py`.
- Plan/receipt identity: `sha256_of` canônico sobre o contrato; `receipt`
  grava `simulation_sha256`, `complexity_sha256` etc. — rerun com o mesmo
  input produz os mesmos hashes.

## §81 — failure taxonomy

Taxonomia canônica em `docs/errors.md` + `errors.py`: `FORGE-<área>-<código>`
com famílias distintas — validação (`FORGE-PLAN-*`, `FORGE-CONTRACT-*`),
indisponibilidade (`FORGE-PROTO-*`), policy (`FORGE-POLICY-DENIED`,
`FORGE-POLICY-APPROVAL-REQUIRED`), persistência (`FORGE-PERSIST-*`), execução
(`FORGE-EXEC-*`), novidade do ciclo (`FORGE-PLAN-GLOBAL-STOP`). Semânticas não
colapsam: cada família tem exit code e renderer próprios.

## §83–§84 — observability & incident replay

- Reconstrução de run: receipt liga `plan_sha256`, `simulation_sha256`,
  `complexity_sha256`, evidence refs, verification, observation, trace
  (`correlation_id`/`parent_run` no RunTelemetry).
- Incident replay: `theforge replay --mode render|verify` reanálisa um run
  histórico **sem executar providers** — provado por
  `test_replay.py::test_render_reads_only_the_run_never_the_workspace_nor_providers`
  e os 17 testes do arquivo (divergência de hash/contexto, refusals de
  reprodutibilidade, runs encadeados).

## §85–§86 — trust & authority boundaries

- Trust boundaries: [security report §30](cycle-5.1-security.md) + diagramas em
  `docs/architecture.md` — core / especialistas locais / externos / A2A /
  remote target / MCP / memory export-import, cada um com tier de prova.
- Authority boundaries (documentadas nos ADRs 0044/0049/0051 e reafirmadas):
  semantic planner = *proposta* · validator = *validade* · StrategyPolicy =
  *preferência* (só pós-gates) · hard gates = *compatibilidade* · remote
  provider = *execução* · Forge = *aceitação* · memory = *advisory, nunca
  truth authority*.

## §87–§88 — claims discipline

- Nenhuma afirmação de `secure`/`verified` sem escopo (verificado por varredura).
- Compatibilidade com especialistas sempre carrega SHA + janela de versão +
  surface fingerprint + timestamp — vide
  [cycle-5.1-audit.md](cycle-5.1-audit.md) e o reality manifest
  (`scripts/reality/collect.py`).
