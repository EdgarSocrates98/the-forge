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
kind = "local-file"          # ou "http" (cliente chega na Wave D)
path = "registry.json"       # relativo ao diretório do registries.toml
enabled = true               # opt-in: default desabilitado

[[sources]]
id = "public-registry"
kind = "http"
url = "https://registry.example"
enabled = false              # remoto nunca surpreende (air-gapped por default)
max_age_s = 3600             # freshness budget para documentos em cache
```

- `id` — identificador da fonte (`[a-zA-Z0-9_-]+`).
- `kind` — `local-file` (documento JSON; mirrors, catálogos vendored, feeds
  air-gapped) ou `http` (Wave D: cliente read-only com cache e freshness).
- `enabled` — **default `false`**: uma fonte configurada não faz nada até ser
  habilitada explicitamente.
- `max_age_s` — freshness budget do cache (Wave D).

## Leitura

`theforge.registry.sources.read_sources(specs)` retorna um `SourceRead` por
fonte, na ordem configurada:

| `status` | significado |
|---|---|
| `ok` | documento decodificado (`read.document`) |
| `disabled` | fonte existe mas está `enabled = false` — reportada, nunca lida |
| `unavailable` | fonte inalcançável (arquivo ausente, rede, kind não implementado) |
| `invalid` | conteúdo não é um `RegistryDocument` válido |

Uma fonte indisponível é **dado**, não exceção: o core continua funcionando
offline com o que estiver instalado.

## `theforge registry sources`

Inspeção read-only e offline: projeta o registry local como fonte
(`local`, authoritative) e lista as fontes configuradas com status e contagem
de entradas.

```text
local (authoritative): 4 installed providers
feed                 local-file  ok           entries=12 registry=team-mirror
public-registry      http        disabled
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
- `http` é declarável mas inerte até a Wave D — ler retorna `unavailable`.
- Popularidade/downloads/stars nunca são evidência de engenharia.
