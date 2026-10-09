# Ecosystem provisioning audit (FASE 0)

Evidence-based, not README claims. Generated against `main` after the
install + DX programs.

## Per-forge lifecycle matrix

| Pergunta | the-forge | api-forge | spark-aws | spark-azure | platform | doctor-data | doctor-api |
|---|---|---|---|---|---|---|---|
| CLI canônica | theforge | apiforge | sparkforge-aws | sparkforge-azure | platformforge | forge-doctor-data | forge-doctor-api |
| Versão | 0.5.0 | 0.1.0 | 0.5.0 | 0.1.0 | 0.1.0 | 1.0.0rc1 | 0.2.0 |
| Python | >=3.11 | >=3.12,<3.13 | >=3.10 | >=3.10 | >=3.10 | >=3.11 | >=3.11 |
| setup.sh/.ps1 | sim | sim | sim | sim | sim | sim | sim |
| install project | `install apply` | `install` | `install` | `install` | `install` | `install` | `scripts/forge_install.py` |
| install workspace | `install auto --scope workspace` | via registry | via registry | via registry | via registry | via registry | via registry |
| install user | `--scope user` | idem | idem | idem | idem | idem | idem |
| MCP | N/A (orquestrador) | `apiforge-mcp` | `mcp serve` | `mcp serve` | `platformforge-mcp` | `mcp` | `mcp` |
| Skills | 33 (kiro etc) | 15 | 60 | 22 | 12 | 0 | 0 |
| Agents (defs) | 8 AgentSpec TOML | 32 | 19 | 40 | 41 | 0 | 0 |
| Subagents hosts | .devin/.agents mirrors | sim | sim | sim | sim | N/A | N/A |
| Orquestrador interno | router + agents | SDD + dispatch | 14 coordinators | coordinators | Router V2 | scan/diagnose | scan/diagnose |
| Verificação | doctor + install doctor | install doctor/verify | doctor | distribution doctor | doctor | install doctor | forge_install doctor |
| Update | `install update --to pin` | idem | idem | idem | idem | idem | script idem |
| Uninstall | `install uninstall` | idem | idem | idem | idem | idem | script idem |
| Registry | `~/.forge/installations` | consumido | consumido | consumido | consumido | consumido | consumido |

## Operações sensíveis (classificação)

- **Read-only**: analyze/scan/judge/status/doctor/capabilities/playbook/next-step.
- **Mutação local**: install/repair/uninstall (ledger-owned), workspace state, case state.
- **Rede**: `collect *` (cloud dumps), setup deps download.
- **Aprovação**: qualquer mutação exige `--yes` pós-`--dry-run` (contrato
  install); lab mutável exige `--execute --confirm` (aws).

## Capabilities expostas ao The Forge

`forge/ProviderAdapter` v1 com `analyze`/`judge` por forja; registry em
`theforge registry`/`providers`. Capacidades internas não acessíveis via
adapter hoje: workflows compostos, coordinators, skills, MCP tools —
inventariados mas não executáveis remotamente (é o gap do programa).

## Evidência de hosts reais

Instalação estrutural verificada (escrita em `.claude/`, `.devin/`,
`.agents/`, `.mcp.json` com ledger); consumo real pelo host: UNVERIFIED.
