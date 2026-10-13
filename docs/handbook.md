# The Forge Handbook — ecossistema de especialistas

Guia central do ecossistema. Cada forja é independente — este documento
roteia, não substitui a documentação de cada repo.

## O que é

Sete repositórios, um padrão: análise determinística (facts → rules →
findings), instalação portátil nos hosts de IA, e honestidade de status
(`available` / `unverified` / `blocked` — nunca "funciona" sem evidência).

## Qual forja usar

| Preciso de… | Forja | Repo |
|---|---|---|
| orquestrar o ecossistema, rotear para especialista | The Forge | `the-forge` |
| revisar/difundir contratos e evolução de API | API Forge | `api-forge` |
| performance/custo de jobs AWS Glue e EMR | Spark Forge AWS | `spark-forge-aws` |
| plataformas de dados Azure (Databricks, Fabric, ADF) | Spark Forge Azure | `spark-forge-azure` |
| engenharia de plataforma agentic, frota, SRE | Platform Forge | `platform-forge` |
| diagnóstico de projeto de dados (scan/checks) | Forge Doctor Data | `forge-doctor-data` |
| diagnóstico de projeto de API (scan/checks) | Forge Doctor API | `forge-doctor-api` |

## Ciclo de vida comum

1. **Clone + setup**: `git clone <repo> && ./setup.sh` — cria venv, wheel
   e launcher no PATH, e registra a forja em `~/.forge/installations`.
2. **Instalar no host**: `<cli> install [--dry-run → --yes]` — escreve
   skills/agents/config do MCP nos diretórios do host (Claude, Devin,
   Codex, Copilot). Perfis: `minimal` / `recommended` / `full`.
3. **Verificar**: `<cli> [install] doctor` e `mcp-verify` — handshake real,
   `tools/list`, `tools/call` segura, saída limpa.
4. **Usar**: via CLI direto ou pelo host de IA (a instalação publica os
   ativos; o host decide quando invocar).
5. **Reparar/remover**: `repair` cura regiões gerenciadas mantendo edições
   do usuário; `uninstall` remove só o que o ledger registrou.

## Composição entre forjas

`theforge install auto` instala/delega nas forjas registradas do
workspace (scope `workspace`, `--member` para fan-out). `theforge
providers` e `theforge ask` roteiam para o especialista certo — o piso é
sempre o CLI da forja, que funciona sem o The Forge.

## Control plane

`theforge specialists list` mostra o ciclo de vida real de cada forja
(NOT_INSTALLED → INSTALLED → CONFIGURED → REGISTERED → HEALTHY), a partir
de evidência — registry de instalações, probe do CLI e checkouts locais.
`theforge hosts list` detecta os hosts de IA com `confidence_basis`;
`theforge task run "<intent>"` delega trabalho real via argv do
especialista (stages honestos: COMPLETED só com exit_code).
Detalhe: `docs/control-plane.md`.

## Hosts de IA

- **Claude Code**: skills em `.claude/skills/`, agents em `.claude/agents/`,
  MCP via `.mcp.json`. Detalhe: `docs/installation/claude-code.md`.
- **Devin**: `.devin/skills/`, `.agents/agents/` (+import de `.claude/agents/`).
  Detalhe: `docs/installation/devin-cli.md`.
- **Codex**: `.agents/` + config MCP própria. Detalhe: `docs/installation/codex-cli.md`.
- **Copilot**: `docs/installation/copilot-cli.md`.

## Progressive disclosure e economia

Não carregue as ~200 skills do ecossistema de uma vez. Cada forja expõe
índices (`capabilities`, `agents`, `next-step`) — o host puxa a skill
quando a tarefa chega. Ver `docs/economy.md` por repo.

## MCP

Forjas com servidor MCP expõem tools read-only; o ciclo de vida
(handshake → enumeração → invocação → término) é verificado por
`<cli> [...] mcp-verify`. Forjas sem MCP: The Forge (NOT_APPLICABLE).

## Limitações honestas

- Execução real dentro dos hosts: UNVERIFIED — a estrutura de instalação
  é testada; o consumo pelo host depende do host.
- Multi-OS: desenvolvido e verificado em Windows; scripts `.sh`/`.ps1`
  existem mas a matriz multi-OS não foi executada.
- `collect *` e similares exigem credenciais de cloud — nada os invoca
  sem você.

## Referências por forja

Cada repo: `docs/installation/` (12 guias), `docs/reference/` (comandos,
skills, agents gerados do parser real), `docs/tutorials/first-run.md`,
`docs/economy.md`, `docs/installation/troubleshooting.md`.
