# Forge Ecosystem — Portal de Documentação (§10.5)

> **The Forge é um ecossistema modular de ferramentas de engenharia agentic
> que conecta agentes, skills, MCPs e motores especializados para ajudar
> profissionais a analisar, construir e evoluir soluções técnicas com
> contexto controlado e evidências verificáveis.** (§10.6)

Não somos substituto do conhecimento técnico — demonstramos como a IA
amplia capacidades profissionais **dentro de limites verificáveis**.

Este portal **aponta para as fontes oficiais** de cada projeto — não
duplica manuais. Cada linha abaixo leva ao documento canônico que o
próprio repositório mantém.

## As 18 seções

| # | Seção | Fonte canônica |
|---|---|---|
| 1 | Introdução | [Visão geral do onboarding](../onboarding/README.md) · [README do the-forge](https://github.com/EdgarSocrates98/the-forge/blob/main/README.md) |
| 2 | Arquitetura | [Arquitetura do control plane](../architecture.md) · [ADR index](../adr/README.md) |
| 3 | Catálogo de Forjas | [Which Forge](../hub/which-forge.md) — gerado dos manifests reais |
| 4 | Comparativo de capacidades | [Matriz de compatibilidade](../programs/ecosystem-2026/compatibility-matrix.md) · [capabilities.md](../capabilities.md) |
| 5 | Instalação | [Onboarding da família](../installation/family-onboarding.md) · [Quickstart](../installation/quickstart.md) · [EN](../installation/quickstart.en.md) |
| 6 | Host setup | [Agentic hosts](../agentic.md) — Devin, Claude, Codex, Copilot |
| 7 | Skills | [Skills](../skills.md) |
| 8 | Agents | [Agents](../agents.md) — autoridade fechada por spec |
| 9 | MCP | [Interoperabilidade MCP](../interoperability-mcp.md) · [real providers](../real-providers.md) |
| 10 | CLI | [Referência do CLI](../cli.md) · [commands.md](../reference/commands.md) — gerado do parser |
| 11 | Portal | [Forge Portal](https://github.com/EdgarSocrates98/forge-portal/blob/main/README.md) · `theforge portal` |
| 12 | Graph Studio | [Graph Studio quickstart](../graph-studio/quickstart.md) · [arquitetura](../graph-studio/architecture.md) |
| 13 | Forge Lab | [Metodologia de benchmarks](../programs/ecosystem-2026/benchmarks/methodology.md) · `theforge lab --help` |
| 14 | Contratos | [Estabilidade de contratos](../contract-stability.md) · [schemas/](../../schemas/) |
| 15 | Troubleshooting | [Taxonomia de erros](../errors.md) · [Troubleshooting por guia](../onboarding/getting-started/) |
| 16 | FAQ | [FAQ do ecossistema](faq.md) |
| 17 | Exemplos | [Golden Paths](../onboarding/golden-paths/) · [Getting Started](../onboarding/getting-started/) |
| 18 | Contribuição | [CONTRIBUTING.md](https://github.com/EdgarSocrates98/the-forge/blob/main/CONTRIBUTING.md) · [Releases](releases.md) |

## Fontes oficiais por Forja

| Forja | Domínio | Docs oficiais |
|---|---|---|
| the-forge | control plane (WHO/WHEN/HOW) | [docs/](../INDEX.md) |
| forge-cli | CLI/compat | [README](https://github.com/EdgarSocrates98/forge-cli/blob/main/README.md) |
| forge-portal | UI local | [README](https://github.com/EdgarSocrates98/forge-portal/blob/main/README.md) |
| api-forge | engenharia de API | [README](https://github.com/EdgarSocrates98/api-forge/blob/main/README.md) · [PT](https://github.com/EdgarSocrates98/api-forge/blob/main/README.pt-BR.md) |
| platform-forge | plataforma/infra | [README](https://github.com/EdgarSocrates98/platform-forge/blob/main/README.md) · [PT](https://github.com/EdgarSocrates98/platform-forge/blob/main/README.pt-BR.md) |
| spark-forge-aws | data engineering AWS | [README](https://github.com/EdgarSocrates98/spark-forge-aws/blob/main/README.md) |
| spark-forge-azure | data engineering Azure | [README](https://github.com/EdgarSocrates98/spark-forge-azure/blob/main/README.md) |
| forge-doctor-data | diagnóstico data | [README](https://github.com/EdgarSocrates98/forge-doctor-data/blob/main/README.md) |
| forge-doctor-api | diagnóstico API | [README](https://github.com/EdgarSocrates98/forge-doctor-api/blob/main/README.md) |

## Regras deste portal

- Nada de badge de qualidade sem medição real por trás (§10.7).
- Link para fonte oficial, nunca cópia — quando a fonte muda, o link segue
  correto; uma duplicata ficaria stale.
- Claims de benchmark só citam `docs/programs/ecosystem-2026/benchmarks/`.
