# MCP interoperability (boundary document)

Cycle 4, Wave J — §68–72. Este documento fixa os papéis de forma permanente:

```text
MCP             = tools / resources / prompts access
Forge Protocol  = Forge provider orchestration
A2A             = agent-to-agent interoperability
```

Um **MCP server de terceiro não é um Forge provider** — nunca entra em
`RegistryDocument.entries`, nunca vira `RemoteProviderCandidate`, e não é
instalado ou executado automaticamente pelo Forge.

O próprio The Forge também expõe um servidor MCP local, mas ele é uma
interface do control plane, não um provider federado: `theforge mcp serve`
publica descoberta de skills/agentes/capabilities, planejamento, execução
governada e o ciclo de instalação. O extra é opcional no pacote para preservar
o núcleo stdlib-only; `forge.json` declara `extras: ["mcp"]`, o comando
`["theforge", "mcp", "serve"]` e o servidor `theforge`, e o installkit escreve
essa entrada em `.mcp.json` nos escopos `project`, `workspace` e `user`.

## Fonte `mcp`

`kind = "mcp"` em `registries.toml` aponta `url` para um endpoint de listagem
da API oficial do MCP Registry (`GET /v0{,.1}/servers` —
`registry.modelcontextprotocol.io` é o registry oficial; qualquer host com a
mesma API serve):

```toml
[[sources]]
id = "official-mcp"
kind = "mcp"
enabled = true
url = "https://registry.modelcontextprotocol.io/v0/servers"
max_age_s = 3600
```

A leitura (`registry/mcp.py` → `McpRegistrySource` → `McpSourceRead`) reusa
o mesmo transporte dos `http`/`a2a` sources — https-only fora de loopback,
body capado, cache verificado por sha256, freshness explícito,
`THEFORGE_NO_NETWORK=1`. O decode (`interop/mcp.py`) é tolerante e
**bounded** (§71): uma página, máximo 100 servers — `nextCursor` é
surfaced, nunca seguido automaticamente.

## O que o Forge faz com MCP

### MCP nativo do The Forge

Instalação local, sem flags para o caminho comum:

```bash
theforge install apply --scope project --components mcp --yes
theforge mcp serve
```

O servidor usa `stdio` por padrão. Para um cliente HTTP local, use
`theforge mcp serve --transport streamable-http` e conecte em `/mcp`. As
tools de leitura carregam anotações de risco e retornam JSON estruturado;
`theforge_install` só escreve quando recebe `confirm=true`.

### MCP externo

1. **Tooling awareness** — em `theforge capabilities discover`, se o
   `CapabilityRequirement` declara `technologies`, servidores cujo
   nome/título/descrição casam aparecem na seção `mcp tooling:` —
   claramente marcados como tooling, não providers. Bounded a 10 notas,
   ordem determinística.

2. **Dependency detection** (§70) — uma capability pode declarar
   `mcp_requires: ["io.github.org/server"]` no manifesto. `discover` reporta
   cada dep como `mcp dependency: <name> (declared by provider/cap) —
   listed|unlisted` conforme uma fonte `mcp` habilitada lista o nome.
   Detecção é observacional; **nada é instalado ou configurado**.

## Dimensões de política preservadas (§72)

Cada `McpServerEntry` carrega, do próprio registry e sem interpretação:

- `requires_network` — qualquer `remotes[]` declarado (egresso ao usar);
- `requires_credentials` — headers de remote ou env vars `isSecret`/
  `isRequired` (credenciais ficam com o operador);
- `remotes` (type + url + nomes de headers) e `packages`
  (`registryType:identifier`) — caminhos de obtenção *para humanos*;
- `limitations` — sempre inclui "metadata is publisher-declared —
  unverified".

## Limites

- Nenhuma definição de tool é carregada (schema de tools fica no server,
  fora do escopo do registry listing — progressive discovery por design).
- `listed` significa apenas "o registry declara o nome" — não disponível
  localmente, não confiável, não executável pelo Forge.
- Assinatura/verificação de registry MCP não existe na API pública ainda —
  `signature_state` não se aplica aqui; as claims seguem unverified.
