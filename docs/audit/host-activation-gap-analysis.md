# Host activation gap analysis (FASE 0)

O que existe vs o que a FASE 4 exige.

| Requisito | Estado atual | Gap |
|---|---|---|
| Detectar host atual | implícito (`--host` explícito; sem detecção automática com evidência) | **HostDetectionResult**: env markers + binary presence + config dirs, com `evidence` e `limitations` |
| Escopos project/workspace/user | implementado no install | reutilizar |
| Skills instaladas | install escreve `.claude/skills/` etc com ledger | verificação de *carregamento* pelo host (não provável offline) |
| Agents/subagents | mirrors gerados + AgentSpec | declaração honesta de suporte (subagent nativo ≠ arquivo de instrução) |
| MCP handshake real | `mcp_verify`: init→tools/list→tools/call→exit | por-forge declaração do verify-tool existe; executado de verdade só em doctor-data |
| Dynamic activation | nada | **ACTIVE_NOW / RESTART_REQUIRED / UNSUPPORTED** por host+componente; instruções de retomada |
| ActivationReceipt | nada | `HostActivationReceipt/v1` com checks + outcome |

## Hosts suportados hoje

claude, devin, codex, copilot — cada um com caminhos próprios
(`render.py` do installkit conhece os layouts por host). Não presumir
paridade: Devin importa `.claude/agents/` + lê `.agents/agents/`;
Codex usa `.codex/`; Copilot CI só via playbook.

## Verdade sobre ativação

Nenhum host foi observado *carregando* assets no decorrer de uma sessão.
Portanto todo resultado honesto hoje é `RESTART_REQUIRED` ou
`UNSUPPORTED` para componentes já carregados na sessão — `ACTIVE_NOW`
só para componentes cujo consumo é read-time (ex.: MCP stdio spawnado
por chamada, se o host respawnar).
