# Feature Freeze — Cycle 5.1

Declarado ao fechamento do Cycle 5.1 sobre `0.4.0`. O freeze formaliza o fim da
expansão arquitetural: The Forge entra em **DOGFOODING**, não em Cycle 6.

## Manifest

```yaml
freeze:
  cycle: "5.1"
  declared_on_version: "0.4.0"
  architecture: frozen
  contracts: stabilization        # additive evolution allowed; breaking needs ADR
  allowed_changes:
    - bugfix
    - security
    - compatibility               # specialist surface/version tracking
    - performance                 # regressions and hot-path work
    - docs                        # corrections, evidence, clarifications
    - test                        # coverage, determinism, adversarial
    - small_ux_cli                # corrections only — no new command surface
  prohibited_without_adr:
    - major_feature
    - new_subsystem
    - breaking_contract
    - new_orchestration_engine
    - remote_execution_transport
    - marketplace
    - distributed_runtime
    - new_memory_backend
    - new_graph_architecture
    - new_learning_architecture
    - scheduler_redesign
    - saas_plane
```

## O que o freeze permite

Corrigir, proteger e provar: bug fixes, security fixes, compatibilidade com
surfaces novas dos especialistas, regressões de performance, correções de
documentação, melhorias de teste e de evidência, pequenas correções de CLI/UX.

## O que o freeze proíbe sem ADR explícito

Novo subsistema de orquestração, transporte de execução remota, marketplace,
runtime distribuído, backend novo de memória, arquitetura nova de grafo ou de
aprendizado, scheduler novo, plano SaaS — e qualquer quebra de contrato
`stable candidate` ([versioning.md § Estabilidade](versioning.md#estabilidade-de-contratos-freeze-review)).

## Feature request gate (§73)

Durante o freeze uma feature nova só avança com evidência de dogfooding:

```text
problem observed repeatedly in dogfooding notes
or security requirement
or compatibility requirement
or critical usability blocker
```

`N` não é rígido — o princípio é **evidence before expansion**: uma observação
única de fricção é nota, não feature. Decisões de exceção passam por ADR.

## Onde observações vão

As observações de dogfooding seguem a taxonomia de
[dogfooding.md](dogfooding.md) — bug, friction,
missing capability, bad plan, unnecessary capability, slow path, bad memory
retrieval, bad graph relation, verification failure, compatibility drift,
unexpected cost, documentation gap. Observação nunca vira feature
automaticamente.
