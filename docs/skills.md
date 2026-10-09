# Ecosystem Skills (`forge-*`)

16 skills canônicas que ensinam os hosts a usar a plataforma — renderizadas
por host, auditadas semanticamente.

## Fonte canônica

`agentic/skills/*.md` — frontmatter `+++` TOML + corpo com blocos
`<!-- host:claude|codex|devin -->` para diferenças justificadas. Edite a
fonte, nunca o mirror ([ADR 0056](adr/0056-agentic-host-adaptation.md)):

```bash
.venv/Scripts/python scripts/agentic/render_skills.py           # render
.venv/Scripts/python scripts/agentic/render_skills.py --check   # drift gate
```

Saídas: `.claude/skills/` (frontmatter `allowed-tools`/`argument-hint`),
`.agents/skills/` + `.devin/skills/` (envelope `<background_information>`/
`<instructions>`; Codex ganha `agents/openai.yaml` por skill).

## As 16

**Ecossistema** (10): `forge-ecosystem` (mapa das seis), `forge-routing`,
`forge-discovery`, `forge-capability-negotiation`,
`forge-cross-domain-planning`, `forge-install`, `forge-bootstrap`,
`forge-verification`, `forge-troubleshooting`, `forge-factory`.

**Especialistas** (6): `forge-spark-aws`, `forge-spark-azure`, `forge-api`,
`forge-platform`, `forge-doctor-data`, `forge-doctor-api` — cada uma diz
quando usar, quando **não** usar, e aponta `[freshness]` para o pacote de
conhecimento.

## Freshness

Cada render carrega `<!-- forge:freshness specialists=… version=… -->`. A
auditoria (`SKILL_QUALITY`) falha quando o `tested_version` da skill diverge
do pacote — skill stale é defeito detectável, não silêncio (§52, §78).

## Qualidade

`audit_assets.py` exige em cada fonte canônica: `name` == filename,
`description` não vazia (sem trigger, a skill nunca carrega sob demanda),
`## Overview` + `## Boundaries`/`## Limits`, e refs `$forge-x`/`/forge-x`
que resolvem para skill ou path rastreado. Menções em prosa (`forge-aws`
como família) não são invocações.

## O que não são

Não declaram capabilities — isso é do manifest do provider
([ADR 0053](adr/0053-skill-vs-capability.md)). Não são lidas pelo runtime.
