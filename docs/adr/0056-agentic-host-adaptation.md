# ADR 0056 — Adaptação de assets agentic por host: canônico renderiza, auditoria vigia

- Status: aceito (2026-10-08)

## Contexto

O ADR 0020 decidiu mirrors manuais para as skills `kiro-*` até que um gatilho
disparasse. O prompt agentic adicionou 15 skills `forge-*` × 3 hosts + 8
specs de agentes — +45 mirrors a mão tornou a fonte canônica a opção mais
barata, não a mais cara. Ao mesmo tempo, os hosts são realmente diferentes:
Claude tem frontmatter `allowed-tools`, Codex usa envelope + `openai.yaml`,
Devin usa `run_subagent` em vez de arquivos de agente, e `.claude/agents/` é
gitignored (vem do plugin — renderizar lá produziria arquivo local
invisível).

## Decisão

- **Skills**: fonte canônica em `agentic/skills/*.md` (frontmatter `+++` TOML
  + corpo com blocos `<!-- host:x -->`). `scripts/agentic/render_skills.py`
  gera os três hosts; `--check` é gate de drift. O trailer
  `<!-- forge:freshness ... -->` liga cada mirror ao `tested_version` do
  pacote de conhecimento.
- **Agents**: fonte canônica `agentic/agents/*.toml` (`AgentSpec`). Codex
  tem formato rastreado em repo (`.codex/agents/*.toml`, renderizado por
  `render_agents.py`); Claude lê agents do plugin (`.claude/agents/` local);
  Devin usa profiles do harness (`run_subagent`). `rendered_hosts` declara
  onde cada spec vira arquivo — não fingimos formato que o host não tem.
- **Auditoria semântica, não byte**: `audit_assets.py` compara perfil
  semântico (skills, fases, paths, refs) entre hosts e trata diferenças
  justificadas como `host-only`/`accepted` declaradas em `agentic.toml`.
  `SKILL_QUALITY` vigia as fontes canônicas: descrição, seções de
  Boundaries/Limits, freshness vs. pacote, refs que resolvem.
- As `kiro-*` continuam manuais — a reavaliação do ADR 0020 cobriu só o que
  o gatilho pediu.

## Consequências

- 45 mirrors viraram 15 fontes + render; editar é mexer na fonte e rodar o
  renderer, nunca replicar à mão.
- Diferenças de host passam a ser declaradas e auditadas, não acidentais.
- Um host novo entra adicionando um renderer + entrada em `agentic.toml` —
  o canônico não muda.
