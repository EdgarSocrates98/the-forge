# Discovery — descoberta universal de especialistas (lf-0027)

`src/theforge/discovery.py` resolve **quais especialistas existem nesta
máquina e em que estado estão**, agregando evidência de todas as fontes
legítimas — mais baratas primeiro — e separando *descoberta de metadata* de
*verificação executável*. É a camada que [remote-discovery.md](remote-discovery.md)
(providers **não** instalados) não cobre: o que já está presente.

Não confundir com `specialists.collect()` ([control-plane.md](control-plane.md)):
`collect` monta a visão de lifecycle para instalar/ativar; `discover` responde
"o que existe, com que proveniência e que evidência de execução". As duas
compartilham as mesmas fontes de receituário (`~/.forge/installations`,
`~/.forge-cli/forges/state.json`, checkouts).

## O contrato `theforge/SpecialistCapability/v1`

Definido em `src/theforge/contracts/specialist_capability.py`; schema gerado
em `schemas/SpecialistCapability.schema.json`.

**Mapeamento de namespace.** A spec cross-forge (lf-0027, auditada em
forge-cli `docs/integration/`) chama este contrato de
`forge/SpecialistCapability/v1`. Dentro do the-forge os contratos do
ecossistema vivem no namespace `theforge/<Name>/v1` — o prefixo `forge/` da
spec mapeia para `theforge/` aqui. Manifestos com
`"schema": "forge/SpecialistCapability/v1"` são **rejeitados** (schema
pinado), não aceitos por tolerância.

O documento declara: `specialist` (id provider + version SemVer/`runtime-detected`
+ domínio), `capabilities[]` (id pontilhado, descrição, `entrypoint` argv,
`execution_mode` `local|remote|hybrid`, `risk` = `OperationClass`,
`requires`/`optional_deps`/`permissions`/`network`/`external_cost`,
`timeout_s`, `discovery_mode`, `verification_mode`) e os surfaces
`health`/`handoff` (`{supported, detail}`).

O especialista publica o manifesto como **`forge.capabilities.json`** (ou
`forge.capability.json`) na raiz do checkout ou embutido no pacote instalado.
O manifesto é *declarado, nunca inferido*: ausência é gap honesto, não
"zero capabilities".

## Estados de descoberta

```text
NOT_INSTALLED  — id de catálogo sem nenhuma evidência
DISCOVERED     — evidência de presença, nada validado ainda
VERIFIED       — handshake + manifesto + liveness provados por caminho governado
INCOMPATIBLE   — presente, mas não roda aqui (Requires-Python, versão major, protocolo)
DEGRADED       — instalado mas parcialmente quebrado (raiz sumiu, probe falhou)
UNAVAILABLE    — presente mas inalcançável/não saudável agora (registry describe falhou)
UNTRUSTED      — encontrado mas não pode executar (entry unverified/blocked
                 ou manifesto declarado que falha validação de contrato)
```

### DISCOVERED ≠ VERIFIED

Estado é função da *evidência*, não da *existência de arquivos*. VERIFIED
exige `probe=True` **e** os três checks por caminho governado:

| check | evidência aceita |
|---|---|
| `handshake` | `describe` via Forge Protocol (registry) **ou** probe `--version` por argv tipado **ou** metadado de dist instalada (metadado sozinho não gera VERIFIED — só `DISCOVERED` + limitation) |
| `manifest` | `forge.capabilities.json`/`forge.agentic.json`/manifest do registry parseou contra o contrato |
| `health` | op `health` via `SubprocessTransport`, ou liveness pelo próprio version probe; `SKIP` quando o especialista não declara surface de health |

`probe=False` nunca executa nada → teto DISCOVERED, com a limitation
"identity evidence is cached/metadata only". Um `ForgeManifest` vindo de
cache do registry idem: handshake PASS não-live é honesto e não promove.

## Fontes e precedência

```text
1. registry          providers.toml (builtin > user > project) + records
2. install-receipt   ~/.forge/installations/<id>.json
3. forge-cli         ~/.forge-cli/forges/state.json (leitura; forge-cli escreve)
4. checkout          membros do workspace com .git + forge.json
5. configured-path   discovery.toml (user config e .forge/config) e
                     configured_paths do chamador — forge.json basta,
                     nenhum .git necessário
6. package           importlib.metadata (Name/Version/Requires-Python/files)
7. entry-point       grupo theforge.specialists + console_scripts do cli
8. bundled-manifest  forge.capabilities.json / forge.agentic.json
9. mcp               bloco mcp do install manifest / .mcp.json
```

Cada evidência carrega proveniência (`source`, `detail`, `path`, `sha256`)
no `DiscoveryReport` — um relatório cacheado explica *o que viu*, não só o
que afirma. Versão resolve por evidência forte primeiro: manifest do
registry > dist instalada > receituário > manifesto declarado.

### Trust do registry é respeitado

`builtin`/`trusted`/`local` podem verificar; `unverified` só com
`allow_unverified=True`; `blocked` nunca executa. Uma entry barrada e sem
outra evidência resolve `UNTRUSTED` (e nunca `DISCOVERED` "inocente").

## Execução governada

Nenhuma verificação inventa transporte: describe/health vão pelo
`SubprocessTransport` existente (env scrubbed, caps de saída, kill de
process-tree, stderr redigido). O probe de versão para CLIs não-registry é
argv tipado (`version_cmd` do receituário de instalação, `shim`/`bin` do
receipt forge-cli, ou `cli` resolvível via `shutil.which`) com `safe_env`,
timeout bounded e **nunca `shell=True`**. Metadados de pacote são lidos por
`importlib.metadata` — nunca executando entry points para inspecionar.

## Scan bounded + cache

`scan_budget_s` (default 5s) é um deadline monotônico compartilhado por
todas as fontes; os passos caros (records do registry, metadados por dist,
scan global de entry points) checam o budget e o relatório marca
`truncated` + `limitations` quando algo é cortado — relatório truncado
nunca vira cache. Resultados são persistidos em
`<cache>/discovery/report-<context_digest>.json` com TTL (`cache_ttl_s`,
default 300s): o digest cobre workspace, paths configurados, `probe`,
`allow_unverified` e o conjunto de ids — contexto diferente, cache
diferente. Todo documento persistido passa por `security.redact`; um
relatório que contém valores com cara de segredo não é escrito de todo
(warning registrado).

## `discovery.toml`

```toml
# user config (THEFORGE_CONFIG_DIR) e/ou .forge/config/discovery.toml
paths = ["/opt/forges/data sentinel"]           # id vem do forge.json local

[[specialists]]
id = "data-sentinel"                            # override explícito de id
path = "/srv/forges/data-sentinel checkout"
```

User config tem precedência sobre o arquivo de projeto para o mesmo path.
Arquivo malformado é ignorado — nunca fatal para um scan.

## API

```python
from theforge.discovery import discover_specialists, discover_specialist

report = discover_specialists(workspace_root=Path.cwd(), probe=True)
entry = discover_specialist("data-sentinel", probe=True)
```

Injeção para testes e hosts: `registry`, `transport_factory`,
`dist_loader`, `entry_point_scan`, `clock`, `cache_dir`, `scan_budget_s`.
