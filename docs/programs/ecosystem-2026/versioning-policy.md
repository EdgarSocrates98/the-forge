# Política de versões — ecossistema Forge

Spec: `factory/specs/active/cyc8-01-compat-manifest.md` (§8.3–8.4 do prompt-fonte).
Manifesto: [`../../../ecosystem-compatibility.json`](../../../ecosystem-compatibility.json) ·
Schema: [`../../portable-installation/schemas/EcosystemCompatibility.schema.json`](../../portable-installation/schemas/EcosystemCompatibility.schema.json) ·
Validação Python: `src/theforge/install/compatibility.py`.

## Princípio

Os nove repositórios têm **ciclos de vida independentes** — não existe "versão do
ecossistema". O que existe é o **release train** (`release: YYYY.MM`): uma
combinação certificada de versões publicada no manifesto. Versão única obrigatória
e bump em bloco estão explicitamente rejeitados na spec.

## Esquema por projeto (estado real, baseline 2026-10-15)

| Projeto | Versão | Scheme | Fonte | Observação |
|---|---|---|---|---|
| the-forge | `0.5.0` | semver | `pyproject.toml` | contratos `theforge/*/vN` independentes |
| api-forge | `0.1.0` | semver | `pyproject.toml` | |
| platform-forge | `0.1.0` | semver | `pyproject.toml` | |
| spark-forge-aws | `0.5.0` | semver | `pyproject.toml` | |
| spark-forge-azure | `0.1.0` | semver | `pyproject.toml` | |
| forge-doctor-data | `1.0.0rc1` | pep440 | `pyproject.toml` | janela RC — PEP 440 não é SemVer estrito |
| forge-doctor-api | `0.2.0` | semver | `pyproject.toml` | RC discipline: sem bump sem `docs/versioning.md` |
| forge-cli | `0.1.0` | semver | `package.json` | npm — publicação pendente (decisão de produto) |
| forge-portal | `0.1.0` | semver | `package.json` | declarada (era 0.0.0 placeholder) |

**Regra**: cada projeto usa SemVer **onde apropriado**; onde outro esquema
vigora (PEP 440 no Doctor Data), o manifesto declara `scheme` por componente —
sem conversão forçada.

## Eixos de versão separados

| Eixo | Como versiona | Estado |
|---|---|---|
| Versão da Forja (projeto) | SemVer/PEP 440 no arquivo de versão do repo | real |
| Contratos de protocolo | `theforge/<Name>/vN` — major inteiro no id | real |
| Contratos de instalação | `forge/<Name>/vN` — major inteiro no id | real |
| Instalador (installkit) | `scripts/installkit/forge_installkit.py` vendored + byte-parity | real |
| Assets de host | gerados do roster canônico (`agents sync`, audit_assets) | real |
| Portal — app | `package.json` 0.1.0 | declarada |
| Portal — API | envelope `forge/PortalApi/1` servido por `<cli> portal` | real |
| Portal — assets | `forge/PortalAssets/1` + `portal_version` 1.0.0, sha256 por arquivo, vendored via `scripts/vendor.py` | real |
| Interface MCP | `theforge/McpRegistryDocument/v1` + `mcp_server_name` por forge.json | real |

## Manifesto de compatibilidade

`ecosystem-compatibility.json` na raiz do the-forge — namespace `forge/*` da
família installkit (mesma de `forge/InstallReceipt/v1`), pois os consumidores
são o plano de instalação/release (forge-cli, Portal, hosts).

- **`components`**: versão certificada + `scheme` + `source` (proveniência
  obrigatória — versões fictícias são rejeitadas por construção).
- **`contracts`**: janela `[min_major, max_major]` por família. Família sem
  contrato publicado declara `contract: null` — estado honesto, nunca range
  inventado (mecanismo reservado; hoje todas as famílias declaradas têm contrato).
- **`check(component, version)`**: `certified` (membro exato) /
  `incompatible` (versão diverge) / `unknown` (componente ausente).
- **`contract_supported(family, major)`**: janela declarada; `False` para
  famílias ausentes ou não versionadas.

Avaliação de compatibilidade além de pertencimento (janelas de downgrade,
atualização parcial) é política do consumidor — o manifesto só declara.

## Consumo

- **forge-cli** (cyc8-05): compat-check antes de install/update; rollback usa o
  manifesto da combinação anterior.
- **Portal** (cyc8-06): release UI lê o manifesto — nunca duplica lógica de
  compatibilidade no frontend.
- **Hosts/installkit**: `forge/WorkspaceInstall` + este manifesto fecham a
  resposta "o que está instalado é uma combinação certificada?".

## Pendências (produto, não inventadas aqui)

- Publicação dos pacotes (PyPI/npm) e `distribution` reais — ⚠ decisão de
  canal ainda aberta.
- `forge-portal` package version 0.1.0 — versão declarada do app (antes 0.0.0 placeholder) é
  decisão de produto (o contrato `forge/PortalApi/1` já existe independente).
- Assinatura/provenance do manifesto — escopo da cyc8-03 (supply chain).
