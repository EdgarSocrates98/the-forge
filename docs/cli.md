# CLI

`theforge` é o nome canônico da CLI e o usado em todos os exemplos; `forge` é um alias de conveniência ([ADR 0008](adr/0008-cli-name.md)). Todo subcomando aceita `--root <dir>` (padrão: diretório atual), `--json` e `--debug` ([mensagens de erro](#mensagens-de-erro-e---debug)), sempre **depois** do subcomando final: `theforge registry list --json`, `theforge init --root X`. Colocá-los antes (`theforge --root X init`) não funciona.

| Comando | Faz | Exit |
|---|---|---|
| `init` | cria `.forge/` (idempotente); remove o cache legado `.forge/registry` com aviso | 0 |
| `doctor` | OS, Python, git, host, workspace, providers | 0 / 1 só se algum check for `fail` (Python < 3.11, `.forge` sem escrita, provider builtin não saudável, `providers.toml` inválido); provider não builtin não saudável e workspace não inicializado são `warn` (exit 0) |
| `status` | resumo do workspace, incluindo os providers com cache | 0 |
| `registry list` | providers (usa o cache do usuário) | 0 |
| `registry refresh` | re-`describe` de todos os providers; remove o cache legado `.forge/registry` com aviso | 0 |
| `registry show <id>` | manifest, argv e hash | 0 / 2 se desconhecido |
| `capabilities list [--provider id]` | capabilities declaradas, com aliases, depreciação (`replaced_by`) e `declared_by`; aviso em stderr para cada depreciada | 0 |
| `capabilities search <q>` | busca em id, aliases, descrição e keywords | 0 |
| `providers health` | health de cada provider | 0 / 1 |
| `ask "<texto>" [--capability id] [--action a] [--profile auto\|economy\|balanced\|max] [--target path]... [--allow-unverified] [--approve CAPABILITY]...` | roteia, avalia a policy e executa | 0 / 2 / 3 / 4 / 5 |
| `plan "<texto>" [--profile auto\|economy\|balanced\|max] [--target path]... [--from FILE] [--execute] [--allow-unverified] [--approve CAPABILITY]...` | monta (e, com `--execute`, executa) um plano multi-provider ([`plan`](#plan)) | 0 / 2 / 3 / 4 / 5 |

`--profile` default `auto`: depois do routing, o complexity engine mede a tarefa (repositórios, risco declarado, ambiguidade, impacto) e escolhe o perfil efetivo — gravado no artefato `complexity` (`ComplexityAssessment/v1`) e linkado no receipt por `complexity_sha256`; `explain` mostra `auto-><resolvido>`. O prompt nunca é entrada. Perfis explícitos mantêm a semântica de sempre; só gravam `complexity` quando a avaliação medida promove os limites elásticos um degrau (a evidência da promoção).
| `workspace show` | descreve repositórios, git, tecnologias e relações usando só o cache do registry ([`workspace show`](#workspace-show)) | 0 |
| `explain <run_id>` | relatório versionado de um run ou plano, com verificação de hashes ([`explain`](#explain)) | 0 / 2 / 6 |
| `replay <run_id> --mode render\|verify\|execute [--allow-unverified] [--approve CAPABILITY]...` | reapresenta, reverifica ou reexecuta um run ([`replay`](#replay)) | render/verify: 0 / 2 / 6; execute: 0 / 2 / 3 / 4 / 5 |
| `resume <run_id> [--allow-unverified] [--approve CAPABILITY]...` | continua um run de plano reutilizando os nós provadamente intactos ([`resume`](#resume)) | 0 / 2 / 3 / 4 / 5 |
| `decisions` | a memória de decisões reutilizáveis do projeto (`.forge/intel/decisions.json`): routing, profile, pattern e veredictos de debate com sua `basis` e trilha de runs | 0 |

## Exit codes gerais

| Código | Significado |
|---|---|
| 0 | sucesso: `ok` / `partial` em `ask` e `plan`, `planned` em `plan` sem `--execute`, `explain`/`replay` sem divergência |
| 1 | `doctor` / `providers health` com falha |
| 2 | uso inválido (inclusive arquivo de plano ilegível, `FORGE-PLAN-FILE`, e run id malformado ou desconhecido) ou workspace não inicializado |
| 3 | `no_route` / `ambiguous` |
| 4 | `provider_failure` / `refused` (inclusive recusa de policy, plano rejeitado e `replay --mode execute` recusado) |
| 5 | falha ao gravar ou ler o run (`theforge: persistence error:`) |
| 6 | divergência de integridade: `explain`, `replay --mode verify` e `replay --mode render` |
| 70 | erro interno inesperado (sem traceback) |
| 130 | interrompido (Ctrl+C) |

Não existe outro exit: os valores por desfecho (`ok`, `partial`, `planned` → 0; `ambiguous`, `no_route` → 3; `refused`, `provider_failure` → 4) mais os fixos {1, 2, 5, 6, 70, 130}.

## Mensagens de erro e `--debug`
Todo erro sai em stderr com um prefixo fixo e termina com `[<código> · <família>]` ([errors.md](errors.md)):

```
theforge: error: unknown run 20261004T120000Z-0a1b2c3d [FORGE-USAGE · usage]
theforge: persistence error: <detalhe> [FORGE-PERSIST-WRITE · persistence]
theforge: internal error: <TipoDaExceção>: <mensagem> [FORGE-INTERNAL · internal]
theforge: interrupted
theforge: integrity divergence: 1 artifact(s) diverge [FORGE-PERSIST-DIVERGENCE · persistence]
```

- Prefixos: `theforge: error:` (uso inválido, exit 2; recusa de `replay`, exit 4), `theforge: persistence error:` (exit 5), `theforge: internal error:` (exit 70), `theforge: interrupted` (exit 130, sem sufixo) e `theforge: integrity divergence: <n> artifact(s) diverge` (exit 6, em `explain` e `replay --mode render`/`verify`; a saída em stdout, texto ou `--json`, continua listando cada divergência e não muda).
- Nas saídas de `ask` e `plan`, a linha `Error:` traz o mesmo sufixo; `--json` traz `error` e `error_family`. Um código nativo de provider (`AF-*`, `SPARKFORGE-*`, …) não tem família e aparece como `[<código> · provider code]`.
- Nunca há traceback, nem em erro interno: em texto e em `--json`, um traceback dentro de um detalhe (por exemplo, o fim do stderr de um provider) vira `[traceback omitted] <última linha>`.
- `--debug` (aceito por todo subcomando) imprime, depois da mensagem de um erro de uso, de persistência ou interno, e depois da saída de um run de `ask` ou `plan` que terminou em erro interno, o diagnóstico redigido em linhas `theforge: debug:` (`stage=… code=… family=…`, `error: <tipo>: <mensagem>`, `cause: …`, `frame: <módulo>:<função>:<linha>`, só módulos `theforge.*`). Em `ask` e `plan`, um erro interno do run também grava o artefato `diagnostic` do run, só com `--debug`. Detalhes em [security.md](security.md#diagnóstico-de-debug).

## Trust e `--allow-unverified`
Providers de projeto são sempre `unverified`: um `trust` maior em `.forge/config/providers.toml` é rebaixado com aviso. Sem `--allow-unverified`, eles aparecem como `untrusted` no registry e não são executados. Com a flag, entram no routing, mas `local_mutation` continua pedindo aprovação. Semântica completa dos níveis em [security.md](security.md#níveis-de-trust) e [ADR 0010](adr/0010-policy-model.md).

## Aprovação (`--approve`)
Antes de executar, `ask` avalia a policy do `operation_class` declarado pela capability selecionada:

- `allow`: executa.
- `ask` sem aprovação: não executa; sai com exit 4, código `FORGE-POLICY-APPROVAL-REQUIRED` e `Unlock: --approve <capability>`. Repita o comando com `--approve <capability>` para executar; o run registra `approved: yes`.
- `deny`: não executa; exit 4 com `FORGE-POLICY-DENIED`. `--approve` não desbloqueia (por padrão, `destructive` é sempre `deny`).

`--approve` é repetível e vale só para a capability nomeada. Em `plan --execute`, libera só os nós que usam aquela capability. As regras padrão e os arquivos `policy.toml` estão em [security.md](security.md#policy-e-risco).

## `explain`
Além de task, candidatos (cada um com sinais, `rank` e `state`: `supported`, `heuristic` ou `unresolved`), seleção, confiança e fallbacks, `explain` mostra o artefato `risk`:

```
Risk:        local_mutation (source: provider_declaration)
Policy:      allow   rule: default.local_mutation.local   approved: yes
Dimensions:  read_only=no local_mutation=yes external_read=no external_mutation=no destructive=no credentials=unknown cross_account=unknown
```

Quando a decisão foi `ask` sem aprovação, a linha `Policy` termina com `unlock: --approve <capability>`. Runs sem artefato `risk` (anteriores ao ciclo 2, ou que pararam antes de selecionar um provider) mostram `Risk:        not recorded`.

### Contexto e telemetria
Quando o run tem `ContextPack`, `explain` mostra as seções abaixo, nesta ordem (exemplo de um run `--profile max` com uma rodada de negociação):

```
Context:     1 files, 10/1048576 bytes (complete); excluded 2
Tiers:       effective: metadata, reference, requested   bytes: metadata=0 reference=10 requested=0
Items:       reference pyproject.toml  signals: dependency_manifest
Excluded:    .env (secret)
             ghost.txt (missing)
Unmatched:   unmatched (no_signal): 1
Git:         main@22abb691044e dirty changed=2
Rounds:      r1: 2 files, 81/1048576 bytes (complete); excluded 2
                 requested req.txt  signals: requested
Drift:       none
Telemetry:   profile=max scan=4ms routing=9ms context=27ms provider=223ms files=2/2 cache=0/2 context_bytes=81 providers=1 fallbacks=0 rounds=1 verification=strong
```

- `Tiers`: tiers efetivos (perfil ∩ declaração da capability, lidos da telemetria; sem telemetria, as chaves de `tier_bytes`) e bytes por tier.
- `Items`: um item por linha, `tier path[:início-fim]  signals: ...`. `Excluded`: `path (motivo)`. `Unmatched`: agregado de arquivos sem sinal.
- `Git`: `branch@head dirty|clean changed=N` (+ estados como `merge`), ou `unavailable (<limitação>)` quando o git não pôde ser lido.
- `Rounds`: um bloco por artefato `context-r1`/`context-r2` com os itens `requested` e as exclusões novas; `none` sem negociação.
- `Drift`: caminhos com divergência de contexto (da telemetria; em runs sem telemetria, das limitações `context-drift:` do receipt).
- `Telemetry`: uma linha com durações por fase, arquivos selecionados/varridos, cache hits/misses, providers executados, fallbacks, rodadas e o nível de verificação. Métrica não medida aparece como `unknown` (e `~N` quando estimada).

Runs anteriores a esses artefatos continuam legíveis: campos ausentes aparecem como `not recorded`/`unknown`, e `Telemetry:   not recorded` quando não há telemetria.

Estas seções são um contrato de saída de texto: `explain` as monta sobre os artefatos crus do `ExplainReport` com o mesmo formato (`render.EXPLAIN_CONTEXT_SECTIONS` e os testes de `tests/test_cli.py` que as verificam), assim como as notas de routing `capability-alias`, `capability-deprecated` e `capability-overlap`.

### Verificação, reprodutibilidade, plano e integridade
Depois das seções acima, `explain` acrescenta:

```
Provider:    echo-forge 0.1.0 (trust: builtin)
Evidence:    1 (confirmed=1)   duration=368ms
Verification: self_report=reported provider_evidence=reported forge=passed independent=not_performed
Reproducibility: reproducible (all reproducibility conditions met)
Integrity:   ok (7 checked)
Not recorded: none
```

- `Provider` (com a versão observada quando difere da declarada), `Evidence` (contagem por status epistêmico e duração), `Verification` (os quatro níveis; detalhes de uma checagem `failed` em linhas abaixo) e `Reproducibility` (nível e motivos; `unknown` com `not recorded` em runs anteriores a esta versão).
- `Plan run: <id> (node <nó>)` num run de nó, `Replay of: <id>` num run criado por `replay --mode execute` e `Resumed from: <id>` num run criado por `resume`; nós reutilizados pelo resume aparecem como `(reused)` e retentativas como `xN attempts`.
- Num run de plano: `Plan` (status, padrão, origem e perfil), `Nodes` (um por linha: provider, capability e ação, dependências com status epistêmico, regra e evidência, desfecho, run e `blocked_by`), `Violations`, `Handoffs` (origem → destino, itens, truncado), `Synthesis`, `Failures`, `Plan result` (status, ordem efetiva, reprodutibilidade combinada), `Workspace` (repositórios, tecnologias, relações) e `Install` (itens do plano de instalação).
- `Error family` quando o run tem erro, `Limitations`, `Unknowns`, `Integrity` e `Not recorded` (seções esperadas sem dado gravado).
- `Integrity`: `ok (N checked[, M unrecorded])` ou `N divergence(s)` seguido de uma linha `<tipo> <artefato>` por divergência (`modified`, `missing` ou `unreadable`; `work/<path>` para um artifact do provider, `<run>/<artefato>` para um run de nó). Com divergência o exit é 6 e o stderr traz uma linha `theforge: integrity divergence: <n> artifact(s) diverge [FORGE-PERSIST-DIVERGENCE · persistence]`; o que é conferido está em [security.md](security.md#integridade-de-runs-e-âncora-de-confiança).

Exits: 0 sem divergência, 2 para run id malformado ou desconhecido, 6 com divergência. `explain` só lê o run: nunca escreve nele nem inicia providers.

### `explain --json` (`ExplainReport` v1)
`--json` emite um `ExplainReport` (`schema = "theforge/ExplainReport/v1"`, JSON Schema publicado em `schemas/ExplainReport.schema.json`):

| Chave | Conteúdo |
|---|---|
| `schema`, `producer`, `created_at`, `run_id`, `kind` (`run` ou `plan`), `status` | identificação; `status` é o do receipt (`null` se não gravado) |
| `intent`, `targets`, `profile` | da tarefa |
| `routing` | status, padrão, motivo, confiança, sinais, candidatos, seleção, fallbacks e `notes` (notas de routing da Wave B) |
| `context` | budget, bytes usados, arquivos, excluídos, tiers, rodadas, `unmatched`, `git`, `drift` |
| `provider`, `result`, `risk`, `telemetry`, `verification`, `reproducibility` | provider e versão; findings, evidências por status epistêmico, duração; os artefatos `risk` e `telemetry` crus; `VerificationResult`; nível e motivos (`unknown` quando não gravado) |
| `plan` | só em runs de plano: `plan`, `result` (`PlanResult`), `workspace_descriptor`, `installation` |
| `parent_run`, `replay_of`, `error`, `error_family` | vínculos e erro com família |
| `integrity` | `checked`, `divergences` (`artifact`, `kind`, `expected`, `actual`) e `unrecorded` |
| `limitations`, `unknowns`, `not_recorded` | do receipt; seções sem dado gravado |
| `artifacts` | os artefatos crus (redigidos) do run por nome: `artifacts.task`, `artifacts.context`, `artifacts["context-r1"]`, `artifacts.telemetry`, … |

- Em `artifacts`, só aparecem os artefatos presentes e legíveis: um artefato ausente é omitido (não vira `null`), e um ilegível também é omitido, listado em `not_recorded` e anotado como limitação `explain-unreadable: <nome>`. Antes desta versão, `--json` emitia os artefatos no nível de cima e sempre com `context-r1`, `context-r2` e `telemetry` (`null` quando ausentes); automações devem ler `artifacts.<nome>`.
- **Evolução aditiva.** Dentro de `ExplainReport/v1` só entram campos novos opcionais, com default; remover um campo ou mudar seu tipo exige `ExplainReport/v2`. Automações devem ignorar campos que não conhecem.

## `plan`
`theforge plan "<texto>"` monta um plano multi-provider: um nó por especialista, executado localmente ([architecture.md](architecture.md#fluxo-de-plan), [ADR 0018](adr/0018-multi-provider-execution.md)).

```
$ theforge plan "Projete um pipeline Spark que produza dados para uma API" --profile max
Run <run_id>: planned
Plan:        validated  pattern: pipeline  source: decomposed  profile: max
Nodes:       n1 spark-forge pyspark.static-analysis:pyspark
             n2 api-forge api.analyze:analyze  after n1 (inferred, intent-order: …)
Install:     none
Execute:     nothing was executed; re-run with --execute
Explain:     theforge explain <run_id>
```

- **Sem `--execute`** (padrão): descreve o workspace, decompõe ou lê o plano, valida, pede a [estimativa `plan`](protocol.md#operação-plan) aos providers que a declaram, confere health e grava tudo; nenhum nó executa e o desfecho é `planned` (exit 0).
- **`--execute`**: executa os nós na ordem topológica, cada um como um run próprio com o provider fixado, e mostra o desfecho de cada nó (`-> ok run=<id>`, `-> skipped blocked_by=<nó>`), `Handoffs`, `Synthesis`, `Failures` e `Plan result`. Desfechos: `ok`, `partial`, `refused`, `provider_failure`.
- **Padrões.** `route` (um nó) e `pipeline` rodam sequencialmente; `delegate`, `parallel` e `debate` executam os nós independentes de cada nível em concorrência limitada (4), com a ordem gravada sempre topológica. `delegate` só aceita subtarefas independentes (sem `depends_on`/`inputs` entre especialistas); `debate` exige ≥2 `proposer` e 1 `referee` dependente de todos, e grava o artefato `decision` (`DecisionRecord/v1`: `question`, `options`, `evidence`, `tradeoffs`, `chosen`, `rejected`, `rationale`, `confidence`, `unknowns`) — `chosen="unresolved"` quando o referee não declara `evidence id="decision"` com a claim de um proposer. A decomposição só emite `route`/`pipeline`; os demais padrões entram por `--from FILE` ou por proposta semântica validada.
- **Ordem dos nós.** Sem `--from`, a ordem segue primeiro as relações declaradas no grafo de capabilities (regra `capability-graph`: `requires` e produces→consumes entre os qualificados) e só depois a ordem textual das keywords casadas (regra `intent-order`): ambos são proxies do fluxo de dados e podem inferir a dependência errada ("uma API que consome os dados do pipeline Spark" põe a API primeiro). Revise o plano sem `--execute` antes de executar.
- **Planner semântico.** Quando a decomposição fica `ambiguous` e o profile não é `economy`, um provider com capability `proposes_plans` pode propor um `SemanticPlanProposal` que o core valida como qualquer plano (`source: semantic` na saída). Sem planner declarado, ou com proposta inválida, o desfecho fica `ambiguous` com a limitação correspondente.
- **`--from FILE`**: lê um `ExecutionPlan` em JSON (até 1 MiB, leitura estrita) e fixa a ordem e as dependências explicitamente. Os campos controlados pelo run (`plan_run`, `producer`, `created_at`, `status`, `violations`, `source`, `task_id`) são substituídos, e o `--profile` da linha de comando prevalece sobre o do arquivo (com limitação). Capability dada por alias vira o ID canônico com a nota `capability-alias`. Arquivo ilegível ou fora do contrato é erro de uso `FORGE-PLAN-FILE` (exit 2); um plano que não passa na validação termina `refused` com o primeiro código `FORGE-PLAN-*` (exit 4), sem executar nenhum nó.

  ```json
  {"task_id": "x", "pattern": "pipeline", "profile": "max", "nodes": [
    {"id": "n1", "role": "producer", "provider": "spark-forge",
     "capability": "pyspark.static-analysis", "action": "pyspark"},
    {"id": "n2", "role": "consumer", "provider": "api-forge",
     "capability": "api.analyze", "action": "analyze",
     "depends_on": [{"node": "n1", "epistemic": "explicit", "evidence": "plan file"}],
     "inputs": ["n1"]}]}
  ```
- **Perfil.** Só `max` permite mais de um provider (até 4). Em `economy` e `balanced` uma tarefa que precisaria de vários providers usa a decisão de routing de um provider: um nó `route` quando ela seleciona um, senão `ambiguous`/`no_route` (exit 3); havendo vários providers qualificados, o run registra a limitação `multi-provider decomposition not allowed by profile`. Limite de 8 nós por plano.
- Provider referenciado ausente, inválido, incompatível ou indisponível aparece em `Install:` (plano de instalação somente de planejamento: nada é baixado nem executado).
- `--approve`, `--allow-unverified` e `--target` têm o mesmo sentido de `ask`. `--json` emite `run_id`, `status`, `plan`, `result` (`PlanResult`), `installation`, `error` e `error_family`.

## `workspace show`
Descreve o workspace sem iniciar nenhum processo de provider: repositórios (raiz e subdiretórios até 3 níveis, sem seguir symlinks), o resumo git de cada um, tecnologias com o arquivo de evidência, relações (`contains` observada e `depends_on` declarada em `.forge/config/workspace.toml`), limitações e incógnitas. Usa só os manifests do cache do registry; um provider configurado sem cache vira a limitação `provider <id>: no cached manifest, its signals were not used` (rode `theforge registry refresh`). `--json` emite o `WorkspaceDescriptor` redigido. Exit 0.

```toml
# .forge/config/workspace.toml (opcional, committable)
[[relations]]
source = "orders-api"
target = "data-pipeline"
kind = "depends_on"
```

Só `depends_on` entre dois repositórios descobertos é aceito; uma entrada inválida é ignorada com aviso `FORGE-WORKSPACE-CONFIG`.

## `replay`
`theforge replay <run_id> --mode render|verify|execute` ([ADR 0019](adr/0019-error-taxonomy-and-reproducibility.md)):

| Modo | Faz | Exit |
|---|---|---|
| `render` | reapresenta o relatório do `explain` só a partir dos artefatos gravados, sem iniciar providers e sem ler o workspace | 0, ou 6 com divergência de integridade |
| `verify` | recalcula os hashes do run e compara os itens de contexto registrados (inclusive dos runs de nó de um plano) com o workspace atual, sem iniciar providers nem escrever; mostra `Replay verify of <id>: N divergence(s)` e uma linha `<tipo> <artefato>` por divergência (`workspace/<path>` para um arquivo de contexto alterado) | 0 sem divergência, 6 com divergência (mais a linha `theforge: integrity divergence:` em stderr) |
| `execute` | executa um novo run com os parâmetros originais, o provider fixado e `replay_of` apontando o original (que não é alterado), e compara os resultados sem campos voláteis: `Comparison: same`, `different` ou `no-result` | o do desfecho do novo run (0 / 3 / 4); 4 se recusado |

`execute` é recusado antes de iniciar qualquer provider, com todos os motivos na mensagem (`theforge: error: replay refused: <motivo>; … [<código> · replay]`, exit 4):

- `FORGE-REPLAY-UNSUPPORTED`: run de plano ou run de nó de um plano.
- `FORGE-REPLAY-NOT-REPRODUCIBLE`: reprodutibilidade `non_reproducible` ou `unknown` (inclusive não gravada); entradas registradas (`task`, `routing`, `handoff`, contexto, receipt) divergentes dos hashes (`integrity: <artefato> <tipo>`); arquivo de contexto alterado no workspace; provider não registrado, sem descrição no cache, de versão diferente ou com fingerprint diferente.

`--json` emite `mode`, `run_id`, `report` (render), `divergences`, `new_run`, `comparison` e, em `execute`, `new_status`. `--approve` e `--allow-unverified` valem para a reexecução.

## `resume`

`theforge resume <run_id>` continua um run de plano sem repetir o que já está provado. O run original não é alterado: um run novo é criado com a mesma `task` e o mesmo `plan` (hashes byte-idênticos — a prova de que nada mudou) e `resumed_from` aponta o original no receipt, no `plan-state` e no `explain`.

- **Reuso (o nó inteiro é re-hidratado, marcado `reused`, `attempts=0`, mesmo run filho)**: só quando o `NodeOutcome` gravado era válido (`ok`/`partial`), a cadeia de hashes do run filho ainda verifica de ponta a ponta, a identidade do provider (fingerprint e hash do manifesto) é a mesma e o handoff que seria reconstruído hoje é byte-idêntico ao registrado (`inputs.handoff_sha256`) — o que também prova que os resultados de upstream são os mesmos artefatos.
- **Reexecução**: qualquer dúvida reexecuta o nó — outcome sem resultado válido, artefato divergente, provider alterado/ausente, handoff irreprodutível. O motivo vira limitação `resume: node <nó> re-executed (<motivo>)` e o plano um resumo `resume <id>: reused X of Y recorded node runs`.
- **Ponto de partida**: `plan-result` quando existe; num run interrompido no meio do plano, o último snapshot `plan-state` (os nós `succeeded` viram candidatos a reuso). Sem nenhum dos dois, todo nó reexecuta.
- **Revalidação**: o plano gravado é rechecado contra o registry atual — um provider que sumiu ou perdeu a capability recusa o resume (`FORGE-PLAN-*`, exit 4). Um run desconhecido ou sem `plan` é erro de uso (exit 2).
- **Retry**: `retry.toml` (usuário em `THEFORGE_CONFIG_DIR`, projeto em `.forge/config/`; o projeto vence por chave) habilita retentativa de falhas transitórias de protocolo: `[retry] max_attempts = 1..5`, `retryable_codes` (default `FORGE-PROTO-TIMEOUT`, `FORGE-PROTO-EXIT`), `backoff_seconds`/`backoff_cap_seconds` (exponencial determinístico, sem jitter). O default é `max_attempts = 1` — nunca retenta — e recusas/policy nunca retentam. `NodeOutcome.attempts` conta as tentativas; cada tentativa é um run filho com recibo próprio.

`--json` emite `run_id`, `status`, `resumed_from`, `plan`, `result` (com `reused`/`attempts` por nó), `installation`, `decision` e `error`/`error_family`.

## Variáveis de ambiente
| Variável | Efeito |
|---|---|
| `THEFORGE_CONFIG_DIR` | diretório de configuração do usuário (`providers.toml`, `policy.toml`, `complexity.toml`, `retry.toml`) |
| `THEFORGE_CACHE_DIR` | diretório de cache do usuário (cache do registry); ver [ADR 0009](adr/0009-registry-cache-location.md) |
