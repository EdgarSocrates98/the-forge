# Matriz de Aceite — FASE 0 (baseline observado)

Gerado de `docs/experience/audit-fase0.json` (audit 2026-10-11T01:57:42+00:00).
Estados: **SUPPORTED** (evidência no audit), **PARTIAL**, **UNSUPPORTED**,
**UNVERIFIED** (sem evidência de comportamento — não confundir com ausente),
**NOT_APPLICABLE**. Célula nunca é preenchida por existência de arquivo solto.

| capacidade \ forja | alvo do programa | the-forge | api-forge | spark-forge-aws | spark-forge-azure | platform-forge | forge-doctor-data | forge-doctor-api |
|---|---|---|---|---|---|---|---|---|
| `install.lifecycle` | status/doctor/plan honestos | SUPPORTED<br><sub>superfície install/</sub> | SUPPORTED<br><sub>superfície install/</sub> | SUPPORTED<br><sub>superfície install/</sub> | SUPPORTED<br><sub>superfície install/</sub> | SUPPORTED<br><sub>superfície install/</sub> | SUPPORTED<br><sub>superfície install/</sub> | UNSUPPORTED<br><sub>sem superfície install</sub> |
| `cli.agentic` | verbos descobrem agents/skills | SUPPORTED<br><sub>41 recursos agentic</sub> | SUPPORTED<br><sub>45 recursos agentic</sub> | SUPPORTED<br><sub>79 recursos agentic</sub> | SUPPORTED<br><sub>62 recursos agentic</sub> | SUPPORTED<br><sub>53 recursos agentic</sub> | PARTIAL<br><sub>0 recursos agentic</sub> | PARTIAL<br><sub>0 recursos agentic</sub> |
| `tui.entries` | entradas reais, DocMeta, sem botão falso | SUPPORTED<br><sub>8 arquivos ui/</sub> | SUPPORTED<br><sub>8 arquivos ui/</sub> | SUPPORTED<br><sub>8 arquivos ui/</sub> | SUPPORTED<br><sub>8 arquivos ui/</sub> | SUPPORTED<br><sub>8 arquivos ui/</sub> | SUPPORTED<br><sub>8 arquivos ui/</sub> | SUPPORTED<br><sub>8 arquivos ui/</sub> |
| `mcp.surface` | tools declaradas + handshake | UNSUPPORTED<br><sub>sem mcp/</sub> | UNVERIFIED<br><sub>módulo mcp/ existe, tools não contadas</sub> | SUPPORTED<br><sub>146 tools no lock</sub> | UNVERIFIED<br><sub>módulo mcp/ existe, tools não contadas</sub> | UNVERIFIED<br><sub>módulo mcp/ existe, tools não contadas</sub> | UNVERIFIED<br><sub>módulo mcp/ existe, tools não contadas</sub> | UNVERIFIED<br><sub>módulo mcp/ existe, tools não contadas</sub> |
| `graph.surface` | projeção consumível | SUPPORTED<br><sub>graphview/knowledge detectado</sub> | SUPPORTED<br><sub>graphview/knowledge detectado</sub> | SUPPORTED<br><sub>graphview/knowledge detectado</sub> | SUPPORTED<br><sub>graphview/knowledge detectado</sub> | SUPPORTED<br><sub>graphview/knowledge detectado</sub> | SUPPORTED<br><sub>graphview/knowledge detectado</sub> | SUPPORTED<br><sub>graphview/knowledge detectado</sub> |
| `agents.catalog` | catálogo didático §11 | SUPPORTED<br><sub>8 agents canônicos</sub> | SUPPORTED<br><sub>31 agents canônicos</sub> | SUPPORTED<br><sub>19 agents canônicos</sub> | SUPPORTED<br><sub>40 agents canônicos</sub> | SUPPORTED<br><sub>41 agents canônicos</sub> | UNSUPPORTED<br><sub>0 agents canônicos</sub> | UNSUPPORTED<br><sub>0 agents canônicos</sub> |
| `skills.catalog` | skills canônicas + triggers | SUPPORTED<br><sub>33 skills em .agents/skills,.claude/skills,.devin/skills</sub> | SUPPORTED<br><sub>14 skills em .github/skills</sub> | SUPPORTED<br><sub>60 skills em skills</sub> | SUPPORTED<br><sub>22 skills em skills</sub> | SUPPORTED<br><sub>12 skills em .devin/skills</sub> | UNSUPPORTED<br><sub>0 skills em —</sub> | UNSUPPORTED<br><sub>0 skills em —</sub> |
| `mirrors.sync` | espelhos == render(canônico) | SUPPORTED<br><sub>108 arquivos espelho</sub> | SUPPORTED<br><sub>136 arquivos espelho</sub> | SUPPORTED<br><sub>190 arquivos espelho</sub> | SUPPORTED<br><sub>85 arquivos espelho</sub> | SUPPORTED<br><sub>176 arquivos espelho</sub> | UNSUPPORTED<br><sub>0 arquivos espelho</sub> | SUPPORTED<br><sub>1 arquivos espelho</sub> |
| `tests.suite` | suíte verde em main | SUPPORTED<br><sub>158 arquivos de teste</sub> | SUPPORTED<br><sub>349 arquivos de teste</sub> | SUPPORTED<br><sub>494 arquivos de teste</sub> | SUPPORTED<br><sub>274 arquivos de teste</sub> | SUPPORTED<br><sub>105 arquivos de teste</sub> | SUPPORTED<br><sub>199 arquivos de teste</sub> | SUPPORTED<br><sub>87 arquivos de teste</sub> |

## Leituras honestas do baseline

- **the-forge** v0.5.0: 8 agents, 33 skills, 108 espelhos, 158 arquivos de teste — superfícies agentic presentes.
- **api-forge** v0.1.0: 31 agents, 14 skills, 136 espelhos, 349 arquivos de teste — superfícies agentic presentes.
- **spark-forge-aws** v0.5.0: 19 agents, 60 skills, 190 espelhos, 494 arquivos de teste — superfícies agentic presentes.
- **spark-forge-azure** v0.1.0: 40 agents, 22 skills, 85 espelhos, 274 arquivos de teste — superfícies agentic presentes.
- **platform-forge** v0.1.0: 41 agents, 12 skills, 176 espelhos, 105 arquivos de teste — superfícies agentic presentes.
- **forge-doctor-data** v1.0.0rc1: 0 agents, 0 skills, 0 espelhos, 199 arquivos de teste — sem agents canônicos; sem skills canônicas; sem espelhos de host.
- **forge-doctor-api** v0.2.0: 0 agents, 0 skills, 1 espelhos, 87 arquivos de teste — sem agents canônicos; sem skills canônicas.

> Regenerar: `python scripts/experience/gen_acceptance_matrix.py`
> (roda `audit_surfaces.py` antes se o inventário mudou).
