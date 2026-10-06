# Forge Protocol v1

## Invocação
`<argv do provider> <op>`. O request JSON entra pelo stdin e a response JSON sai pelo stdout, um documento cada.

- Exit 0 sempre que houver uma response de protocolo válida, inclusive `refused`.
- Exit ≠ 0, stdout que não é JSON, stdout acima de 8 MB ou timeout são falhas de transporte (`provider_failure`). Em timeout, oversize ou interrupção, o core encerra o provider **e toda a árvore de processos** que ele criou (limitações em [security.md](security.md#limitações-de-isolamento)).
- stderr é truncado em 64 KB e só sai do transporte redigido (os últimos 500 caracteres). stderr bruto nunca é persistido.
- O cwd é controlado pelo core: um diretório temporário por chamada em `describe` e `health`, e `.forge/runs/<id>/work` em `execute`. Nunca é o diretório do chamador, e não é sandbox.

## Ops
| Op | Obrigatória | Payload do request | Payload da response |
|---|---|---|---|
| `describe` | sim | `{}` | `ForgeManifest` |
| `health` | sim | `{}` | `HealthReport` (`ok\|degraded\|unavailable`) |
| `execute` | não | `ExecuteRequest{task, capability, action, context, handoff?}` | `ExecutionResult` |
| `plan` | não | `PlanRequest{task, capability, action}` | `PlanEstimate` |
| `verify` | não | `VerifyRequest{task, capability, action, run_id, result, handoff?}` | `VerifyVerdict` |
| `resolve` | não | `ResolveRequest{task, candidates, ambiguity, technologies}` | `RoutingProposal` |
| `estimate` | reservada | — | — |

O provider declara as ops que suporta em `describe.ops`. `plan` é chamada só em providers que a declaram ([Operação `plan`](#operação-plan)); `verify` é chamada só em providers que a declaram e que têm uma capability com `relations.can_verify` sobre a capability que executou ([Operação `verify`](#operação-verify), [ADR 0021](adr/0021-independent-verification.md)); `resolve` é chamada só em providers que a declaram e que têm uma capability com `resolves_ambiguity`, e só quando o routing determinístico terminou `ambiguous` ([Operação `resolve`](#operação-resolve), [ADR 0025](adr/0025-semantic-routing-fallback.md)); `estimate` continua reservada e o core nunca a envia ([ADR 0018](adr/0018-multi-provider-execution.md)). As capabilities de um provider que não declara `execute` não são roteáveis. A decisão de routing registra em `limitations` os providers excluídos por isso quando são relevantes: declaram a capability pedida com `--capability`, ou, no routing por sinais, nada foi roteado. Um pedido com `--capability` é recusado com `FORGE-PROTO-OP-UNSUPPORTED` (sem iniciar o processo de `execute`) quando um provider roteável declara a capability sem `execute` e nenhum outro poderia executá-la: nenhum declarante com `execute`, qualquer que seja o trust ou o estado, e nenhum provider não bloqueado de manifest desconhecido. Caso contrário fica o `no_route` comum: o provider que executaria está fora do routing por outro motivo (por exemplo `unverified` sem `--allow-unverified`, ou indisponível), e `theforge registry list` mostra trust e estado de cada um.

## Envelopes
```json
{"protocol":"forge/v1","kind":"Request","op":"execute","request_id":"r_…","payload":{}}
```
```json
{"protocol":"forge/v1","kind":"Response","op":"execute","request_id":"r_…",
 "producer":{"id":"my-forge","version":"1.0.0"},
 "status":"ok|partial|refused|error","payload":{},
 "error":{"code":"…","detail":"…","field":null,"unlock":null},
 "limitations":[],"unknowns":[]}
```
- `request_id` precisa ecoar o do request.
- `kind` precisa ser `Response`.
- `op` é opcional (compatível com providers do ciclo 1), mas, quando presente, precisa ser igual à op pedida. Os providers de referência sempre o emitem; novos providers devem emiti-lo.
- `error` é obrigatório quando o status é `refused` ou `error`.
- `producer.id` precisa ser o id registrado do provider e `producer.version` a `version` do manifest. O core confere o `producer` do envelope em toda op: em `describe` contra o manifest retornado, em `health`, `plan` e `execute` contra o manifest em uso. Em `execute`, o `ExecutionResult.producer` (id e versão) também é conferido.

O core valida a response em duas etapas.

1. Transporte (`SubprocessTransport.call`), para toda op:
   1. JSON (`FORGE-PROTO-NOT-JSON`).
   2. Envelope (`FORGE-PROTO-SCHEMA`): `kind`, `status`, campos obrigatórios. O payload não é validado aqui.
   3. `request_id` (`FORGE-PROTO-MISMATCH`).
   4. `op`, quando presente (`FORGE-PROTO-OP-MISMATCH`).
   5. Protocolo (`FORGE-PROTO-VERSION`), exceto em `describe`, que ainda não tem protocolo negociado.
2. Por quem chamou:
   - `describe`: status, schema do manifest, id do manifest igual à entrada e `producer` (`FORGE-PROTO-PRODUCER`). Qualquer falha deixa o provider `invalid` (o schema do manifest não gera código `FORGE-PROTO-*`). Depois vêm os [limites de manifest](#manifest) e a negociação.
   - `health`: `producer` (`FORGE-PROTO-PRODUCER`), status (o `error` do provider ou, sem ele, `FORGE-HEALTH-FAILED`) e schema do `HealthReport` (`FORGE-PROTO-SCHEMA`).
   - `execute`: `producer` do envelope (`FORGE-PROTO-PRODUCER`), status (`refused`/`error` repassam o `error` do provider), schema do `ExecutionResult` (`FORGE-PROTO-SCHEMA`) e [integridade](#integridade-do-resultado), começando pelo `producer` do resultado.
   - `plan`: `producer` (`FORGE-PROTO-PRODUCER`), status e schema do `PlanEstimate` (`FORGE-PROTO-SCHEMA`); qualquer falha vira limitação `FORGE-PLAN-ESTIMATE` no nó, nunca erro ([Operação `plan`](#operação-plan)).

## Versionamento
- `describe.protocols` lista as versões suportadas; o core escolhe o maior major em comum.
- Só entradas no formato `forge/v<N>` (N de 1 a 999, sem zero à esquerda) contam. Entradas malformadas são ignoradas, duplicadas contam uma vez, e a ordem não importa.
- Lista vazia: o manifest é inválido (`protocols must not be empty`) e o provider fica `invalid`.
- Lista não vazia sem major `forge/v<N>` válido em comum (inclusive só com entradas malformadas): o provider fica `incompatible` e sai do routing.
- Breaking change exige um novo major.
- Para qualquer op que não seja `describe`, o provider deve recusar requests com protocolo que não suporta.

## Campos desconhecidos
A tolerância depende de quem produziu o contrato:

| Origem | Contratos | Campo desconhecido |
|---|---|---|
| Provider | `Response`, `ForgeManifest`, `HealthReport`, `ExecutionResult`, `Evidence` | ignorado (forward-compat dentro do major) |
| Provider | `PlanEstimate` (payload da op `plan`) | ignorado |
| Core, ao reler o que gravou | artefatos do run (`task`, `workspace-descriptor`, `routing`, `plan`, `installation`, `risk`, `handoff`, `context`, `context-r1`, `context-r2`, `result`, `plan-state`, `plan-result`, `decision`, `graph`, `capability-graph`, `semantic-proposal`, `routing-proposal`, `verification`, `telemetry`, `diagnostic`, `complexity`, `budget`, `receipt`), o cache do registry, o cache de fingerprints de contexto, o histórico de performance (`.forge/metrics/provider-performance.json`) e a inteligência do projeto (`.forge/intel/`) | rejeitado em qualquer profundidade (`$.<caminho>: unknown field`) |

- O core persiste só os campos que conhece, então um `result` vindo de provider com campos extras é relido sem eles.
- Nos JSON Schemas de `schemas/`, `additionalProperties: false` aparece só nos contratos que nunca cruzam o protocolo: `RoutingDecision`, `ExecutionReceipt`, `RiskAssessment`, `RunTelemetry`, `ExecutionPlan`, `PlanResult`, `WorkspaceDescriptor`, `WorkspaceGraph`, `VerificationResult`, `InstallationPlan`, `ExplainReport`, `Diagnostic`, `ComplexityAssessment`, `CapabilityGraph`, `DecisionRecord`, `PlanState`, `RunBudget`, `ProviderPerformance`, `ProjectIntel` e `DecisionMemory`. `TaskSpec`, `ContextPack` e `Handoff` vão ao provider dentro de `ExecuteRequest` (e `TaskSpec` dentro de `PlanRequest` e de `ResolveRequest`) e continuam com schema aberto, assim como `PlanRequest`, `PlanEstimate`, `SemanticPlanProposal`, `VerifyRequest`, `VerifyVerdict`, `ResolveRequest` e `RoutingProposal`; a rigidez deles vem da releitura estrita.

## Integridade do resultado
Um `ExecutionResult` só é persistido se passar por todas as regras abaixo. Caso contrário, o run termina em `provider_failure` com o código da primeira violação, nenhum artefato `result` é gravado e o receipt é gravado mesmo assim.

- IDs de `evidence` únicos (`FORGE-RESULT-DUP-EVIDENCE`) e IDs de `findings` únicos (`FORGE-RESULT-DUP-FINDING`).
- Todo `finding.evidence_ids` aponta para uma evidence do mesmo resultado (`FORGE-RESULT-DANGLING-EVIDENCE`).
- `artifacts[].path` (`FORGE-RESULT-ARTIFACT-PATH`): caminho relativo POSIX, não vazio, sem `\`, sem `/` inicial, sem letra de drive (`C:`), sem segmento `..`, sem byte NUL e que nomeie algo abaixo da raiz (não só `.`). A checagem é léxica: o core nunca abre o caminho.
- A raiz de `artifacts[].path` é o cwd do `execute` (`.forge/runs/<id>/work/`): `native/full-output.json` nomeia `.forge/runs/<id>/work/native/full-output.json`. O `sha256` é calculado pelo provider sobre os bytes do arquivo. A integridade não abre o arquivo; depois dela, a [verificação](#verificação-do-resultado) recalcula o hash de cada artifact em `work/`.
- `created_at` em ISO-8601 UTC, com sufixo `Z` ou `+00:00` (`FORGE-PROTO-SCHEMA`).
- `producer` igual ao provider invocado, id e versão (`FORGE-PROTO-PRODUCER`).

### Formato de hash
Todo campo SHA-256 é exatamente 64 caracteres hexadecimais **minúsculos** (`^[0-9a-f]{64}$`): `Artifact.sha256`, `ContextFile.sha256`, `Evidence.hash` (quando presente) e os `*_sha256` do receipt. Hash maiúsculo, curto ou não hexadecimal invalida o contrato que o contém. O que `Evidence.hash` cobre está em [Revalidação de contexto](#revalidação-de-contexto-toctou).

### Verificação do resultado
Todo run que recebe um resultado válido grava o artefato `verification` (`theforge/VerificationResult/v1`), ligado ao receipt por `verification_sha256`. Ele separa quatro níveis, e o próprio contrato impede que o que o provider diz de si apareça como verificação aprovada:

| Nível | Status possíveis | Conteúdo |
|---|---|---|
| `self_report` | `reported`, `not_performed` | o status que o provider declarou na response |
| `provider_evidence` | `reported`, `not_performed` | as evidências do provider, contadas por status epistêmico |
| `forge` | `passed`, `failed`, `not_performed` | checagens que The Forge executa: integridade do resultado, `producer`, reverificação de contexto no nível do perfil (`minimal` não reverifica) e o sha256 de cada `artifacts[].path` recalculado em `work/` |
| `independent` | `passed`, `failed`, `not_performed` | veredicto da op `verify` de um provider de identidade distinta que declara `can_verify` sobre `<producer>/<capability>` — [Operação `verify`](#operação-verify) |

`forge` é `passed` só se todas as checagens executadas passarem. Um artifact ausente, fora da raiz ou com hash diferente do declarado reprova `forge`, gera a limitação `FORGE-RESULT-ARTIFACT-HASH: <path>` e o run termina `partial`, nunca `ok`. Um veredicto independente `failed` demove o run da mesma forma, com a limitação `independent verification failed: <verifier>`.

#### Operação `verify`
Depois das checagens determinísticas, o core procura um verificador independente: um provider `ready` cujo manifest declara a op `verify` e uma capability com `relations.can_verify` contendo `<producer>/<capability>` exatos do que executou. Independência é de **identidade**, não de capability: o produtor — mesmo id ou mesmo `argv` (o mesmo programa sob outro id) — nunca é seu próprio verificador, e candidatos `blocked`/`unverified` (sem `--allow-unverified`) são recusados; todos os descartes aparecem no `details` do check. O request é um `VerifyRequest` com a task, o `ExecutionResult` persistido (já redigido), o run_id e o handoff que o run recebeu — nada de arquivos do workspace.

O verificador responde `VerifyVerdict`: `passed` ou `failed` são veredictos sobre o resultado; `refused`/`error` no envelope, `producer` divergente, payload malformado ou falha de transporte viram `not_performed` — um verificador que não consegue julgar nunca é evidência contra o resultado. Com vários candidatos elegíveis o menor `id` vence (determinístico); sem nenhum, `not_performed` diz por quê. Regra epistêmica: um `passed` certifica que uma identidade independente verificou o resultado — evidência nova sobre a verificação, nunca sobre as afirmações; o `epistemic` da evidência do produtor não muda (subir exige evidência nova, como na regra de `Evidence.derived_from` do handoff).

#### Operação `resolve`
Só quando o routing determinístico de um `ask` termina `ambiguous` — e o profile não é `economy` — o core procura um resolver: o primeiro provider `ready` (ordem de id) que declara a op `resolve` e uma capability com `resolves_ambiguity` ([ADR 0025](adr/0025-semantic-routing-fallback.md)). O request é um `ResolveRequest` com a entrada mínima: a `task`, os `candidates` já elegíveis pelo routing (provider, capability, ações declaradas, estado e os sinais que pontuaram), a razão da ambiguidade e os nomes das tecnologias do workspace — nunca arquivos, packs ou o repositório.

O resolver responde uma `RoutingProposal` (`choice{provider, capability, action}`, `confidence`, `reason`, `evidence`, `alternatives`, `unknowns`, `limitations`). Ela **nunca roteia como veio**: o core revalida a escolha — provider registrado, capability resolvida (alias vira o id canônico com nota), candidato dentro do conjunto oferecido, ação declarada (vazia = `default_action`) — e a seleção validada segue o mesmo funil de health, policy, contexto e verificação de qualquer rota determinística. A proposta é persistida como artefato `routing-proposal` e ligada ao receipt por `inputs.routing_proposal_sha256`; a decisão gravada carrega a razão original da ambiguidade e a proveniência do resolver, com confiança `low` — um desempate semântico não é sinal medido. `refused`/`error` no envelope, `producer` divergente, payload malformado, falha de transporte ou escolha inválida deixam o desfecho `ambiguous` com a limitação correspondente; sem resolver declarado, idem. O provider é um backend de raciocínio genérico: o core depende da op e dos contratos, nunca de uma implementação.

## Contexto v2
O `ContextPack` continua por referência ([ADR 0007](adr/0007-context-pack-by-reference.md)): caminho, sha256 e tamanho, nunca conteúdo. Todos os campos abaixo são aditivos e opcionais dentro de `theforge/ContextPack/v1`; um provider que os ignora continua válido e recebe só itens `reference`. Decisões em [ADR 0015](adr/0015-context-intelligence.md).

### Tiers
| Tier | Onde aparece | Conteúdo |
|---|---|---|
| `metadata` | `ContextPack.workspace` (um por pack) | resumo do workspace; sempre presente em packs v2; conta 0 bytes |
| `reference` | `files[].tier` | arquivo inteiro: `sha256` e `bytes` do arquivo; `lines` proibido |
| `excerpt` | `files[].tier` | intervalo de linhas: `sha256` e `bytes` do intervalo; `lines` obrigatório |
| `requested` | `files[].tier` | item acrescentado por um [pedido de contexto](#pedido-de-contexto); arquivo inteiro sem `lines`, intervalo com `lines` |

- Tiers efetivos = tiers do perfil (`economy`: `metadata`, `reference`; `balanced` e `max`: os quatro) ∩ o que a capability declara em `context` (abaixo). Sem `context.excerpts` o provider nunca recebe `excerpt`, em nenhum perfil.
- Um `excerpt` vem do intervalo citado na intenção da tarefa (`arq.md:10-20`, `arq.md:L10-L20`, `arq.md#L10-L20`) ou, quando o arquivo inteiro não cabe no budget restante, do maior prefixo de linhas completas que caiba (pelo menos uma linha). Sem `excerpt` efetivo, um intervalo citado vira o arquivo inteiro e um arquivo que não cabe é excluído por `budget`.
- `tier_bytes` soma os bytes por tier (`metadata` sempre 0) e é igual a `used_bytes`. `tokens` é sempre `unknown` no core: bytes nunca viram tokens.
- `round`: 0 no pack inicial; 1 e 2 nas rodadas de negociação.

### Intervalos de linha
`lines` é `{"start": N, "end": M}`, 1-based e inclusivo (`1 <= start <= end`). Linhas são delimitadas só por `\n`: cada linha inclui o seu `\n` final, `\r\n` mantém o `\r` dentro da linha, a última linha sem `\n` conta como está e um `\n` final não abre uma linha vazia extra. O `sha256` e os `bytes` de um item com `lines` são exatamente os bytes dessas linhas.

### Sinais e exclusões
Cada item traz em `signals` os motivos determinísticos da seleção (`reason` repete-os unidos por `;`, por compatibilidade):

| Sinal | Significado |
|---|---|
| `intent_lines` | intervalo de linhas citado na intenção |
| `intent_path` | caminho citado na intenção |
| `target:<alvo>` | arquivo sob um alvo explícito da tarefa (o alvo padrão `.` não gera sinal) |
| `glob:<glob>` | casado por um `signals.file_globs` da capability |
| `git:changed` | alterado ou não rastreado segundo o `git status` (ver [security.md](security.md#consulta-git-somente-leitura)) |
| `dependency_manifest` | manifesto de dependências na raiz (`pyproject.toml`, `requirements*.txt`, `package.json`) |
| `requested` | acrescentado por pedido do provider |

A ordem é fixa: citados na intenção, depois alvos, depois globs (com os alterados no git primeiro e mais globs casados antes), depois só-git, depois só-dependência, e por fim o caminho. Arquivos sem nenhum sinal não são candidatos e entram só no agregado `workspace.unmatched_files`. Nenhum sinal usa LLM, embeddings, rede ou regra de domínio.

`excluded[].reason` é um de `budget`, `max_files`, `tier_not_allowed`, `secret`, `outside_root`, `unreadable`, `missing`, `symlinked_dir` e `max_files_reached`; `excluded[].signals` traz os sinais do arquivo excluído. Citações recusadas na intenção e itens recusados de um pedido são gravados depois de `security.redact`.

### Resumo do workspace (`metadata`)
`workspace` = `{files_scanned, unmatched_files, dependency_files, git}`. `git` é `{available, branch, head, detached, dirty, changed_files, state}`: `available` diz se um repositório foi localizado; `dirty` é verdadeiro se o `git status` tem qualquer entrada no repositório inteiro; `changed_files` conta só os arquivos alterados dentro da raiz do workspace (então `dirty: true` com `changed_files: 0` é possível); `state` lista `no_commits`, `merge`, `rebase`, `cherry_pick` e `bisect`. `dirty` e `changed_files` ficam nulos quando o `status` não rodou. Quando o git falta ou é recusado, o motivo vai para `ContextPack.limitations` (prefixo `git:`) e o run segue.

### Declarações no manifest
```json
{"capabilities": [{"id": "…", "context": {"excerpts": true, "requests": true}}],
 "context_revalidation": "hash"}
```
- `capabilities[].context.excerpts`: a capability aceita itens `excerpt` (sabe ler por intervalo). Padrão `false`.
- `capabilities[].context.requests`: a capability pode enviar [pedido de contexto](#pedido-de-contexto). Padrão `false`.
- `context_revalidation`: `hash`, `core`, `none` ou ausente ([abaixo](#revalidação-de-contexto-toctou)).

## Pedido de contexto
Em `execute`, um provider cuja capability declara `context.requests` pode responder um `ExecutionResult` com `context_request` em vez do resultado final:

```json
{"context_request": {"items": [{"path": "src/app.py", "lines": {"start": 10, "end": 40}, "reason": "…"}]}}
```

- A resposta passa pelas mesmas checagens de envelope, status, schema e [integridade](#integridade-do-resultado) de qualquer `execute`, mas **nunca** é gravada como `result`: sucesso só existe no resultado final, sem `context_request`.
- Checagens, nesta ordem (todas terminam em `provider_failure`, sem `result`):
  1. capability sem `context.requests` → `FORGE-CONTEXT-REQUEST-UNSUPPORTED`;
  2. rodadas do perfil esgotadas (`economy` 0, `balanced` 1, `max` 2; nunca mais de 2) → `FORGE-CONTEXT-REQUEST-LIMIT` (em `economy`, qualquer pedido);
  3. 0 itens ou mais de 64 → `FORGE-CONTEXT-REQUEST-INVALID`.

  `context_request` estruturalmente inválido (por exemplo `lines` com `start < 1` ou `end < start`) falha antes, no schema do resultado (`FORGE-PROTO-SCHEMA`).
- Cada item passa pelas mesmas regras da seleção inicial: caminho relativo POSIX dentro da raiz (sem `\`, NUL, `/` ou `~` inicial, drive ou `..`), presente na varredura, nome que não seja de segredo, limite de arquivos e budget **restante** do pack. Item aprovado entra como `requested`; item recusado entra em `excluded` com o motivo, e o run segue. Intervalo além do fim do arquivo é recusado como `missing`. Um item já entregue com o mesmo caminho e intervalo é ignorado. O `reason` do item não é persistido. O pedido nunca amplia o budget nem o limite de arquivos do perfil.
- O pack estendido (itens anteriores preservados, `round` incrementado) é validado, gravado como artefato `context-r1`/`context-r2` (hash em `ReceiptInputs.context_round_sha256`) e enviado em uma nova chamada `execute`.
- Cada chamada `execute` tem o timeout inteiro do perfil (60 s / 180 s / 600 s). No pior caso, `max` faz 3 chamadas: 3 × 600 s ≈ 30 min.

## Revalidação de contexto (TOCTOU)
Entre o hash do ContextPack e a leitura pelo provider o arquivo pode mudar. O provider **deve** fazer uma de duas coisas:

1. revalidar: recalcular o sha256 do que leu e informá-lo em `Evidence.hash` (declare `context_revalidation: "hash"`); ou
2. declarar no manifest, em `context_revalidation`, a estratégia alternativa: `core` (deixa a revalidação para a reverificação do core) ou `none` (não revalida).

Provider sem `context_revalidation` é registrado como `undeclared`, com a limitação `provider-revalidation-undeclared` na telemetria e no receipt. A estratégia declarada é registrada na telemetria do run (`provider_revalidation`). A declaração é informativa: a reverificação do core segue o nível do perfil qualquer que seja a estratégia.

### Semântica de `Evidence.hash`
`Evidence.hash` é o sha256 de **exatamente** o conteúdo entregue em `location.path`:

- o arquivo inteiro, para itens `reference` e `requested` sem `lines`;
- os bytes do intervalo `lines` do item (regra de [intervalos de linha](#intervalos-de-linha)), para itens `excerpt` e `requested` com `lines`.

`location.line` não altera esse escopo. Em qualquer outro caso o provider deve deixar `hash` nulo: evidência sem `location`, caminho fora do ContextPack, ou leitura que não cobre exatamente o conteúdo do item (por exemplo, só parte de um arquivo entregue como `reference`).

### Regra de divergência
- **Reportada pelo provider**: uma evidência com `location` e `hash` não nulo cujo valor difere do `sha256` de **todos** os itens do pack final com o mesmo caminho (basta coincidir com um; a comparação é sempre contra `item.sha256`, que já é o hash do intervalo para itens com `lines`). `hash` nulo ou evidência sem `location` nunca geram divergência reportada.
- **Reverificada pelo core**, conforme o nível do perfil: `minimal` (`economy`) não reverifica e registra `context-not-reverified`; `conditional` (`balanced`) rehasheia os itens referenciados por evidências `confirmed` ou `observed`; `strong` (`max`) rehasheia todos os itens do pack final. O rehash usa o mesmo escopo do item, sem cache; arquivo ausente, ilegível, fora da raiz ou intervalo além do fim conta como divergência.
- **Efeito**: evidências `confirmed`/`observed` sobre um item divergente são gravadas como `unresolved`, com a limitação `context-drift: was <status>`; o resultado e o receipt recebem `context-drift: <path>`; o run termina `partial`, nunca `ok`.

## Manifest
Além do schema, o manifest é recusado (provider `invalid`, fora do routing) se tiver IDs de capability duplicados, capability sem `actions`, `default_action` fora de `actions`, `ops` sem `describe` e `health`, alias repetido ou alias igual ao ID de uma capability do mesmo manifest, ou `replaced_by` igual ao próprio ID.

### Versão (SemVer)
`version` precisa ser [SemVer 2.0.0](https://semver.org/) (`MAJOR.MINOR.PATCH`, pré-release e build opcionais, sem `v` inicial nem zeros à esquerda). Versão malformada (`1.0`, `v1.2.3`, `01.2.3`) deixa o provider `invalid`, fora do routing, com `FORGE-MANIFEST-VERSION` e a versão recebida no erro. As demais regras de versão estão em [versioning.md](versioning.md).

### Taxonomia, aliases e depreciação
Campos opcionais de cada capability, com default que preserva o comportamento anterior (o schema continua `theforge/ForgeManifest/v1`):

| Campo | Default | Efeito |
|---|---|---|
| `aliases` | `[]` | IDs antigos que continuam atendendo `--capability`; o pedido resolve para o ID canônico e a decisão registra `capability-alias`. Um alias que resolve para IDs canônicos diferentes em providers diferentes vira `ambiguous` |
| `deprecated` | `false` | a capability continua roteável; a decisão registra `capability-deprecated` e `capabilities list` avisa em stderr |
| `replaced_by` | `null` | ID da capability substituta, mostrado junto da depreciação |

O ID, as ações, os aliases e o formato de `replaced_by` passam pelas regras mecânicas da taxonomia ([capabilities.md](capabilities.md#regras-mecânicas), [ADR 0017](adr/0017-capability-taxonomy.md)). Uma violação exclui só aquela capability, com aviso `FORGE-MANIFEST-TAXONOMY`; se nenhuma sobrar, o provider fica `invalid`.

O manifest pode declarar `context_revalidation` (opcional; os adapters reais declaram `"hash"`: conferem o sha256 de cada arquivo do ContextPack antes de usá-lo). Um core que não conhece o campo o ignora, como qualquer campo desconhecido de provider.

Atualizar o core para esta versão muda o `manifest_sha256` de todo provider (os defaults acima entram no hash). Cada entrada do cache do registry é descartada uma vez, com o aviso `registry cache for <id> discarded: …`, e o provider é descrito de novo. Não há ação a tomar.

### Limites

Limites (`contracts/types.py`, valores iniciais):

| Limite | Valor | Ao exceder |
|---|---|---|
| capabilities por manifest | 256 | provider `invalid` |
| `actions` por capability | 16 | capability excluída |
| `signals.keywords` por capability | 64 | capability excluída |
| `signals.file_globs` por capability | 32 | capability excluída |
| `signals.dependencies` por capability | 32 | capability excluída |

- Capability excluída gera aviso `FORGE-MANIFEST-LIMITS` no registry; as demais continuam roteáveis. Se nenhuma sobrar, o provider fica `invalid`.
- **Glob catch-all** também exclui a capability. É catch-all um glob (sem espaços nas pontas e sem `./` inicial) que seja `*`, `**`, `**/*`, `*.*` ou `**/*.*`, ou que não tenha nenhum caractere alfanumérico literal depois de descartar classes negadas (`[!…]`, `[^…]`) e classes com intervalo (`[a-z]`). Exemplos: `?*`, `**/?*`, `[!.]*`. Classes positivas de literais contam como literais (`*.[ch]` é válido). Globs por extensão (`*.md`, `*.scala`) são sinais legítimos e são permitidos.

## Execução multi-provider
`theforge plan` divide uma tarefa em nós, cada um executado por um único provider, um de cada vez ([ADR 0018](adr/0018-multi-provider-execution.md), [architecture.md](architecture.md#fluxo-de-plan)). Para o provider, cada nó é um `execute` comum. Tudo nesta seção é aditivo e opcional dentro de `forge/v1`: um provider que não conhece nenhum destes campos continua válido, e um nó com ele termina `ok` normalmente.

### Operação `plan`
- **Quando.** Só durante `theforge plan`, depois de o plano ser validado e antes de executar qualquer nó (inclusive sem `--execute`): uma chamada por nó cujo provider declara `plan` em `describe.ops`. `ask` nunca chama `plan`. Há um segundo momento opcional, anterior: quando a decomposição determinística termina `ambiguous` e o profile não é `economy`, o planner híbrido chama o tier-2 (abaixo).
- **Superfície.** A mesma de `describe` e `health`: cwd temporário apagado depois da chamada, [ambiente mínimo](security.md#ambiente-do-provider), timeout de 10 s e `producer` (id e versão) conferido. Provider que não está `ready`, `blocked` ou `unverified` sem `--allow-unverified` não é chamado.
- **Request.** `PlanRequest` (`theforge/PlanRequest/v1`, schema aberto): `{task, capability, action}`, com a `TaskSpec` do nó (alvos do nó, capability e ação pedidas). Campos aditivos: `purpose` (`"estimate"`, padrão; `"proposal"` no tier-2), `options` (o conjunto elegível que um planner semântico pode escolher) e `ambiguity` (por que os tiers determinísticos não decidiram).
- **Response.** Status `ok` com payload `PlanEstimate` (`theforge/PlanEstimate/v1`, schema aberto) para `purpose="estimate"`, ou `SemanticPlanProposal` (`theforge/SemanticPlanProposal/v1`, schema aberto) para `purpose="proposal"`. Campos de `PlanEstimate`, todos opcionais:

  | Campo | Conteúdo |
  |---|---|
  | `context_needed` | caminhos relativos ou globs que o provider espera ler |
  | `operation_class` | classe de operação estimada para este pedido (`read_only` … `destructive`) |
  | `expected_artifacts` | artifacts que o provider espera gravar |
  | `unknowns`, `limitations` | o que o provider ainda não sabe e o que não fará |

- **Uso.** A estimativa vai para `nodes[].estimate` do plano. Uma `operation_class` estimada só pode **endurecer** a policy: o nó é avaliado para a classe declarada no manifest e para a estimada, e vale a decisão mais restritiva (`deny` > `ask` > `allow`). Quando a estimada vence, o `risk` do run do nó registra a classe estimada e a limitação `operation-class: estimate <estimada> stricter than declared <declarada>`.
- **Falhas.** Nada aqui falha o planejamento. Provider sem `plan` gera a limitação `estimate: provider does not declare op plan` no nó; qualquer outra falha (estado, trust, transporte, `refused`/`error`, `producer`, schema) gera `estimate: FORGE-PLAN-ESTIMATE: <detalhe>`. Nos dois casos a estimativa fica desconhecida e o nó segue com a classe declarada.

#### Planner híbrido (`purpose="proposal"`, tier-2)

O decompositor é determinístico e camadas: tier-0 cobre capability pedida, um provider qualificado ou o limite do profile; tier-1 ordena o pipeline pelas relações declaradas do grafo de capabilities (`requires`, produces→consumes; `conflicts` e ciclos viram ambiguidade) e só então pelo proxy `intent-order`. Só quando o resultado é `ambiguous` — e o profile não é `economy` — o core procura um provider `ready` com uma capability `proposes_plans` (escolha determinística por id) e chama o op `plan` com `purpose="proposal"`, `options` (só os candidatos elegíveis do routing) e `ambiguity`.

A resposta é uma `SemanticPlanProposal` — `nodes` (com `ref`, provider/capability/action, `depends_on`, `inputs`, `role`, `rationale`), `dependencies` com razão por aresta, `rationale`, `evidence`, `assumptions`, `unknowns`, `confidence`, `alternatives` e `limitations`. Ela **nunca executa como veio**: o core materializa um `ExecutionPlan` (`source="semantic"`, dependências `explicit` com a razão declarada como evidência) e o `check_plan` de sempre revalida providers, capabilities, actions e limites do profile — nada inventado é aceito, refs quebrados e duplicatas viram violações `FORGE-PLAN-INVALID`. A proposta é persistida no artefato `semantic-proposal` do run de plano, linkada por `PlanRefs.semantic_proposal_sha256`; o routing gravado marca `semantic plan proposed by <planner>`. Sem planner declarado, ou falha/invalidade qualquer, o run fica no desfecho determinístico `ambiguous` com a limitação correspondente; `economy` nunca chama o planner.

### Handoff
Um nó que depende de outros recebe, no campo opcional `handoff` do `ExecuteRequest`, um `Handoff` (`theforge/Handoff/v1`, schema aberto) montado só a partir dos nós listados em `inputs` do nó. Fora de planos o campo é `null`.

```json
{"handoff": {"schema": "theforge/Handoff/v1", "producer": {"id": "theforge", "version": "…"},
  "created_at": "…", "plan_run": "…", "target_node": "n2",
  "items": [{"kind": "evidence", "id": "e1", "epistemic": "observed",
             "origin": {"plan_run": "…", "node": "n1", "run_id": "…",
                        "provider": {"id": "spark-forge", "version": "0.5.0"}},
             "subject": "…", "claim": "…", "location": {"path": "jobs/x.py", "line": 3},
             "hash": null}],
  "truncated": false, "dropped": 0, "limitations": []}}
```

- **Itens (evidence bus).** `decision` (`id` = `outcome`, o status, a capability e a ação do nó de origem, `epistemic` = `observed`), `verification` (`id` = `verification`, resumo `forge=<status> independent=<status> self_report=<status> provider_evidence=<status>` do `VerificationResult` do run de origem — só quando o run persistiu verificação), `finding` (id original, severidade, `evidence_ids`), `evidence` (id original, **status epistêmico original** nunca elevado e `derived_from` verbatim — a cadeia de proveniência), `artifact` (caminho relativo ao `work/` do nó de origem, `hash` sha256 e `artifact_type` quando inferível), `constraint` (`constraint:<i>`, as `limitations` do resultado de origem, redigidas e capadas) e `assumption` (`assumption:<i>`, as `assumptions` declaradas do resultado). Cada item traz `origin`: run do plano, nó, run e provider (id e versão) de onde veio — quem produziu, de qual run, com qual nível epistêmico e se foi verificado.
- **Reuse content-addressed.** Itens idênticos em conteúdo vindos de vários nós de origem são enviados uma única vez: a primeira ocorrência prevalece e as demais origens ficam em `also_from`. Um item repassado verbatim por um intermediário (ex.: dependência em diamante) não se duplica.
- **Filtro do consumidor.** Quando a capability do nó consumidor declara `relations.consumes`, itens `artifact` cujo `artifact_type` inferido (o único `produces` declarado da capability de origem) não está nas necessidades são descartados com a limitação `handoff-filtered: <nó>:<caminho> (artifact type <t> not consumed by <cap>)`; artifacts de tipo desconhecido são conservados (nunca se adivinha). Necessidades vazias desligam o filtro.
- **Sem conteúdo.** Nenhum item carrega conteúdo de arquivo nem a saída integral do provider: só ids, `claim` (no máximo 500 caracteres), localização e hashes. Um nó de origem sem resultado válido não contribui (limitação `handoff-input-missing: <nó>`). `unknowns` de origem não cruzam.
- **Limites.** 256 itens e 262 144 bytes de JSON canônico. Acima disso o core corta de forma determinística, nesta prioridade por nó de origem: decisão, verificação, findings (por severidade), evidências (as referenciadas por findings primeiro, depois por status epistêmico), artifacts (os consumidos declarados primeiro), constraints e assumptions; `truncated` vira `true`, `dropped` conta os descartados e a limitação `handoff-truncated: dropped <N> items` é registrada.
- **Redação.** O handoff passa por `security.redact` antes de ser medido; o que o provider recebe é exatamente o artefato `handoff` gravado no run do nó, cujo hash fica em `inputs.handoff_sha256` do receipt.
- **Consumo opcional.** O provider pode ignorar o campo. Se a capability selecionada não declara `accepts_handoff: true` e recebe um handoff, o run do nó registra a limitação `handoff-use-undeclared: <provider>/<capability>` e segue normalmente.

### Declarações no manifest
```json
{"capabilities": [{"id": "…", "accepts_handoff": true,
                   "relations": {"produces": ["orders.facts"],
                                 "consumes": ["upstream.context"],
                                 "requires": ["other-forge/x.y"],
                                 "complements": [], "conflicts": [],
                                 "can_verify": [], "can_review": []}}],
 "execution": {"local": true, "offline": true, "requires_network": false,
               "deterministic": true},
 "ops": ["describe", "health", "execute", "plan"]}
```
- `capabilities[].accepts_handoff` (padrão `false`): a capability lê o `handoff` do `ExecuteRequest`. Só muda a limitação acima; o handoff é enviado de qualquer forma.
- `capabilities[].proposes_plans` (padrão `false`): a capability responde pedidos `plan` com `purpose="proposal"` — é o planner semântico do tier-2 ([planner híbrido](#planner-híbrido-purposeproposal-tier-2)).
- `capabilities[].resolves_ambiguity` (padrão `false`): a capability responde pedidos `resolve` com uma `RoutingProposal` — é o resolvedor semântico de routing ([Operação `resolve`](#operação-resolve)); o provider também precisa declarar a op `resolve`.
- `capabilities[].relations` (padrão vazio): relações declaradas que alimentam o grafo de capabilities. `produces`/`consumes` nomeiam tipos de artefato (`^[a-z][a-z0-9-]*(\.[a-z][a-z0-9-]*)*$`); `requires`, `complements`, `conflicts`, `can_verify`, `can_review` nomeiam capabilities — `cap.id` para a do próprio provider, `provider/cap.id` entre providers. É declaração, não verificação: um alvo ausente do registry mantém a aresta e é nomeado nas limitações do grafo.
- `execution.deterministic` (padrão `null`, não declarado): `true` diz que as mesmas entradas produzem o mesmo resultado. É condição necessária para o run ser `reproducible`; `null` ou `false` nunca resultam em `reproducible` ([ADR 0019](adr/0019-error-taxonomy-and-reproducibility.md)).
- `plan` em `ops`: o provider responde à [operação `plan`](#operação-plan).

Nos adapters reais: `api.analyze` do API Forge declara `accepts_handoff` e consome os itens como *facts* de upstream (`--upstream`, `apiforge/upstream-facts/v1`; itens acima dos limites do intake — 32 itens, 64 KiB — são truncados com limitação, itens malformados são pulados com limitação). Quando o especialista instalado não expõe a entrada, o adapter degrada a `ok`/`partial` com a limitação de consumo ausente — nunca finge ter lido. O Spark Forge e o `api.change-control` ainda não declaram: recebem o handoff e o run do nó registra `handoff-use-undeclared`.

#### Evidência derivada (`Evidence.derived_from`)

Uma capability que consumiu o handoff pode marcar a evidência que carrega adiante com `derived_from: {provider, run_id, item, node?, plan_run?}` — a identidade do item de origem. O check de verificação `handoff-provenance` confere cada `derived_from` contra o handoff entregue àquele run: item que o provider não recebeu, `node`/`plan_run` divergentes ou status epistêmico **mais forte** que o do item de origem (um `inferred` virar `confirmed` sem evidência nova) falham a verificação.

### Padrões
`RoutingDecision.pattern` (padrão `route`; decisões gravadas sem o campo são relidas como `route`) e `ExecutionPlan.pattern` aceitam `route`, `delegate`, `parallel`, `pipeline` e `debate`, e todos executam. `route` (um nó) e `pipeline` rodam sequencialmente na ordem topológica; `delegate`, `parallel` e `debate` executam os nós de cada nível de dependência concorrentemente, no máximo `MAX_PARALLEL_NODES` = 4 por vez — a ordem gravada no `plan-result` é sempre a topológica, nunca a de chegada, e cada nó continua sendo um run completo com recibo próprio e a mesma semântica de falha parcial (um nó cujo ancestral falhou fica `skipped`; os independentes continuam). Regras estruturais por padrão: `delegate` exige subtarefas independentes (o core é o manager — nenhum especialista declara `depends_on`/`inputs`); `debate` exige pelo menos dois nós `role="proposer"` independentes e exatamente um `role="referee"` que depende de todos e os declara em `inputs`. Um valor de `pattern` fora dos cinco é recusado com `FORGE-PLAN-PATTERN-RESERVED`. Os demais códigos de plano estão em [errors.md](errors.md#códigos).

O `debate` é caro e raro — nunca o padrão: a decomposição determinística só emite `route`/`pipeline`; `delegate`, `parallel` e `debate` entram por `--from FILE` ou por proposta semântica validada. Ao fim de um `debate` o core compõe o `DecisionRecord/v1` (artefato `decision`, schema fechado) com `question`, `options`, `evidence` (os itens que o referee recebeu), `tradeoffs` (findings dos proposers), `chosen`, `rejected`, `rationale`, `confidence`, `unknowns` e `limitations`. A escolha é uma convenção auditável: o referee declara `evidence` com `id="decision"` e `claim` = id do nó proposer escolhido; sem ela, ou com uma claim fora dos proposers, o record fica `unresolved` com a razão em `limitations` — o core nunca inventa a escolha.

Um plano executado também grava `plan-state` (`PlanState/v1`): snapshot durável do escalonador, regravado quando o plano é validado, após cada nó registrado e uma última vez antes do `plan-result` — o receipt liga o hash final. `theforge resume <run_id>` continua um run de plano (a task e o plano gravados são reusados verbatim — hashes idênticos são a prova) re-hidratando só os nós cujas entradas ainda verificam (cadeia de hashes do run filho, identidade do provider, handoff reconstruído byte-idêntico); o resto reexecuta e o motivo é registrado como limitação. A retentativa de falhas transitórias é política (`retry.toml`), nunca o default: só os códigos listados, no máximo `max_attempts` tentativas, cada uma um run filho completo.

## Códigos de erro do core
Os valores ficam em `src/theforge/contracts/codes.py` e nunca mudam depois de publicados. A lista canônica e testada de códigos `FORGE-*`, com a família de cada um, é [errors.md](errors.md). Esta seção só resume os códigos de manifest e de pedido de contexto citados acima:

| Código | Família | Causa |
|---|---|---|
| `FORGE-MANIFEST-LIMITS` | registry | manifest ou capability acima dos [limites](#limites), ou glob catch-all (aviso; capability ou provider excluído) |
| `FORGE-MANIFEST-VERSION` | registry | `version` do manifest não é SemVer 2.0.0 (provider `invalid`) |
| `FORGE-MANIFEST-TAXONOMY` | registry | capability, ação, alias ou `replaced_by` fora das regras mecânicas da taxonomia (aviso; capability excluída, provider `invalid` se nenhuma restar) |
| `FORGE-CONTEXT-REQUEST-UNSUPPORTED` | context | `context_request` de uma capability que não declara `context.requests` ([pedido de contexto](#pedido-de-contexto); `provider_failure`) |
| `FORGE-CONTEXT-REQUEST-LIMIT` | context | `context_request` além das rodadas do perfil, inclusive qualquer pedido em `economy` (`provider_failure`) |
| `FORGE-CONTEXT-REQUEST-INVALID` | context | `context_request` com 0 itens ou mais de 64 (`provider_failure`) |

## Códigos dos adapters reais
Os adapters de Spark Forge e API Forge ([ADR 0014](adr/0014-provider-adapter-location.md)) respondem com códigos próprios, que não são `FORGE-*` e não ficam em `codes.py`. Convenção: `ADAPTER-<X>` para a mecânica comum (`_shell.py`, igual nos dois), `<FORGE>-ADAPTER-<X>` para falhas originadas no adapter e `<FORGE>-<X>` (sem `ADAPTER`) só para erros nativos mapeados. Códigos `AF-*` do API Forge passam intactos, com `field` e `unlock`.

| Código | Status | Causa |
|---|---|---|
| `ADAPTER-OP-UNSUPPORTED` | `refused` | op desconhecida |
| `ADAPTER-PROTOCOL-UNSUPPORTED` | `refused` | protocolo do request não suportado (fora de `describe`) |
| `ADAPTER-REQUEST-INVALID` | `error` | request malformado |
| `ADAPTER-CAPABILITY-UNSUPPORTED` / `ADAPTER-ACTION-UNSUPPORTED` | `refused` | capability ou ação não declarada no manifest |
| `ADAPTER-INTERNAL` | `error` | exceção inesperada (só o tipo, nunca traceback) |
| `ADAPTER-NATIVE-TIMEOUT` | `error` | a chamada nativa passou de 85% do timeout de execute do perfil; a árvore nativa é encerrada |
| `ADAPTER-OUTPUT-TOO-LARGE` | `error` | o resultado passa de 4 MiB mesmo sem nenhum finding inline; nada é gravado |
| `ADAPTER-REPLAY-MISSING` / `ADAPTER-REPLAY-INVALID` | `error` | em `--replay`, um arquivo do cenário (gravação da ação, `environment.json` ou `health.json`) não existe ou é inválido |
| `SPARKFORGE-ADAPTER-UNAVAILABLE` / `APIFORGE-ADAPTER-UNAVAILABLE` | `refused` | especialista não importável (no API, também Python ≠ 3.12) |
| `SPARKFORGE-ADAPTER-SNAPSHOT-INVALID` / `APIFORGE-ADAPTER-SNAPSHOT-INVALID` | `error` | snapshot empacotado da superfície nativa ausente ou ilegível |
| `SPARKFORGE-ADAPTER-NATIVE-FAILED` | `error` | o processo filho nativo saiu com código ≠ 0 ou com stdout truncado |
| `SPARKFORGE-ADAPTER-NATIVE-INVALID` / `APIFORGE-ADAPTER-NATIVE-INVALID` | `error` | saída nativa fora do formato esperado |
| `APIFORGE-ADAPTER-NATIVE-FAILURE` | `error` | a CLI saiu com erro sem uma linha `AF-*` reconhecível |
| `APIFORGE-ADAPTER-INPUT-OUTSIDE` | `refused` | caminho do bundle de `change-control` fora do workspace |
| `SPARKFORGE-TOOL-UNKNOWN` | `refused` | tool nativa inexistente |
| `SPARKFORGE-<código nativo>` / `SPARKFORGE-TOOL-ERROR` | `refused` ou `error` | erro nativo: tipado ou exit 2 → `refused`, senão `error` |
| `AF-*` | `refused` ou `error` | erro nativo do API Forge: exit 2 → `refused`; exit 3, `AF-CLI-INTERNAL` ou outro → `error` |

## Contratos
Os JSON Schemas ficam em `schemas/` (regenerados com `python -m theforge.contracts.schema schemas`; um teste confere a paridade). Todo contrato tem `schema = "theforge/<Name>/v1"` e só evolui por campos aditivos e opcionais dentro de v1. `RiskAssessment` v1 é o artefato `risk` do run (ver [security.md](security.md#policy-e-risco)). `RunTelemetry` v1 é o artefato `telemetry`, gravado em todo run e ligado ao receipt por `telemetry_sha256` (ver [architecture.md](architecture.md#telemetria)).

Contratos da execução multi-provider ([ADR 0018](adr/0018-multi-provider-execution.md), [ADR 0019](adr/0019-error-taxonomy-and-reproducibility.md)):

| Contrato | Onde aparece | Cruza o protocolo |
|---|---|---|
| `theforge/PlanRequest/v1`, `theforge/PlanEstimate/v1` | request e response da [op `plan`](#operação-plan); a estimativa fica em `nodes[].estimate` | sim (schema aberto) |
| `theforge/Handoff/v1` | `ExecuteRequest.handoff` e artefato `handoff` do run do nó | sim (schema aberto) |
| `theforge/ResolveRequest/v1`, `theforge/RoutingProposal/v1` | request e response da [op `resolve`](#operação-resolve); a proposta fica no artefato `routing-proposal`, ligado ao receipt por `inputs.routing_proposal_sha256` | sim (schema aberto) |
| `theforge/ExecutionPlan/v1` | artefato `plan` do run do plano | não |
| `theforge/PlanResult/v1` | artefato `plan-result`: desfecho por nó, ordem efetiva, síntese, reprodutibilidade combinada | não |
| `theforge/DecisionRecord/v1` | artefato `decision` de um plano `debate` ([padrões](#padrões)) | não |
| `theforge/RunBudget/v1` | artefato `budget` de todo run que resolve um perfil, ligado ao receipt por `inputs.budget_sha256` | não |
| `theforge/ProviderPerformance/v1` | histórico medido por provider+capability em `.forge/metrics/provider-performance.json` ([economia](architecture.md#economia)) | não |
| `theforge/ProjectIntel/v1` | snapshot fingerprinted do workspace em `.forge/intel/project.json`; freshness é veredito de leitura, nunca gravado ([inteligência do projeto](architecture.md#inteligência-do-projeto)) | não |
| `theforge/DecisionMemory/v1` | decisões reutilizáveis deduplicadas em `.forge/intel/decisions.json`, lidas por `theforge decisions` | não |
| `theforge/PlanState/v1` | artefato `plan-state`: snapshot durável do escalonador (estado por nó, `run_state`, `resumed_from`), regravado a cada nó e ligado no receipt por `PlanRefs.plan_state_sha256` | não |
| `theforge/WorkspaceDescriptor/v1` | artefato `workspace-descriptor` e `theforge workspace show --json` | não |
| `theforge/WorkspaceGraph/v1` | artefato `graph` (nós e arestas com evidência) | não |
| `theforge/VerificationResult/v1` | artefato `verification` de todo run de um provider | não |
| `theforge/InstallationPlan/v1` | artefato `installation`, só de planejamento | não |
| `theforge/ExplainReport/v1` | `theforge explain --json` ([cli.md](cli.md#explain)) | não |
| `theforge/Diagnostic/v1` | artefato `diagnostic` e linhas `theforge: debug:` com `--debug` | não |

Campos aditivos em contratos existentes: `RoutingDecision.pattern`, `ExecuteRequest.handoff`, `Capability.{accepts_handoff, proposes_plans, resolves_ambiguity, relations}`, `PlanRequest.{purpose, options, ambiguity}`, `Evidence.derived_from`, `ExecutionResult.assumptions`, `HandoffItem.{derived_from, also_from, artifact_type}` e os kinds `constraint`/`assumption`/`verification`, `ExecutionInfo.deterministic`, `ExecutionReceipt.{kind, parent_run, plan_node, replay_of, resumed_from, verification_sha256, reproducibility, plan}`, `ReceiptInputs.{handoff_sha256, complexity_sha256, budget_sha256, routing_proposal_sha256}`, `NodeOutcome.{attempts, reused}`, `PlanResult.decision_sha256`, `PlanRefs.{capability_graph_sha256, semantic_proposal_sha256, decision_sha256, plan_state_sha256}`, `RunTelemetry.{semantic_planner_calls, semantic_resolver_calls, files_cited, evidence_returned, findings_returned, spans}` (`Span`: `id`, `name`, `start_ms`, `duration_ms`, `parent`, `status`, `attributes`), o valor `semantic` de `ExecutionPlan.source` e o desfecho `planned` (só em receipts de `kind = "plan"`). Runs e manifests gravados sem eles continuam válidos: verificação e reprodutibilidade ausentes valem "não registrado" e `unknown`.

Nomes reservados (sem implementação): `EnvironmentReport` (v0 não estável em `doctor`); a op `estimate`. O antigo nome reservado `Budget` foi implementado como `RunBudget/v1`.
