# Specialized Agents

Oito agentes especializados com autoridade fechada — delegam trabalho
bounded, nunca decisão.

## Registry

Specs canônicas em `agentic/agents/*.toml` (`AgentSpec/v1`), carregadas por
`src/theforge/agents.py`:

```text
$ theforge agents list                     # os oito, com autoridade
$ theforge agents show ecosystem-router    # uma spec (human ou --json)
```

| Agent | Autoridade | Faz | Nunca |
|---|---|---|---|
| `ecosystem-router` | propose | propõe `RoutingProposal` sobre o conjunto elegível | escolher fora dele, instalar, executar |
| `forge-discovery` | classify | classifica estado de instalação/surface | instalar, aprovar |
| `capability-negotiator` | propose | propõe plano de capacidades | executar, instalar |
| `bootstrap-installation` | execute-approved | constrói `InstallationPlanV2`; executa só com aprovação | verificar o próprio trabalho, aprovar |
| `cross-forge-planner` | propose | propõe composição multi-forge | executar, instalar |
| `execution-orchestrator` | execute-approved | coordena plano aprovado | aprovar, instalar |
| `verification-orchestrator` | propose | propõe verificação independente | produzir, instalar |
| `ecosystem-debugger` | advise | diagnóstico evidence-first | qualquer mutação |

## Autoridade

`authority` é literal fechado: `propose` · `classify` · `advise` ·
`execute-approved`. `UNIVERSAL_FORBIDDEN` (grant-trust, approve,
waive-verification, modify-registry) é parede construtiva — omitir quebra a
spec. `check_authority` aplica universal → forbidden da spec → teto da
classe. Detalhes: [ADR 0054](adr/0054-agent-authority-model.md).

## Hosts

Codex tem formato rastreado (`.codex/agents/*.toml`, renderizado por
`render_agents.py`). Claude lê agents do plugin (`.claude/agents/` é
gitignored); Devin usa `run_subagent`. `rendered_hosts` declara onde cada
spec vira arquivo — veja [ADR 0056](adr/0056-agentic-host-adaptation.md).

## Economia

`context_budget_bytes` (1 KiB–512 KiB) e `max_skills` bounded por construção —
nenhum agente recebe o repo inteiro por default. Consumo real vai para os
contadores `agent_*`/`skill_*`/`knowledge_bytes` do `RunTelemetry`.
