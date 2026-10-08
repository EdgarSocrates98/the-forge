# Brief: context-intelligence-v2

## Problem
Context Broker atual seleciona só por globs + budget em bytes; sem git, sem cache, sem revalidação pós-execução; perfis economy/balanced/max diferem apenas em bytes e timeout.

## Current State
`context/broker.py` budgets 64KiB/256KiB/1MiB; `.forge/cache/` criado e não usado; echo provider revalida sha; sem métricas; sem baseline de performance.

## Desired Outcome
Tiers de contexto, sinais git read-only, cache de fingerprints mensurável e correto, estratégia TOCTOU documentada no protocolo, bytes≠tokens, perfis materialmente diferentes, telemetria por run, baseline de performance medido antes de otimizar.

## Approach
Evoluir o broker existente sem abandonar o mecanismo barato; cache sempre conservador (qualquer sinal de mudança → rehash).

## Scope
- **In**: requisitos semente abaixo (orig. Requirements 11, 12, 17 de `cycle2-reality-hardening`, gerados em 2026-10-02 a partir de `prompt_evo_passo1.md` e auditoria do código).
- **Out**: tudo que pertence a outras specs do roadmap `.kiro/steering/roadmap.md`.

## Boundary Candidates
- Seleção/explicação de contexto
- Sinais git read-only
- Cache de fingerprints
- Perfis de economy e telemetria
- Benchmarks

## Out of Boundary
- Embeddings/LLM
- Execução multi-provider (pertence a cross-forge-foundation)

## Upstream / Downstream
- **Upstream**: cycle2-reality-hardening (validação de ContextPack, contratos)
- **Downstream**: cross-forge-foundation

## Existing Spec Touchpoints
- **Extends**: núcleo do Cycle 1 (`src/theforge/`)
- **Adjacent**: demais specs do Cycle 2 em `.kiro/steering/roadmap.md`

## Constraints
Runtime stdlib-only (Python >= 3.11, 0 deps runtime); integração só via Forge Protocol; routing determinístico; nenhum sucesso sem `ExecutionResult` válido; tudo persistido passa por `security.redact`; sem forge-kernel; sem conhecimento de domínio no core.

## Requirements Seed
Requisitos já revisados (EARS) a reaproveitar na fase de requirements; renumerar localmente.

### Seed 11 (orig. Requirement 11): Context Intelligence v2
**Objective:** As a usuário de The Forge, I want que o contexto entregue ao provider seja o mais barato suficiente, explicável e íntegro, so that providers recebam o que precisam sem desperdício nem conteúdo divergente.

#### Acceptance Criteria
1. The The Forge shall classificar o contexto em tiers (metadados, referências a arquivos, trechos/estruturas relevantes, pedido explícito do provider) e preferir sempre o tier mais barato suficiente.
2. The The Forge shall explicar, para cada arquivo incluído ou excluído, o motivo da seleção ou exclusão.
3. Where o workspace é um repositório git e git está disponível, The Forge shall considerar branch atual, HEAD, arquivos alterados e status como sinais de relevância, sem executar nenhuma operação que modifique o repositório.
4. If git não está disponível ou o workspace não é repositório, The Forge shall operar sem sinais de git e registrar a limitação.
5. The The Forge shall considerar como sinais de relevância, além de globs: arquivos de dependência, alvos explícitos da tarefa e referências explícitas a caminhos na tarefa, sem uso de embeddings ou LLM por padrão.
6. When nada mudou desde a seleção anterior, The Forge shall reutilizar fingerprints de arquivos sem recalcular o hash de conteúdo, e nunca reutilizar um fingerprint quando qualquer evidência de mudança for detectada.
7. The The Forge shall registrar métricas de contexto por run: arquivos varridos, arquivos hasheados, bytes hasheados, acertos e faltas de cache e duração da seleção.
8. If um arquivo do ContextPack muda entre a geração do hash e a leitura pelo provider, The Forge shall tornar a divergência explícita no resultado do run e não tratar como confirmada a evidência derivada daquele arquivo.
9. The The Forge shall definir e documentar no protocolo e no guia de autoria de providers a obrigação de revalidar o hash do conteúdo lido ou a estratégia alternativa adotada.
10. The The Forge shall reportar orçamento de contexto em bytes medidos e reportar tokens como `measured`, `estimated` ou `unknown`, usando `unknown` quando não houver estimativa.
11. Where o provider declara suporte a pedido de contexto adicional, The Forge shall validar o pedido contra policy e budget e limitar a negociação a um número fixo de rodadas.

### Seed 12 (orig. Requirement 12): Perfis de economy e telemetria
**Objective:** As a usuário de The Forge, I want que os perfis economy, balanced e max produzam comportamento materialmente diferente e medido, so that eu controle custo e profundidade de forma previsível.

#### Acceptance Criteria
1. While o perfil é `economy`, The Forge shall usar apenas resolução determinística, contexto pequeno, um único provider e verificação mínima.
2. While o perfil é `balanced`, The Forge shall usar contexto determinístico expandido e verificação condicional.
3. While o perfil é `max`, The Forge shall permitir contexto maior, execução multi-provider quando o plano exigir e verificação forte.
4. The The Forge shall ter testes que provem diferença observável entre os três perfis em budget de contexto, número máximo de providers e nível de verificação.
5. The The Forge shall registrar por run: duração de varredura, routing, contexto e provider; arquivos varridos e selecionados; bytes de contexto; acertos/faltas de cache; número de providers e de fallbacks.

### Seed 17 (orig. Requirement 17): Baseline de performance
**Objective:** As a mantenedor, I want medir performance antes de otimizar, so that budgets de regressão sejam baseados em dados.

#### Acceptance Criteria
1. The The Forge shall medir e registrar baseline de: startup da CLI, registry com e sem cache, varredura de 1k e 10k arquivos, routing, geração de ContextPack e persistência de run, sem dependência de runtime adicional.
2. The The Forge shall definir budgets de regressão somente após o baseline medido e documentar os valores e a origem.
