# Índice de ADRs

Decisões de arquitetura de The Forge, uma por arquivo `NNNN-<slug>.md`. Cada ADR declara o status na linha `- Status:`. A numeração é única e não é reaproveitada; um ADR substituído continua no índice com o status atualizado.

| Número | Título | Status |
|---|---|---|
| 0001 | [Exec-protocol via subprocess em vez de imports ou MCP](0001-exec-protocol.md) | aceito (2026-10-02) |
| 0002 | [JSON e uma única convenção de schema](0002-json-single-schema-convention.md) | aceito (2026-10-02) |
| 0003 | [Python >= 3.11, stdlib-only em runtime](0003-python-stdlib-only.md) | aceito (2026-10-02) |
| 0004 | [Sem forge-kernel por enquanto](0004-no-forge-kernel-yet.md) | aceito (2026-10-02) |
| 0005 | [Routing determinístico primeiro, sem LLM no ciclo 1](0005-deterministic-routing-first.md) | aceito (2026-10-02) |
| 0006 | [Registry local e trust model](0006-local-registry-and-trust.md) | aceito (2026-10-02) |
| 0007 | [ContextPack por referência](0007-context-pack-by-reference.md) | aceito (2026-10-02) |
| 0008 | [Nome `theforge` com alias `forge`](0008-cli-name.md) | aceito (2026-10-02) |
| 0009 | [Cache do registry no diretório de cache do usuário](0009-registry-cache-location.md) | aceito (2026-10-03) |
| 0010 | [Modelo de policy e diferença concreta entre níveis de trust](0010-policy-model.md) | aceito (2026-10-03) |
| 0011 | [Matriz de suporte de CI: macOS e Python 3.14](0011-ci-support-matrix.md) | aceito (2026-10-03) |
| 0012 | [Sandbox de SO: pesquisa, sem dependência no ciclo](0012-os-sandbox-research.md) | aceito (2026-10-03) |
| 0013 | [Identidade local de provider](0013-provider-identity.md) | aceito (2026-10-03) |
| 0014 | [Local dos adapters dos Forges reais](0014-provider-adapter-location.md) | aceito (2026-10-04) |
| 0015 | [Inteligência de contexto: tiers, perfis, fingerprints e TOCTOU](0015-context-intelligence.md) | aceito (2026-10-04) |
| 0016 | [Sinais git somente leitura](0016-git-read-only-signals.md) | aceito (2026-10-04) |
| 0017 | [Taxonomia de capabilities](0017-capability-taxonomy.md) | aceito (2026-10-04) |
| 0018 | [Modelo de execução multi-provider](0018-multi-provider-execution.md) | aceito (2026-10-04) |
| 0019 | [Taxonomia de erros, reprodutibilidade e replay](0019-error-taxonomy-and-reproducibility.md) | aceito (2026-10-04) |
| 0020 | [Fonte canônica de assets agentic e política de hooks](0020-agentic-assets-canonical-source.md) | aceito (2026-10-04) |
| 0021 | [Verificação independente (`can_verify` + op `verify`)](0021-independent-verification.md) | aceito (2026-10-05) |
| 0022 | [Economia: RunBudget, promoção limitada e histórico medido](0022-economy-engine.md) | aceito (2026-10-05) |
| 0023 | [Inteligência de projeto: freshness computada, reuso por seção](0023-project-intelligence.md) | aceito (2026-10-05) |
| 0024 | [Trace local é um campo do RunTelemetry, não um segundo sistema](0024-local-trace-spans.md) | aceito (2026-10-05) |
| 0025 | [Resolver semântico como fallback de routing, nunca como router](0025-semantic-routing-fallback.md) | aceito (2026-10-07) |
| 0026 | [Perfil por avaliação de complexidade medida](0026-complexity-model.md) | aceito (2026-10-07) |
| 0027 | [Grafo de capabilities: relações declaradas + observadas](0027-capability-graph.md) | aceito (2026-10-07) |
| 0028 | [Planner híbrido: determinismo decompõe, semântica só desempata](0028-hybrid-planner.md) | aceito (2026-10-07) |
| 0029 | [Handoff como bus de evidência tipada](0029-evidence-bus.md) | aceito (2026-10-07) |
| 0030 | [Modos avançados de execução](0030-execution-modes.md) | aceito (2026-10-07) |
| 0031 | [Contratos compartilhados: schema repository agora](0031-shared-contracts.md) | aceito (2026-10-07) |
| 0032 | [A2A e MCP como superfícies opcionais, nunca substitutos](0032-external-protocol-interop.md) | aceito (2026-10-07) |

