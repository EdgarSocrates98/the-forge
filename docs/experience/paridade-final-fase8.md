# FASE 8.1 — Matriz de paridade final ×7

> Combina o audit de superfície regenerado (presença) com a verificação
> de comportamento das fases 1–7 (prova). `SUPPORTED` aqui significa
> **verificado em execução real**, não só presente — ver relatórios de
> fase e `matriz-aceite.md` para o baseline de presença.

| dimensão | the-forge | api-forge | spark-forge-aws | spark-forge-azure | platform-forge | doctor-data | doctor-api |
|---|---|---|---|---|---|---|---|
| **CLI** | SUPPORTED — 77 cmds, bare→sumário | SUPPORTED — fuzzy help | SUPPORTED — 247 cmds | SUPPORTED — 22 grupos | SUPPORTED — recusas PF-* | SUPPORTED | SUPPORTED — 28 cmds |
| **TUI** | SUPPORTED — command-center 8 ações | SUPPORTED — home+wizard | SUPPORTED — menu real | SUPPORTED — menu real | SUPPORTED — 7 exploradores | SUPPORTED — 10 itens | SUPPORTED — sentinelas `__diff__`/`__script__` |
| **Host integration** | SUPPORTED — `hosts observe/launch` novo | SUPPORTED — flow real | SUPPORTED — `ai` flow | SUPPORTED — `ai` flow | SUPPORTED — `hosts` flow | SUPPORTED — `hosts` + MCP tool | SUPPORTED — `forge_hosts.py` |
| **Agents** | 8 AgentSpec/v1 c/ autoridade fechada | 31 c/ mirrors | 19 + executors | 40 | 41 roster | 0 (por desenho) | 0 (por desenho) |
| **Skills** | 33 canônicas | 14 | 60 | 22 | 12 | 0 (por desenho) | 0 (por desenho) |
| **MCP** | registry + invoke real | SUPPORTED — handshake real | **146 tools** lock + invoke | 18 tools + handshake | 39 caps + handshake | 14 tools + handshake | 17 tools + handshake |
| **Graph** | view local + federada (235n/595e) | view real | view + blast real | view real | view + blast real | view real | view + blast real |
| **Installation** | bootstrap + lifecycle + ledger | SUPPORTED — E2E scratch | SUPPORTED — E2E scratch | SUPPORTED — E2E scratch | SUPPORTED — E2E scratch | SUPPORTED — E2E scratch | SUPPORTED — E2E scratch |
| **Documentation** | learn+hub+INDEX+receitas | recipes+HOST_PARITY | recipes+rationale | 13 receitas | 12 receitas | 11 receitas | 8 receitas |
| **Tests** | **4853 t** suite | **1856 p** suite | ~14877 t (run final) | **3025 p** suite | **1025 p/0f** | **2638 p** suite | **1763 p/0f** |

## Divergências intencionais (não defeitos)

- **doctor-data/doctor-api: 0 agents/skills** — decisão arquitetural dos
  Doctors (diagnóstico determinístico, surface via MCP+catálogo facade);
  spawn_ok mantido porque subprocess fica no lifecycle de instalação.
- **doctor-api: host flow em `scripts/`** — boundary AST-puro de `src/`
  proíbe subprocess; o fluxo vive no nível checkout como os irmãos de
  instalação.
- **the-forge sem MCP server próprio** — é o orquestrador; consome os
  MCPs dos irmãos via manifesto, não publica um.
- **spark-forge-aws: 145→146 tools** — a tool `sparkforge_aws_ai`
  intencional do fluxo de hosts; lock re-selado.

## Estados externos honestos

- Copilot: `NOT_DETECTED` na máquina do operador + sem status de auth
  documentado — jornada Copilot é `UNVERIFIED` por desenho.
- Codex project-scope `.mcp.json`: `NOT_APPLICABLE` (verificado no
  codex-cli 0.160.0) — alternativa documentada.
- `DEGRADED`/`unverified` reportados onde o CLI da forja não está no
  PATH — discovery honesto, nunca promovido.
