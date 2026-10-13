# Agents & Skills

## Modelo

- **Agents**: especialistas com autoridade fechada — `propose`,
  `classify`, `advise`, `execute-approved` (the-forge AgentSpec/v1;
  `theforge agents list`). Delegam trabalho bounded, nunca decisão.
- **Skills**: procedimento versionado por domínio (`skills/<nome>/SKILL.md`
  + assets), renderizadas para os hosts.
- **Workflows**: passos executáveis declarados no `forge.agentic.json` de
  cada forja — é o que `forge task` delega.

## Onde estão

| Forja | Agents canônicos | Skills canônicas |
|---|---|---|
| the-forge | `agentic/agents/*.toml` (8 AgentSpec) | `scripts/agentic/render_skills.py` fontes |
| api-forge | `agents/*.md` (25 coordenadores, contrato de 9 seções) | `.claude/skills/api-forge-*` |
| spark-forge-aws | `agents/` | `skills/` (glue, EMR, Spark4, Iceberg…) |
| spark-forge-azure | `agents/` | skills azure (`sparkforge-azure-*`) |
| platform-forge | `platformforge/agents/roster.py` (41) | `.devin/skills/platformforge-*` |
| doctors | `forge.agentic.json` workflows | knowledge packs |

## Regras de ouro

1. Mirrors são gerados — nunca edite `.claude/`/`.agents/`/`.devin/`/
   `.codex/`/`.github/` diretamente.
2. Autoridade é literal: `UNIVERSAL_FORBIDDEN` quebra spec se omitida.
3. Routing por catálogo (`rules/catalog/routing.yaml`), não por escolha de
   skill "no olho".

## Fontes

`docs/AGENTS.md` (the-forge), `docs/adr/0054-agent-authority-model.md`,
`AGENTS.md` por forja, `docs/learn/` trilhas.
