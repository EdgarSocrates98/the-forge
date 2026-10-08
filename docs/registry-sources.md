# Registry Sources

De onde vem o *metadata* de providers. Três níveis, com fronteiras explícitas
(ver `docs/adr/0034`):

```text
local registry (installed providers)   →  authoritative
configured sources (registries.toml)   →  untrusted metadata
marketplace UX                         →  someday, on top of the same sources
```

**Discovery não é instalação; instalação não é confiança.** Uma fonte só produz
`RegistryDocument/v1` — dados externos que podem informar descoberta e
negociação, nunca `ProviderEntry`, identidade ou trust. Nada que venha de uma
fonte remota vira provider roteável sem a configuração local explícita
(`providers.toml`) que sempre existiu.

## Contratos

- `theforge/ForgeRegistryEntry/v1` — metadata publicado de **uma versão** de um
  provider: `provider`, `version` (SemVer), `publisher` (declarado, não
  verificado), `manifest_url`/`manifest_sha256`, `distribution`
  (pip-package/file/vcs/container com referência imutável), `protocols`,
  `capabilities`, `platforms`, `runtime` (`python`, `offline`,
  `requires_network`, `requires_credentials`), `hashes`, `signatures`,
  `source_repository`, `license`, `security_contact`, `released_at`,
  `limitations`.
- `theforge/RegistryDocument/v1` — o que uma fonte retorna: `registry`
  (identidade de quem produziu o documento), `produced_at`, `entries`,
  `limitations`. Providers duplicados no mesmo documento são rejeitados.

Os dois são *open schemas*: campos desconhecidos são tolerados no decode
(forward compatibility) — uma fonte mais nova pode acrescentar campos sem
quebrar clientes antigos.

## Configuração — `registries.toml`

