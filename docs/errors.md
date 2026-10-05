# Códigos de erro (`FORGE-*`)

Esta é a **lista canônica** dos códigos de erro de The Forge. Os valores ficam em `src/theforge/contracts/codes.py` (fonte única: nenhum literal `FORGE-*` existe fora dele) e o mapeamento código → família em `CODE_FAMILIES`, no mesmo módulo. Os testes de `tests/test_error_taxonomy.py` conferem que:

- todo código tem exatamente uma família, e a tabela abaixo é igual a `CODE_FAMILIES`;
- nenhum valor publicado muda: `tests/golden/forge_codes.json` congela os valores, e acrescentar um código exige atualizar o golden, `CODE_FAMILIES` e esta tabela no mesmo commit;
- todo código `FORGE-*` citado em outro documento existe aqui, com a mesma família.

Os demais documentos não mantêm tabela concorrente: apontam para esta página. [protocol.md](protocol.md#códigos-de-erro-do-core) só guarda uma tabela curta dos códigos de manifest e de pedido de contexto.

## Famílias

| Família | Abrange |
|---|---|
| `protocol` | transporte e respostas do Forge Protocol (spawn, timeout, JSON, schema, versão, producer, op) |
| `registry` | registry e regras de manifest (limites, SemVer, taxonomia de capabilities, revalidação) |
| `routing` | **sem códigos**: `ambiguous` e `no_route` são desfechos do routing, não erros |
| `plan` | planos multi-provider (validação, limites, arquivo de plano, dependências, estimativa) |
| `context` | ContextPack e negociação de contexto (`context_request`) |
| `provider` | elegibilidade, health e integridade do resultado do provider |
| `policy` | decisões da policy (`ask`/`deny`) |
| `persistence` | gravação, leitura e verificação de hashes dos runs (inclusive o receipt) |
| `security` | trust do provider (`blocked`, `unverified`) |
| `workspace` | descritor de workspace e grafo |
| `replay` | recusas de `replay` |
| `usage` | uso inválido da CLI ou do workspace |
| `internal` | erro interno inesperado |

Por que `routing` não tem códigos: um pedido que casa com mais de um especialista sem desempate termina `ambiguous`, e um que não casa com nenhum termina `no_route`. Os dois são respostas legítimas e determinísticas do routing (nunca um chute), com exit code próprio, e não falhas.

## Códigos

| Código | Família | Significado |
|---|---|---|
| `FORGE-PROTO-SPAWN` | protocol | executável não encontrado ou sem permissão |
| `FORGE-PROTO-TIMEOUT` | protocol | sem resposta no tempo limite (árvore de processos encerrada) |
| `FORGE-PROTO-EXIT` | protocol | exit ≠ 0 (stderr redigido no detalhe) |
| `FORGE-PROTO-NOT-JSON` | protocol | stdout não é JSON |
| `FORGE-PROTO-OVERSIZE` | protocol | stdout > 8 MB |
| `FORGE-PROTO-SCHEMA` | protocol | envelope ou payload inválido, `kind` errado, status desconhecido, timestamp malformado ou fora de UTC |
| `FORGE-PROTO-MISMATCH` | protocol | `request_id` divergente |
| `FORGE-PROTO-OP-MISMATCH` | protocol | `op` da response diferente da op pedida |
| `FORGE-PROTO-OP-UNSUPPORTED` | protocol | a capability pedida é declarada por um provider roteável sem `execute` e nenhum outro provider poderia executá-la (`refused`, sem iniciar o processo) |
| `FORGE-PROTO-VERSION` | protocol | protocolo da response ≠ negociado |
| `FORGE-PROTO-PRODUCER` | protocol | `producer.id` ou `producer.version` diferente do provider invocado (envelope de describe, health ou execute, ou `ExecutionResult.producer`) |
| `FORGE-REGISTRY-MANIFEST-CHANGED` | registry | o manifest mudou de novo na revalidação feita depois de um re-routing |
| `FORGE-MANIFEST-LIMITS` | registry | manifest ou capability acima dos limites, ou glob catch-all (aviso; capability ou provider excluído) |
| `FORGE-MANIFEST-VERSION` | registry | `version` do manifest não é SemVer 2.0.0 (provider `invalid`) |
| `FORGE-MANIFEST-TAXONOMY` | registry | capability, ação, alias ou `replaced_by` fora das regras mecânicas da taxonomia (aviso; capability excluída, provider `invalid` se nenhuma restar) |
| `FORGE-PLAN-INVALID` | plan | plano com ciclo, dependência inexistente, id duplicado, `inputs` fora de `depends_on`, ou regra estrutural do padrão violada — `delegate` proíbe `depends_on`/`inputs`; `debate` exige ≥2 `proposer` independentes e 1 `referee` que depende de todos e os declara em `inputs` (`refused`, nenhum nó executado) |
| `FORGE-PLAN-CAPABILITY` | plan | nó com provider que não está pronto ou que não declara a capability ou a ação (`refused`) |
| `FORGE-PLAN-LIMIT` | plan | nós ou providers distintos acima do limite (`refused`) |
| `FORGE-PLAN-PATTERN-RESERVED` | plan | valor de `pattern` fora dos cinco executáveis (`route`, `delegate`, `parallel`, `pipeline`, `debate`) (`refused`) |
| `FORGE-PLAN-FILE` | plan | arquivo de plano ilegível ou fora do contrato (erro de uso, exit 2) |
| `FORGE-PLAN-DEPENDENCY-FAILED` | plan | nó `skipped` porque um ancestral não produziu resultado válido |
| `FORGE-PLAN-ESTIMATE` | plan | a op `plan` do provider falhou (limitação no nó; o plano segue sem estimativa) |
| `FORGE-CONTEXT-BYTES` | context | ContextPack com `used_bytes` > `budget_bytes` ou ≠ soma dos arquivos (erro do core: o run sai com `FORGE-INTERNAL` e este código no detalhe) |
| `FORGE-CONTEXT-PATH` | context | arquivo do ContextPack fora das regras de caminho (erro do core, como acima) |
| `FORGE-CONTEXT-REQUEST-UNSUPPORTED` | context | `context_request` de uma capability que não declara `context.requests` (`provider_failure`) |
| `FORGE-CONTEXT-REQUEST-LIMIT` | context | `context_request` além das rodadas do perfil, inclusive qualquer pedido em `economy` (`provider_failure`) |
| `FORGE-CONTEXT-REQUEST-INVALID` | context | `context_request` com 0 itens ou mais de 64 (`provider_failure`) |
| `FORGE-PROVIDER-NOT-READY` | provider | provider não está `ready` no registry |
| `FORGE-HEALTH-UNAVAILABLE` | provider | health reporta `unavailable` |
| `FORGE-HEALTH-FAILED` | provider | health respondeu com status ≠ ok |
| `FORGE-RESULT-DUP-EVIDENCE` | provider | evidence com ID repetido |
| `FORGE-RESULT-DUP-FINDING` | provider | finding com ID repetido |
| `FORGE-RESULT-DANGLING-EVIDENCE` | provider | finding referencia evidence inexistente |
| `FORGE-RESULT-ARTIFACT-PATH` | provider | `artifacts[].path` fora das regras de caminho |
| `FORGE-RESULT-ARTIFACT-HASH` | provider | artifact em `work/` difere do hash declarado pelo provider (limitação; run `partial`) |
| `FORGE-POLICY-APPROVAL-REQUIRED` | policy | policy `ask` sem `--approve <capability>` (`refused`) |
| `FORGE-POLICY-DENIED` | policy | policy `deny` (`refused`; aprovação não desbloqueia) |
| `FORGE-RECEIPT-INVALID` | persistence | receipt inconsistente: hash fora do formato, timestamp inválido ou status `ok`/`partial` sem `result_sha256` igual ao hash do `result` gravado |
| `FORGE-PERSIST-WRITE` | persistence | falha ao gravar um run ou o estado do workspace (`theforge: persistence error:`, exit 5) |
| `FORGE-PERSIST-READ` | persistence | falha ao ler um artefato de run (ilegível ou não é objeto JSON; exit 5) |
| `FORGE-PERSIST-DIVERGENCE` | persistence | `explain` ou `replay --mode verify`/`render` encontrou hash persistido divergente (exit 6; a saída lista as divergências e o stderr traz a linha `theforge: integrity divergence: <n> artifact(s) diverge [FORGE-PERSIST-DIVERGENCE · persistence]`) |
| `FORGE-PROVIDER-UNTRUSTED` | security | provider `unverified` não executado sem `--allow-unverified` |
| `FORGE-PROVIDER-BLOCKED` | security | provider com trust `blocked` nunca é executado |
| `FORGE-WORKSPACE-CONFIG` | workspace | entrada inválida em `.forge/config/workspace.toml` (aviso; entrada ignorada, o run segue) |
| `FORGE-WORKSPACE-GRAPH-EDGE` | workspace | aresta do grafo rejeitada (sem evidência, extremidade inexistente ou inferida sem regra) |
| `FORGE-REPLAY-NOT-REPRODUCIBLE` | replay | `replay --mode execute` recusado: run não reproduzível ou `unknown`, contexto mudou ou provider mudou de identidade ou versão (nenhum provider executado; exit 4) |
| `FORGE-REPLAY-UNSUPPORTED` | replay | `replay --mode execute` de um run de plano (exit 4) |
| `FORGE-USAGE` | usage | run que falhou por uso inválido |
| `FORGE-INTERNAL` | internal | run que falhou por erro interno inesperado |

## Códigos nativos de providers

Códigos que não começam com `FORGE-` pertencem ao provider e passam intactos: `AF-*` (API Forge), `SPARKFORGE-*`, `APIFORGE-*` e `ADAPTER-*` (adapters reais). Eles **não têm família** (`family_of` devolve `None`) e são apresentados como código do provider, separados desta taxonomia. A convenção dos adapters está em [protocol.md](protocol.md#códigos-dos-adapters-reais).

## Apresentação na CLI
Toda mensagem de erro termina com `[<código> · <família>]` (código nativo: `[<código> · provider code]`), mantendo os prefixos `theforge: error:`, `theforge: persistence error:` e `theforge: internal error:`; nunca há traceback, e `--debug` mostra o diagnóstico redigido. Exit codes e exemplos em [cli.md](cli.md#mensagens-de-erro-e---debug); decisão em [ADR 0019](adr/0019-error-taxonomy-and-reproducibility.md).
