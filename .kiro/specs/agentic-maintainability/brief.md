# Brief: agentic-maintainability

## Problem
Mirrors `.claude/.agents/.codex/.devin` mantidos à mão sem teste de drift; AGENTS.md sem invariantes do projeto; CLAUDE.md mistura regras do Forge com instruções Kiro extensas; ADRs/documentação precisam refletir o ciclo.

## Current State
17 skills kiro em 3 mirrors com diferenças de sintaxe por host; `.claude/commands/kiro` só no Claude; `.kiro/steering/` inexistente até este roadmap; arquivos soltos `(3` e `dict[str` na raiz.

## Desired Outcome
Teste de drift semântico entre hosts, invariantes em todos os hosts, CLAUDE.md curto, proposta de fonte canônica/plugin, documentação e ADRs consolidados e relatório final do Cycle 2.

## Approach
Auditar e testar antes de migrar; nenhuma migração grande sem benefício.

## Scope
- **In**: requisitos semente abaixo (orig. Requirements 16, 18 de `cycle2-reality-hardening`, gerados em 2026-10-02 a partir de `prompt_evo_passo1.md` e auditoria do código).
- **Out**: tudo que pertence a outras specs do roadmap `.kiro/steering/roadmap.md`.

## Boundary Candidates
- Teste de paridade de assets
- Instruções por host
- Documentação/ADRs/relatório final

## Out of Boundary
- Migração automática para plugin
- Mudanças no runtime

## Upstream / Downstream
- **Upstream**: Todas as specs anteriores (para relatório final e ADRs)
- **Downstream**: Próximo ciclo

## Existing Spec Touchpoints
- **Extends**: núcleo do Cycle 1 (`src/theforge/`)
- **Adjacent**: demais specs do Cycle 2 em `.kiro/steering/roadmap.md`

## Constraints
Runtime stdlib-only (Python >= 3.11, 0 deps runtime); integração só via Forge Protocol; routing determinístico; nenhum sucesso sem `ExecutionResult` válido; tudo persistido passa por `security.redact`; sem forge-kernel; sem conhecimento de domínio no core.

## Requirements Seed
Requisitos já revisados (EARS) a reaproveitar na fase de requirements; renumerar localmente.

### Seed 16 (orig. Requirement 16): Paridade e manutenção dos assets agentic
**Objective:** As a mantenedor, I want detectar drift entre hosts agentic e reduzir o contexto sempre carregado, so that Claude, Codex, Devin e demais hosts sigam as mesmas regras sem custo de tokens desnecessário.

#### Acceptance Criteria
1. The The Forge shall auditar `.claude/`, `.agents/`, `.codex/` e `.devin/` e reportar drift relevante entre skills equivalentes.
2. The The Forge shall ter teste que falhe quando o conteúdo semanticamente compartilhável de skills equivalentes divergir entre hosts, tolerando diferenças de sintaxe específicas de host.
3. The The Forge shall garantir que as invariantes do projeto (stdlib-only, integração só via protocolo, routing determinístico, redação, regeneração de schemas, comandos de teste) estejam presentes nas instruções de todos os hosts suportados.
4. The The Forge shall reduzir o CLAUDE.md a regras persistentes curtas, movendo detalhes de workflow redundantes para skills ou documentação sem perda de comportamento.
5. The The Forge shall produzir proposta, sem migração automática, de fonte canônica de assets agentic e de empacotamento como plugin, mantendo o runtime independente.
6. Where hooks forem adicionados ao workflow de desenvolvimento, The Forge shall restringi-los a checagens focadas e determinísticas (lint focado, testes relevantes, paridade de schema), nunca à suíte completa a cada edição.

### Seed 18 (orig. Requirement 18): Documentação e decisões arquiteturais
**Objective:** As a mantenedor e autor de provider, I want documentação e ADRs atualizados quando o comportamento muda, so that as decisões do ciclo sejam rastreáveis.

#### Acceptance Criteria
1. When o comportamento de protocol, segurança, CLI, contexto ou routing muda, The Forge shall atualizar README, arquitetura, protocolo, guia de autoria de provider, segurança e CLI correspondentes.
2. The The Forge shall registrar ADRs para: ownership de adapters reais, taxonomia de capabilities, matriz de suporte de CI, integridade de contexto, local do cache do registry, modelo de execução multi-provider, fonte canônica de assets agentic e modelo de policy.
3. The The Forge shall documentar `theforge` como nome canônico da CLI e `forge` como alias de conveniência.
4. When um contrato muda, The Forge shall regenerar os schemas publicados e manter o teste de paridade de schemas passando.
5. The The Forge shall produzir relatório final do ciclo com: implementado, mudanças de arquitetura, integração real Spark/API, melhorias de contexto/economy, hardening de segurança, CI, prova cross-forge, resultados medidos, limitações, adiamentos intencionais e próximo ciclo recomendado.