## Decisões exigidas pelo Cycle 2

O Cycle 2 exige que estas oito decisões estejam registradas. Cada uma aponta para o ADR que a registra e para a spec dona da decisão; um ADR exigido ausente é bloqueio da spec dona, nunca um ADR redigido por outra spec.

| Decisão | ADR | Spec dona |
|---|---|---|
| ownership dos adapters reais | [0014](0014-provider-adapter-location.md) | `real-provider-integration` |
| taxonomia de capabilities | [0017](0017-capability-taxonomy.md) | `real-provider-integration` |
| matriz de suporte de CI | [0011](0011-ci-support-matrix.md) | `cycle2-reality-hardening` |
| integridade de contexto | [0015](0015-context-intelligence.md) | `context-intelligence-v2` |
| local do cache do registry | [0009](0009-registry-cache-location.md) | `cycle2-reality-hardening` |
| modelo de execução multi-provider | [0018](0018-multi-provider-execution.md) | `cross-forge-foundation` |
| fonte canônica de assets agentic | [0020](0020-agentic-assets-canonical-source.md) | `agentic-maintainability` |
| verificação independente (`can_verify`, op `verify`) | [0021](0021-independent-verification.md) | `cycle-3` |
| orçamento auditável e desempate por histórico medido | [0022](0022-economy-engine.md) | `cycle-3` |
| inteligência de projeto e staleness explícito | [0023](0023-project-intelligence.md) | `cycle-3` |
| trace local dentro do artefato de telemetria | [0024](0024-local-trace-spans.md) | `cycle-3` |
| resolver semântico como fallback de routing | [0025](0025-semantic-routing-fallback.md) | `cycle-3` |
| perfil por avaliação de complexidade medida | [0026](0026-complexity-model.md) | `cycle-3` |
| grafo de capabilities declarado + observado | [0027](0027-capability-graph.md) | `cycle-3` |
| planner híbrido (tier-2 semântico limitado) | [0028](0028-hybrid-planner.md) | `cycle-3` |
| handoff como bus de evidência tipada | [0029](0029-evidence-bus.md) | `cycle-3` |
| modos avançados de execução e `DecisionRecord` | [0030](0030-execution-modes.md) | `cycle-3` |
| contratos compartilhados: schema repo, sem kernel | [0031](0031-shared-contracts.md) | `cycle-3.1` |
| A2A/MCP opcionais no nível do provider | [0032](0032-external-protocol-interop.md) | `cycle-3.1` |
| negociação de capability: dimensional, gated, sem score | [0033](0033-capability-negotiation-v2.md) | `cycle-4` |
| registry sources: abstração de origem, local autoritativo | [0034](0034-registry-sources.md) | `cycle-4` |
| remote registry client: read-only, cache verificado | [0035](0035-remote-registry-client.md) | `cycle-4` |
| remote discovery: fit honesto, sem instalação | [0036](0036-remote-discovery.md) | `cycle-4` |
| InstallationPlan v2: plano gated, execução fora do escopo | [0037](0037-installation-plan-v2.md) | `cycle-4` |
| modelo de policy | [0010](0010-policy-model.md) | `cycle2-reality-hardening` |

## Novo ADR

Use o próximo número livre, declare `- Status:` logo abaixo do título e acrescente a linha nesta tabela e, se o documento for novo em `docs/`, no índice do [README](../../README.md#documentação) no mesmo commit.
