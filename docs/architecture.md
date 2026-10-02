# Arquitetura (ciclo 1)

```mermaid
flowchart TD
    U[usuário / host / CI] --> CLI[cli: theforge / forge]
    CLI --> F[forger: orquestrador]
    F --> R[registry: fontes, describe, cache, trust]
    F --> RT[routing: sinais determinísticos]
    F --> C[context: scan + Context Broker]
    F --> RS[runs: run store + receipts]
    R --> T[protocol: SubprocessTransport]
    F --> T
    T -->|"argv op, JSON stdin/stdout"| E[echo-forge]
    T --> S[Spark Forge adapter - ciclo 2]
    T --> A[API Forge adapter - ciclo 2]
```

## Fluxo de `ask`

```mermaid
sequenceDiagram
    participant CLI
    participant Forger
    participant Registry
    participant Provider
    CLI->>Forger: AskRequest
    Forger->>Forger: TaskSpec (persistido)
    Forger->>Registry: records()
    Forger->>Forger: route() -> RoutingDecision
    Forger->>Provider: health
    Forger->>Forger: ContextPack (persistido)
    Forger->>Provider: execute(task, capability, action, context)
    Provider-->>Forger: Response(ExecutionResult)
    Forger->>Forger: ExecutionResult + ExecutionReceipt (persistidos)
    Forger-->>CLI: AskOutcome
```

## Responsabilidades

| Módulo | Faz | Não faz |
|---|---|---|
| `contracts` | dataclasses v1, validação, JSON canônico, schemas | I/O |
| `protocol` | spawn, timeout, limite de stdout, validação do envelope | decidir rota |
| `registry` | carregar entradas, `describe`, negociar protocolo, cache, trust, health | executar tarefas |
| `routing` | ranquear capabilities por sinais declarados | conhecer domínios |
| `context` | listar arquivos com segurança, montar ContextPack por referência | ler conteúdo para o provider |
| `forger` | orquestrar um run, fallback de health, receipts | lógica de domínio |
| `runs` | persistir artefatos redigidos, hashes | interpretar resultados |
| `cli` | parsing, render, exit codes | lógica de negócio |

## Estado `.forge/`

| Dir | Classe | Git |
|---|---|---|
| `config/` | persistent | committable |
| `registry/` | cacheable | ignorado |
| `runs/<run_id>/` | persistent local | ignorado |
| `cache/` | ephemeral | ignorado |

## Fora do ciclo 1
Adapters reais (ciclo 2), LLM/semantic routing, multi-provider (parallel/pipeline/debate), economy avançada, installer, workspace graph.
