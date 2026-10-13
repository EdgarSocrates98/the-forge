# Documentação — índice

Mapa dos documentos vivos de `docs/`, agrupados por preocupação. Fatos
históricos ficam em [adr/](adr/) (58 ADRs) e [reports/](reports/) (31
relatórios de ciclo); evidência medida em [reality/](reality/). Docs aqui
descrevem o sistema **como ele é** — quando divergir do código, o código
vence e o doc é consertado.

## Começar

- [architecture.md](architecture.md) — o sistema inteiro num diagrama + invariantes.
- [cli.md](cli.md) — referência dos verbos `theforge`; `--json`/`--root`/`--debug`.
- [feature-freeze.md](feature-freeze.md) — o que o freeze permite e proíbe.
- [dogfooding.md](dogfooding.md) — usando The Forge em projetos reais (fase atual).
- [release-checklist.md](release-checklist.md) — gates de release.
- [versioning.md](versioning.md) — o que se versiona (pacote, protocolo, contratos, adapters) + matriz de compatibilidade.

## Protocolo e contratos

- [protocol.md](protocol.md) — Forge Protocol v1: invocação, describe, health, execute.
- [capabilities.md](capabilities.md) — taxonomia e catálogo de capabilities.
- [errors.md](errors.md) — lista canônica dos códigos `FORGE-*`.
- [failure-semantics.md](failure-semantics.md) — cada modo de falha: código, detecção, propagação.
- [contract-stability.md](contract-stability.md) — scorecard de estabilidade dos contratos.
- [ontology.md](ontology.md) — vocabulário alinhado com Doctors e especialistas.
- `schemas/` — JSON schemas gerados de `src/theforge/contracts/` (não editar à mão).

## Registry e providers

- [real-providers.md](real-providers.md) — os seis especialistas e onde os adapters vivem.
- [provider-authoring.md](provider-authoring.md) — escrever um provider (qualquer linguagem).
- [registry-sources.md](registry-sources.md) — builtin / user / workspace, fronteiras de trust.
- [provider-distribution.md](provider-distribution.md) — Installation Plan v2: candidato remoto → instalado.
- [remote-discovery.md](remote-discovery.md) — descoberta de providers não instalados.
- [installation-orchestration.md](installation-orchestration.md) — o caminho governado de instalação.
- [security.md](security.md) — threat model, redaction, trust, limites do modelo.

## Execução e federação

- [execution-targets.md](execution-targets.md) — onde executar + classificação de dados.
- [cross-forge-orchestration.md](cross-forge-orchestration.md) — composição multi-especialista determinística.
- [trace-federation.md](trace-federation.md) — o trace cross-provider em `RunTelemetry.spans`.
- [global-stop.md](global-stop.md) — continuação cross-provider e stop conditions.
- [information-gain.md](information-gain.md) — estimativa qualitativa de evidência incremental.
- [validation-state-policy.md](validation-state-policy.md) — outcome de código ≠ estado de transporte de CI.

## Inteligência (aprendizado)

Memória verificável, não histórico: correlação nunca vira causa sem experimento.

- [engineering-memory.md](engineering-memory.md) — o que conta como conhecimento de engenharia.
- [economy-observations.md](economy-observations.md) — observações gravadas por execução.
- [context-roi.md](context-roi.md) — `ContextROI/v1` e recomendação de budget de contexto.
- [adaptive-strategy.md](adaptive-strategy.md) — shadow champion/challenger no routing.
- [adaptive-experiments.md](adaptive-experiments.md) — `StrategyExperiment/v1`: shadow → auditable.

## Instalação portátil

- [portable-installation/](portable-installation/README.md) — productização
  da família Forge: bootstrap, contrato v1, escopo × host × perfil, matriz
  de portabilidade e riscos.

## Camada agentic

- [agentic.md](agentic.md) — trabalhar no repo com agentes: hosts, mirrors, auditoria.
- [agentic-ecosystem.md](agentic-ecosystem.md) — como um agente de código enxerga e usa The Forge.
- [skills.md](skills.md) — as 16 skills canônicas `forge-*` (fonte → 3 hosts).
- [agents.md](agents.md) — os 8 AgentSpecs e o modelo de autoridade fechada.
- [forge-knowledge.md](forge-knowledge.md) — o que a plataforma sabe antes do especialista existir.
- [capability-negotiation.md](capability-negotiation.md) — negociação determinística requirement ↔ surface.
- [loop-factory.md](loop-factory.md) — specs dirigem, agentes implementam, humanos aceitam.
- [interoperability-mcp.md](interoperability-mcp.md) — papéis fixos: MCP server ↔ tools, The Forge ↔ providers.
- [a2a-bridge.md](a2a-bridge.md) — bridge A2A experimental.

## Evidência

- [performance.md](performance.md) — benchmark, baseline, budgets de regressão.
- [reports/](reports/) — relatórios de ciclo e fechamento (evidência histórica).
- [reality/](reality/) — manifest medido dos especialistas (`scripts/reality/collect.py`).
- [adr/](adr/) — decisões arquiteturais; fatos históricos não se reescrevem.
- [superpowers/](superpowers/) — spec do ciclo 1 (origem do design).
