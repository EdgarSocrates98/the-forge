# Forge Protocol v1

## Invocação
`<argv do provider> <op>`. O request JSON entra pelo stdin e a response JSON sai pelo stdout, um documento cada.

- Exit 0 sempre que houver uma response de protocolo válida, inclusive `refused`.
- Exit ≠ 0, stdout que não é JSON, stdout acima de 8 MB ou timeout são falhas de transporte (`provider_failure`).

## Ops
| Op | Obrigatória | Payload do request | Payload da response |
|---|---|---|---|
| `describe` | sim | `{}` | `ForgeManifest` |
| `health` | sim | `{}` | `HealthReport` (`ok\|degraded\|unavailable`) |
| `execute` | não | `ExecuteRequest{task, capability, action, context}` | `ExecutionResult` |
| `plan`, `verify`, `estimate` | reservadas | — | — |

O provider declara as ops que suporta em `describe.ops`.

## Envelopes
```json
{"protocol":"forge/v1","kind":"Request","op":"execute","request_id":"r_…","payload":{}}
```
```json
{"protocol":"forge/v1","kind":"Response","request_id":"r_…",
 "producer":{"id":"my-forge","version":"1.0.0"},
 "status":"ok|partial|refused|error","payload":{},
 "error":{"code":"…","detail":"…","field":null,"unlock":null},
 "limitations":[],"unknowns":[]}
```
- `request_id` precisa ecoar o do request.
- `error` é obrigatório quando o status é `refused` ou `error`.

## Versionamento
- `describe.protocols` lista os majors suportados; o core escolhe o maior em comum.
- Sem major em comum, o provider fica `incompatible` e sai do routing.
- Campos desconhecidos são ignorados (forward-compat dentro do major). Breaking change exige um novo major.
- Para qualquer op que não seja `describe`, o provider deve recusar requests com protocolo que não suporta.

## Códigos de erro do core
| Código | Causa |
|---|---|
| `FORGE-PROTO-SPAWN` | executável não encontrado ou sem permissão |
| `FORGE-PROTO-TIMEOUT` | sem resposta no tempo limite |
| `FORGE-PROTO-EXIT` | exit ≠ 0 (stderr redigido no detalhe) |
| `FORGE-PROTO-NOT-JSON` | stdout não é JSON |
| `FORGE-PROTO-OVERSIZE` | stdout > 8 MB |
| `FORGE-PROTO-SCHEMA` | envelope ou payload inválido |
| `FORGE-PROTO-MISMATCH` | `request_id` divergente |
| `FORGE-PROTO-VERSION` | protocolo da response ≠ negociado |
| `FORGE-PROTO-PRODUCER` | `result.producer` diferente do provider que foi chamado |
| `FORGE-PROVIDER-NOT-READY` | provider não está `ready` no registry |
| `FORGE-PROVIDER-UNTRUSTED` | provider `unverified` não executado sem `--allow-unverified` |
| `FORGE-PROVIDER-BLOCKED` | provider com trust `blocked` nunca é executado |
| `FORGE-HEALTH-UNAVAILABLE` | health reporta `unavailable` |
| `FORGE-HEALTH-FAILED` | health respondeu com status ≠ ok |
| `FORGE-USAGE` | receipt de run que falhou por uso inválido |
| `FORGE-INTERNAL` | receipt de run que falhou por erro interno inesperado |

## Contratos
Os JSON Schemas ficam em `schemas/`. Nomes reservados (sem implementação): ExecutionPlan, VerificationResult, Budget, RiskAssessment, GraphNode, GraphEdge, InstallationPlan, DecisionRecord, WorkspaceDescriptor, EnvironmentReport (v0 não estável em `doctor`).
