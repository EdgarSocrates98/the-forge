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

## Relatório

Resultados medidos da suíte A01–A15 e o veredicto do prompt agentic:
[reports/agentic-ecosystem.md](reports/agentic-ecosystem.md).