User config dir primeiro (`~/.config/theforge/` ou `%APPDATA%\theforge\`, ou
`THEFORGE_CONFIG_DIR`), depois `.forge/config/registries.toml` do projeto. O
arquivo do projeto só **adiciona** ids novos — nunca sobrescreve uma fonte do
usuário (mesma precedência de `providers.toml`).

```toml
[[sources]]
id = "team-mirror"
kind = "local-file"          # ou "http" / "a2a" / "mcp"
path = "registry.json"       # relativo ao diretório do registries.toml
enabled = true               # opt-in: default desabilitado

[[sources]]
id = "public-registry"
kind = "http"
url = "https://registry.example/index.json"   # URL do RegistryDocument
enabled = false              # remoto nunca surpreende (air-gapped por default)
max_age_s = 3600             # freshness budget do cache (default 3600)
timeout_s = 10               # espera limitada por request (default 10)

[[sources]]
id = "org-registry"
kind = "http"
url = "https://registry.corp.internal/index.json"
tier = "org"                 # Cycle 5: feed curado pela organização
enabled = true
```

- `id` — identificador da fonte (`[a-zA-Z0-9_-]+`).
- `kind` — `local-file` (documento JSON; mirrors, catálogos vendored, feeds
  air-gapped), `http` (cliente read-only com cache e freshness — Wave D),
  `a2a` (Agent Card remoto convertido em `RegistryDocument` — Wave I,
  experimental; ver [a2a-bridge.md](a2a-bridge.md)) ou `mcp` (listagem do
  MCP Registry oficial — Wave J; tooling metadata, **não** provider:
  `read_sources` a devolve `skipped`, lida via `read_mcp_sources` —
  ver [interoperability-mcp.md](interoperability-mcp.md)).
- `enabled` — **default `false`**: uma fonte configurada não faz nada até ser
  habilitada explicitamente.
- `tier` — `"public"` (default) ou `"org"` (Cycle 5, Wave O). Um feed `org`
  marca seus candidatos com `source_tier="org"` para que política downstream
  (ex.: allowlist de `remote-policy.toml`) possa privilegiá-los — continua
  sendo *claim*: tier nunca vira trust nem sobrescreve a realidade instalada
  local (local manifest verificado permanece autoritativo).
- `max_age_s` — freshness budget: cache mais novo que isso nem dispara fetch.
- `timeout_s` — bounded wait por request HTTP.

## Fonte `http` (read-only)

`HttpRegistrySource` faz um `GET` condicional e honesto sobre freshness:

```text
cache fresh (age ≤ max_age_s)  →  ok, from_cache — sem rede
cache stale/ausente            →  GET (If-None-Match quando há etag)
   ├─ 200 → valida + grava cache → ok
   ├─ 304 → refresh retrieved_at → ok (cache renovado)
   └─ erro/timeout/não-200 → cache? stale (marcado) : unavailable
```

Regras de segurança do cliente:

- **URL `https://` obrigatória** — `http://` só para hosts loopback
  (`127.0.0.1`, `::1`, `localhost`: mirrors locais e testes). Redirects são
  revalidados no URL final.
- **Body limitado** a 8 MiB; decode tolerante (forward-compat) + validação de
  contrato — lixo remoto vira `invalid`, nunca crash.
- **Cache verificado por integridade**: o envelope guarda `url`, `retrieved_at`,
  `etag` e `body_sha256`; na leitura o sha do corpo é recomputado — cache
  adulterado é simplesmente ignorado (§21).
- **`THEFORGE_NO_NETWORK=1`** desliga toda leitura remota independente de
  `enabled` — o kill-switch para ambientes air-gapped.
- ETag enviado como `If-None-Match`; `304` renova o freshness sem
  re-download (eficiência — não chamamos o registry repetidamente).

Todo read remoto carrega proveniência no `SourceRead`: `freshness`
(`fresh`/`stale`/`unknown`), `from_cache`, `retrieved_at`, `etag`,
`body_sha256` — e `status="stale"` quando o documento servido expirou o
budget. Stale nunca é silenciosamente fresh.

## Fonte `a2a` (experimental)

`kind = "a2a"` aponta `url` para um A2A Agent Card remoto. O cliente é o
mesmo `http` read-only (mesmas regras de URL, cache, freshness e
kill-switch); só o decode difere — o card é convertido pelo bridge em um
`RegistryDocument` de uma entrada cujas claims são marcadas *external /
remote / unverified* (nunca provider local, `distribution` vazio, dimensões
de política em `runtime`/`limitations`). Detalhes do mapeamento:
[a2a-bridge.md](a2a-bridge.md).

## Leitura

`theforge.registry.sources.read_sources(specs)` retorna um `SourceRead` por
fonte, na ordem configurada:

| `status` | significado |
|---|---|
| `ok` | documento decodificado (`read.document`) |
| `disabled` | fonte existe mas está `enabled = false` — reportada, nunca lida |
| `stale` | cache servido após expirar o freshness budget — marcado, nunca silencioso |
| `unavailable` | fonte inalcançável (arquivo ausente, rede, sem cache) |
| `invalid` | conteúdo não é um `RegistryDocument` válido (ou url insegura) |

Uma fonte indisponível é **dado**, não exceção: o core continua funcionando
offline com o que estiver instalado.

## `theforge registry sources`

Inspeção read-only e offline: projeta o registry local como fonte
(`local`, authoritative) e lista as fontes configuradas com status e contagem
de entradas.

```text
local (authoritative): 4 installed providers
feed                 local-file  ok           entries=12 registry=team-mirror
public-registry      http        stale        entries=12 registry=public (cache) retrieved=2026-01-01T10:00:00.000000Z  public-registry: fetch failed: TimeoutError; cached document from ... is stale
```

## `local_document`

`theforge.registry.sources.local_document(records)` projeta os providers
instalados (`state == "ready"`) como `ForgeRegistryEntry`: capabilities não
`unsupported`, runtime do `manifest.execution`, `manifest_sha256` em `hashes`.
É a mesma linguagem de metadata dos sources externos — mas gerada de manifests
**verificados localmente**, não de claims remotos. `publisher` sintético
`local:<id>` deixa explícito que não é identidade de publisher real.

## Fronteiras

- Fonte **não** decide trust — `trust` continua só em `providers.toml`.
- Fonte **não** instala — Wave F define `InstallationPlan` com aprovação.
- Fonte **não** executa — descoberta remota (Wave E) nunca dispara provider.
- O cliente `http` é read-only: nenhum `POST`/mutation, nenhum download de
  pacote — só o documento de metadata.
- Popularidade/downloads/stars nunca são evidência de engenharia.
