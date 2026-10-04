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
| Core, ao reler o que gravou | artefatos do run (`task`, `routing`, `risk`, `context`, `result`, `receipt`) e o cache do registry | rejeitado em qualquer profundidade (`$.<caminho>: unknown field`) |

- O core persiste só os campos que conhece, então um `result` vindo de provider com campos extras é relido sem eles.
- Nos JSON Schemas de `schemas/`, `additionalProperties: false` aparece só em `RoutingDecision`, `ExecutionReceipt` e `RiskAssessment`, que nunca cruzam o protocolo. `TaskSpec` e `ContextPack` vão ao provider dentro de `ExecuteRequest` e continuam com schema aberto; a rigidez deles vem da releitura estrita.

## Integridade do resultado
Um `ExecutionResult` só é persistido se passar por todas as regras abaixo. Caso contrário, o run termina em `provider_failure` com o código da primeira violação, nenhum artefato `result` é gravado e o receipt é gravado mesmo assim.

- IDs de `evidence` únicos (`FORGE-RESULT-DUP-EVIDENCE`) e IDs de `findings` únicos (`FORGE-RESULT-DUP-FINDING`).
- Todo `finding.evidence_ids` aponta para uma evidence do mesmo resultado (`FORGE-RESULT-DANGLING-EVIDENCE`).
- `artifacts[].path` (`FORGE-RESULT-ARTIFACT-PATH`): caminho relativo POSIX, não vazio, sem `\`, sem `/` inicial, sem letra de drive (`C:`), sem segmento `..`, sem byte NUL e que nomeie algo abaixo da raiz (não só `.`). A checagem é léxica: o core nunca abre o caminho.
- A raiz de `artifacts[].path` é o cwd do `execute` (`.forge/runs/<id>/work/`): `native/full-output.json` nomeia `.forge/runs/<id>/work/native/full-output.json`. O `sha256` é calculado pelo provider sobre os bytes do arquivo; o core não o recalcula.
- `created_at` em ISO-8601 UTC, com sufixo `Z` ou `+00:00` (`FORGE-PROTO-SCHEMA`).
- `producer` igual ao provider invocado, id e versão (`FORGE-PROTO-PRODUCER`).

### Formato de hash
Todo campo SHA-256 é exatamente 64 caracteres hexadecimais **minúsculos** (`^[0-9a-f]{64}$`): `Artifact.sha256`, `ContextFile.sha256`, `Evidence.hash` (quando presente) e os `*_sha256` do receipt. Hash maiúsculo, curto ou não hexadecimal invalida o contrato que o contém.

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
Os valores ficam em `src/theforge/contracts/codes.py` e nunca mudam depois de publicados. A lista canônica e testada de códigos `FORGE-*` passa a ser `docs/errors.md`, criado pela spec `cross-forge-foundation`; quando ele existir, esta seção fica só com os códigos de manifest e um link para lá.

| Código | Causa |
|---|---|
| `FORGE-PROTO-SPAWN` | executável não encontrado ou sem permissão |
| `FORGE-PROTO-TIMEOUT` | sem resposta no tempo limite (árvore de processos encerrada) |
| `FORGE-PROTO-EXIT` | exit ≠ 0 (stderr redigido no detalhe) |
| `FORGE-PROTO-NOT-JSON` | stdout não é JSON |
| `FORGE-PROTO-OVERSIZE` | stdout > 8 MB |
| `FORGE-PROTO-SCHEMA` | envelope ou payload inválido, `kind` errado, status desconhecido, timestamp malformado ou fora de UTC |
| `FORGE-PROTO-MISMATCH` | `request_id` divergente |
| `FORGE-PROTO-OP-MISMATCH` | `op` da response diferente da op pedida |
| `FORGE-PROTO-OP-UNSUPPORTED` | a capability pedida é declarada por um provider roteável sem `execute` e nenhum outro provider poderia executá-la (`refused`, sem iniciar o processo) |
| `FORGE-PROTO-VERSION` | protocolo da response ≠ negociado |
| `FORGE-PROTO-PRODUCER` | `producer.id` ou `producer.version` diferente do provider invocado (envelope de describe, health ou execute, ou `ExecutionResult.producer`) |
| `FORGE-RESULT-DUP-EVIDENCE` | evidence com ID repetido |
| `FORGE-RESULT-DUP-FINDING` | finding com ID repetido |
| `FORGE-RESULT-DANGLING-EVIDENCE` | finding referencia evidence inexistente |
| `FORGE-RESULT-ARTIFACT-PATH` | `artifacts[].path` fora das regras de caminho |
| `FORGE-CONTEXT-BYTES` | ContextPack com `used_bytes` > `budget_bytes` ou ≠ soma dos arquivos (erro do core: o run sai com `FORGE-INTERNAL` e este código no detalhe) |
| `FORGE-CONTEXT-PATH` | arquivo do ContextPack fora das regras de caminho (erro do core, como acima) |
| `FORGE-RECEIPT-INVALID` | receipt inconsistente: hash fora do formato, timestamp inválido ou status `ok`/`partial` sem `result_sha256` igual ao hash do `result` gravado |
| `FORGE-REGISTRY-MANIFEST-CHANGED` | o manifest mudou de novo na revalidação feita depois de um re-routing |
| `FORGE-MANIFEST-LIMITS` | manifest ou capability acima dos limites, ou glob catch-all (aviso; capability ou provider excluído) |
| `FORGE-MANIFEST-VERSION` | `version` do manifest não é SemVer 2.0.0 (provider `invalid`) |
| `FORGE-MANIFEST-TAXONOMY` | capability, ação, alias ou `replaced_by` fora das regras mecânicas da taxonomia (aviso; capability excluída, provider `invalid` se nenhuma restar) |
| `FORGE-POLICY-APPROVAL-REQUIRED` | policy `ask` sem `--approve <capability>` (`refused`) |
| `FORGE-POLICY-DENIED` | policy `deny` (`refused`; aprovação não desbloqueia) |
| `FORGE-PROVIDER-NOT-READY` | provider não está `ready` no registry |
| `FORGE-PROVIDER-UNTRUSTED` | provider `unverified` não executado sem `--allow-unverified` |
| `FORGE-PROVIDER-BLOCKED` | provider com trust `blocked` nunca é executado |
| `FORGE-HEALTH-UNAVAILABLE` | health reporta `unavailable` |
| `FORGE-HEALTH-FAILED` | health respondeu com status ≠ ok |
| `FORGE-USAGE` | receipt de run que falhou por uso inválido |
| `FORGE-INTERNAL` | receipt de run que falhou por erro interno inesperado |

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
Os JSON Schemas ficam em `schemas/`. `RiskAssessment` v1 é o artefato `risk` do run (ver [security.md](security.md#policy-e-risco)). Nomes reservados (sem implementação): ExecutionPlan, VerificationResult, Budget, GraphNode, GraphEdge, InstallationPlan, DecisionRecord, WorkspaceDescriptor, EnvironmentReport (v0 não estável em `doctor`).
