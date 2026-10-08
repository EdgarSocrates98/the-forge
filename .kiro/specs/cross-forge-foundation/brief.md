# Brief: cross-forge-foundation

## Problem
Contratos multi-provider reservados não existem; nenhum handoff estruturado entre providers; explain sem verificação de hashes; sem replay/debug; códigos de erro sem taxonomia formal.

## Current State
`RoutingDecision.pattern` só `route`; ExecutionPlan/VerificationResult/WorkspaceDescriptor/GraphNode/GraphEdge/InstallationPlan apenas na doc.

## Desired Outcome
ExecutionPlan DAG local determinístico, WorkspaceDescriptor multi-repo, grafo mínimo com evidência, VerificationResult, handoff estruturado e uma prova REAL Spark → API → síntese; explain completo/--json/verificação de hashes, taxonomia FORGE-*, --debug, níveis de reprodutibilidade.

## Approach
Ativar contratos reservados de forma compatível com Protocol v1; executor local sequencial; nada de scheduler distribuído.

## Scope
- **In**: requisitos semente abaixo (orig. Requirements 13, 14 de `cycle2-reality-hardening`, gerados em 2026-10-02 a partir de `prompt_evo_passo1.md` e auditoria do código).
- **Out**: tudo que pertence a outras specs do roadmap `.kiro/steering/roadmap.md`.

## Boundary Candidates
- Contratos multi-provider
- Executor de plano local
- Workspace/grafo mínimos
- Explain/erros/reprodutibilidade

## Out of Boundary
- Scheduler distribuído
- Graph engine/database
- Routing por LLM

## Upstream / Downstream
- **Upstream**: real-provider-integration, context-intelligence-v2
- **Downstream**: agentic-maintainability

## Existing Spec Touchpoints
- **Extends**: núcleo do Cycle 1 (`src/theforge/`)
- **Adjacent**: demais specs do Cycle 2 em `.kiro/steering/roadmap.md`

## Constraints
Runtime stdlib-only (Python >= 3.11, 0 deps runtime); integração só via Forge Protocol; routing determinístico; nenhum sucesso sem `ExecutionResult` válido; tudo persistido passa por `security.redact`; sem forge-kernel; sem conhecimento de domínio no core.

## Requirements Seed
Requisitos já revisados (EARS) a reaproveitar na fase de requirements; renumerar localmente.

### Seed 13 (orig. Requirement 13): Fundação de contratos multi-provider e prova cross-forge
**Objective:** As a usuário de The Forge, I want que uma tarefa híbrida seja decomposta e executada em sequência entre Spark Forge e API Forge com handoff estruturado, so that a coordenação entre especialistas seja comprovada sem orquestrador complexo.

#### Acceptance Criteria
1. The The Forge shall representar um `ExecutionPlan` como grafo acíclico com nós (papel, provider, capability, ação, entrada de contexto, entrada de artifacts) e dependências.
2. If um `ExecutionPlan` contém ciclo, dependência inexistente ou nó com provider sem a capability/ação declarada, The Forge shall rejeitar o plano antes de executar qualquer nó.
3. When um `ExecutionPlan` é executado, The Forge shall executar os nós localmente em ordem topológica determinística.
4. The The Forge shall manter compatibilidade com `RoutingDecision` v1 existente ao introduzir padrões multi-provider (route, delegate, parallel, pipeline, debate), sem quebra do Forge Protocol v1.
5. When um nó depende de outro, The Forge shall repassar ao nó dependente apenas evidências, findings, artifacts e decisões estruturados do nó anterior, nunca o texto integral da saída.
6. The The Forge shall preservar o status epistêmico (`confirmed`, `observed`, `inferred`, `proposed`, `unresolved`) de cada evidência ao longo do handoff e identificar o provider e o run de origem.
7. When a tarefa "Projete um pipeline Spark que produza dados para uma API" é submetida com perfil que permite multi-provider, The Forge shall decompor em nó de dados e nó de API, executar Spark Forge real, repassar evidência estruturada ao API Forge real e produzir síntese final.
8. If um nó falha, The Forge shall não executar nós dependentes e reportar o plano como parcial, com o nó e o motivo da falha.
9. The The Forge shall representar um `WorkspaceDescriptor` com raiz, repositórios, caminhos, HEAD, estado sujo, tecnologias detectadas e relações conhecidas, suportando workspace com múltiplos repositórios independentes sem assumir monorepo.
10. The The Forge shall representar `GraphNode` e `GraphEdge` mínimos em memória e como artifact JSON, em que toda aresta carrega a evidência de origem e o status epistêmico (`explicit`, `observed`, `inferred`), sem criar relações inferidas silenciosamente.
11. The The Forge shall produzir `VerificationResult` distinguindo auto-relato do provider, evidência do provider, verificação de The Forge e verificação independente, e nunca classificar auto-relato como verificação independente.
12. Where um provider declara a operação `plan`, The Forge shall poder obter antes da execução o contexto necessário, a classe de operação estimada, os artifacts esperados e as incógnitas; The Forge shall ativar as operações reservadas `plan` e `verify` somente quando houver caso de uso concreto neste ciclo.
13. The The Forge shall produzir no máximo um `InstallationPlan` somente de planejamento, sem baixar nem instalar nada.

### Seed 14 (orig. Requirement 14): Explicabilidade, erros e reprodutibilidade
**Objective:** As a usuário e automação, I want explicação completa e estável de cada run, taxonomia de erros consistente e diagnóstico controlado, so that eu entenda e automatize decisões de The Forge.

#### Acceptance Criteria
1. When `theforge explain <run>` é executado, The Forge shall mostrar, quando disponíveis: intenção, sinais, candidatos, provider selecionado, fallbacks, contexto, budget, versão do provider, contagem de evidências, findings, duração, limitações e incógnitas.
2. When `theforge explain <run> --json` é executado, The Forge shall emitir JSON com estrutura estável e documentada.
3. When `explain` é executado, The Forge shall verificar os hashes dos artifacts persistidos do run e indicar qualquer divergência.
4. The The Forge shall agrupar todos os códigos `FORGE-*` em uma taxonomia documentada (ex.: protocol, registry, routing, context, provider, policy, persistence, security, internal) sem códigos ad hoc fora dela.
5. The The Forge shall nunca exibir traceback bruto na CLI governada.
6. Where o modo debug é solicitado, The Forge shall exibir diagnóstico detalhado com redação de segredos aplicada.
7. The The Forge shall registrar em cada run um nível de reprodutibilidade (`reproducible`, `partially_reproducible`, `non_reproducible`, `unknown`) e nunca declarar `reproducible` quando o provider declarou ou teve acesso a sistema externo.
8. Where `replay` é oferecido, The Forge shall distinguir re-render, re-verify e re-execute e recusar re-execute quando as entradas não forem reproduzíveis.
