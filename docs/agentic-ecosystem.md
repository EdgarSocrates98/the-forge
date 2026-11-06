# Agentic Ecosystem

Como um agente de código (Claude Code, Codex, Devin) enxerga e usa The
Forge — a camada agentic inteira, num mapa.

## Peças

| Peça | Onde | Decisão |
|---|---|---|
| Conhecimento de bootstrap | `forge-knowledge/*.json` + `theforge knowledge` (`check` = freshness vs. registry ao vivo) | [ADR 0052](adr/0052-forge-knowledge-layer.md) · [doc](forge-knowledge.md) |
| Skills de ecossistema | `agentic/skills/` → `.claude/` `.agents/` `.devin/` | [ADR 0053](adr/0053-skill-vs-capability.md) · [doc](skills.md) |
| Agentes especializados | `agentic/agents/` → `.codex/agents/` | [ADR 0054](adr/0054-agent-authority-model.md) · [doc](agents.md) |
| Auditoria de assets | `scripts/agentic/audit_assets.py` + `agentic.toml` | [ADR 0056](adr/0056-agentic-host-adaptation.md) · [doc](agentic.md) |
| Telemetria agentic | `RunTelemetry` (`agent_calls`, `skills_loaded`, …) | [arquitetura](architecture.md#telemetria) |

## Fluxo de uma tarefa

```text
tarefa ──► skills forge-* carregam sob demanda (description é o gatilho)
       ──► route() determinístico decide provider
       ──► no_route? forge-knowledge diz como instalar
       ──► plano → aprovação humana → execução governada
       ──► doctor/verificador independente confere a saída
       ──► telemetry conta o que a camada agentic consumiu
```

## Invariantes da camada

- Conhecimento estático é bootstrap, nunca verdade de runtime.
- Skill ensina workflow; capability é do manifest. Nunca as duas.
- Autoridade de agente é fechada; aprovação e trust são gates humanos.
- Mirrors são gerados de fonte canônica; diferenças de host são declaradas.
- Métricas não medidas ficam `unknown` — nunca `0` ([docs/agents.md](agents.md)).

## Vocabulário e limites

| Termo | Significado operacional | Fonte canônica |
|---|---|---|
| especialista | Forge/provider que oferece uma capability; não é o mesmo que uma skill ou um agente host | [discovery.md](discovery.md) |
| agente especializado | `AgentSpec/v1` com autoridade fechada, skills e contratos permitidos | [agents.md](agents.md), ADR 0054 |
| analisador determinístico | ferramenta do provider que transforma artefatos em facts/findings reproduzíveis | [ontology.md](ontology.md) |
| contrato de evidência | payload tipado com proveniência, estado e limitações; não é uma promessa textual | [delegation.md](delegation.md) |
| control plane | The Forge: descobre, negocia, roteia, governa e persiste receipts; não contém conhecimento Spark/API | [architecture.md](architecture.md) |
| bridge/adaptador | fronteira subprocesso + JSON entre The Forge e o interpretador do provider | [protocol.md](protocol.md) |
| operação | verbo concreto de um provider, sujeito a capability, trust, approval e policy | [capabilities.md](capabilities.md) |
| MCP tool | ferramenta de interoperabilidade; não é provider nem autoridade de routing | [interoperability-mcp.md](interoperability-mcp.md) |

## Contrato resolvido do ecossistema

O mapa abaixo nomeia uma única autoridade por responsabilidade. O catálogo e o
Portal apenas projetam as respostas dessas autoridades:

| Responsabilidade | Autoridade | Projeção/limite |
|---|---|---|
| identidade, autoridade e contratos do agente | `theforge/AgentSpec/v1` | hosts podem renderizar; não podem ampliar `forbidden`/budget |
| manifesto e workflows do Forge | `forge/SpecialistAgenticManifest/v1` | declarativo; não concede trust nem prova roster |
| roster nativo | checkout do provider + `inspect_roster` | `CONFORMANT`, `DRIFT`, `STALE`, `CONFLICT` ou `UNKNOWN`; nunca capability implícita |
| lifecycle/instalação/health | registry, discovery e `SpecialistLifecycle` | o catálogo carrega fonte, frescor e evidência sem reescrever o lifecycle |
| task, aprovação, execução, eventos e receipt | task/run contracts existentes | “Nova investigação” é uma entrada em `/tasks`, não uma segunda máquina de estados |
| facts/findings do domínio | provider especialista | The Forge transporta e governa; não interpreta conhecimento Spark/API |

## Catálogo e routing

Uma linha federada deve ser lida em dimensões independentes: declaração,
instalação, trust, disponibilidade, frescor e health. `agent_roster` é
evidência adicional, não substituto dessas dimensões. Metadado de bootstrap,
checkout ausente ou provider sem histórico pode aparecer como `UNKNOWN`, mas
não satisfaz um gate.

Routing aplica gates duros de capability negociada, policy/trust, ambiente,
estado e health. Adequação parcial, frescor e histórico medido são sinais para
explicação/ranking; histórico ausente não bloqueia cold start, mas pode exigir
verificação independente mais forte. Conflito ou evidência insuficiente produz
`ambiguous`, `no_route`, `BLOCKED` ou `UNKNOWN` conforme o contrato, nunca um
chute ou promoção silenciosa.

## Jornada de investigação

```text
intent
  → /tasks/plan (plano imutável, escopo de aprovação e expiração)
  → revisão/aprovação humana
  → /tasks/execute (task id + plan token + policy)
  → eventos/receipt/resultados
  → evidência, unknowns e próxima ação
```

O task id, correlation id, receipt e eventos existentes são a fonte de
identidade e replay. `refused`, `failed`, `partial`, `cancelled`,
`telemetry_unavailable` e `unknown` permanecem estados honestos; retry,
reconexão e regeneração usam a mesma tarefa/receipt ou um plano explicitamente
novo. Nenhuma dessas situações autoriza credencial, instalação ou mutação
externa sem o capability gate correspondente.

No Portal, o botão “Nova investigação” só abre `/tasks?new=1` e foca o intent.
Ele não planeja nem executa por conta própria. A aceitação browser está em
`forge-portal/e2e/test_browser_e2e.py`; o alias de query é testado no
`TasksPage`.

## Evidência Spark

O caminho local executável, hashes, oracle positivo/negativo, comportamento
`UNRESOLVED`/`BLOCKED` e os estados `PREPARED`, `REPLAY_VERIFIED`,
`LIVE_EXECUTED` e `INDEPENDENTLY_VERIFIED` estão em
`spark-forge-aws/docs/golden-paths/spark-diagnostic.json`. Replay verificado
prova apenas a fixture e o analisador local. Sem receipt própria, live e
verificação independente continuam `NOT_RUN`.

Orçamento e telemetria seguem [ADR 0064](adr/0064-agentic-operational-safety-and-evidence.md):
unidades não medidas ficam `unknown`, hard stops são aplicados pelo executor e
provider sem spans fica `partial_trace`/`telemetry_unavailable`.

## Relatório

Resultados medidos da suíte A01–A15 e o veredicto do prompt agentic:
[reports/agentic-ecosystem.md](reports/agentic-ecosystem.md).
