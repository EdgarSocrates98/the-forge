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
| `execute` | não | `ExecuteRequest{task, capability, action, context}` | `ExecutionResult` |
| `plan`, `verify`, `estimate` | reservadas | — | — |

O provider declara as ops que suporta em `describe.ops`. As capabilities de um provider que não declara `execute` não são roteáveis. A decisão de routing registra em `limitations` os providers excluídos por isso quando são relevantes: declaram a capability pedida com `--capability`, ou, no routing por sinais, nada foi roteado. Um pedido com `--capability` é recusado com `FORGE-PROTO-OP-UNSUPPORTED` (sem iniciar o processo de `execute`) quando um provider roteável declara a capability sem `execute` e nenhum outro poderia executá-la: nenhum declarante com `execute`, qualquer que seja o trust ou o estado, e nenhum provider não bloqueado de manifest desconhecido. Caso contrário fica o `no_route` comum: o provider que executaria está fora do routing por outro motivo (por exemplo `unverified` sem `--allow-unverified`, ou indisponível), e `theforge registry list` mostra trust e estado de cada um.

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
- `producer.id` precisa ser o id registrado do provider e `producer.version` a `version` do manifest. O core confere o `producer` do envelope nas três ops: em `describe` contra o manifest retornado, em `health` e em `execute` contra o manifest em uso. Em `execute`, o `ExecutionResult.producer` (id e versão) também é conferido.

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
| Core, ao reler o que gravou | artefatos do run (`task`, `routing`, `risk`, `context`, `context-r1`, `context-r2`, `result`, `telemetry`, `receipt`), o cache do registry e o cache de fingerprints de contexto | rejeitado em qualquer profundidade (`$.<caminho>: unknown field`) |

- O core persiste só os campos que conhece, então um `result` vindo de provider com campos extras é relido sem eles.
- Nos JSON Schemas de `schemas/`, `additionalProperties: false` aparece só em `RoutingDecision`, `ExecutionReceipt`, `RiskAssessment` e `RunTelemetry`, que nunca cruzam o protocolo. `TaskSpec` e `ContextPack` vão ao provider dentro de `ExecuteRequest` e continuam com schema aberto; a rigidez deles vem da releitura estrita.

## Integridade do resultado
Um `ExecutionResult` só é persistido se passar por todas as regras abaixo. Caso contrário, o run termina em `provider_failure` com o código da primeira violação, nenhum artefato `result` é gravado e o receipt é gravado mesmo assim.

- IDs de `evidence` únicos (`FORGE-RESULT-DUP-EVIDENCE`) e IDs de `findings` únicos (`FORGE-RESULT-DUP-FINDING`).
- Todo `finding.evidence_ids` aponta para uma evidence do mesmo resultado (`FORGE-RESULT-DANGLING-EVIDENCE`).
- `artifacts[].path` (`FORGE-RESULT-ARTIFACT-PATH`): caminho relativo POSIX, não vazio, sem `\`, sem `/` inicial, sem letra de drive (`C:`), sem segmento `..`, sem byte NUL e que nomeie algo abaixo da raiz (não só `.`). A checagem é léxica: o core nunca abre o caminho.
- A raiz de `artifacts[].path` é o cwd do `execute` (`.forge/runs/<id>/work/`): `native/full-output.json` nomeia `.forge/runs/<id>/work/native/full-output.json`. O `sha256` é calculado pelo provider sobre os bytes do arquivo; o core não o recalcula.
- `created_at` em ISO-8601 UTC, com sufixo `Z` ou `+00:00` (`FORGE-PROTO-SCHEMA`).
- `producer` igual ao provider invocado, id e versão (`FORGE-PROTO-PRODUCER`).

### Formato de hash
Todo campo SHA-256 é exatamente 64 caracteres hexadecimais **minúsculos** (`^[0-9a-f]{64}$`): `Artifact.sha256`, `ContextFile.sha256`, `Evidence.hash` (quando presente) e os `*_sha256` do receipt. Hash maiúsculo, curto ou não hexadecimal invalida o contrato que o contém. O que `Evidence.hash` cobre está em [Revalidação de contexto](#revalidação-de-contexto-toctou).

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
Os JSON Schemas ficam em `schemas/`. `RiskAssessment` v1 é o artefato `risk` do run (ver [security.md](security.md#policy-e-risco)). `RunTelemetry` v1 é o artefato `telemetry`, gravado em todo run e ligado ao receipt por `telemetry_sha256` (ver [architecture.md](architecture.md#telemetria)). Nomes reservados (sem implementação): ExecutionPlan, VerificationResult, Budget, GraphNode, GraphEdge, InstallationPlan, DecisionRecord, WorkspaceDescriptor, EnvironmentReport (v0 não estável em `doctor`).
