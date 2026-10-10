# CLI Audit — Forge Experience 3.0

Fonte: `commands.generated.json` por repo + `check_docs.py` (0 problemas
nos 7). Contagens do inventário real de parsers.

## Superfície de comandos

| Forja | Comandos | Bare-TTY | Bare non-TTY | Descobribilidade |
|---|---|---|---|---|
| the-forge | 63 | Command Center | summary JSON/text | `help`, did-you-mean |
| spark-forge-aws | 242 | ui home | help | `help <verbo>`, did-you-mean |
| api-forge | 443 | ui home | summary | `apiforge-tui` extra |
| spark-forge-azure | 93 | ui home | help | `help <verbo>` |
| platform-forge | 57 | ui home | help | `help <verbo>` |
| forge-doctor-data | 289 | run_home | help | `help <verbo>` |
| forge-doctor-api | 35 | run_home | help | `help <verbo>` |

## Lacunas contra o "Super CLI" do §2.9

- Sem **command palette** em nenhuma CLI (Ctrl+K exige full-screen ou
  fluxo interativo novo).
- Busca dentro do produto: catálogos existem como docs gerados, não como
  `… search`-verb unificado por forge (aws tem `code search` de domínio,
  não navegação de produto).
- Erros: recusas estruturadas com `unlock` existem (FORGE-*, SF-*, AF-*,
  PF-*); falta padronizar "próximo passo" nas mensagens de CLI comuns.
- Progresso real: instalação/wizard mostram plano e receipt; operações
  longas (index, analyze) não têm progresso — só saída final.

## O que já está premium

- Inventário real por parser (não regex), reference gerado, keep-blocks.
- Exit codes semânticos e `--json` nas superfícies de automação.
- Recusas fail-closed com código + unlock em todas as forjas.
- cp1252-safe stdout nos 7 entrypoints.
