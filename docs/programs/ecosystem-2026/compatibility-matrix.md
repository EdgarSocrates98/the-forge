# Compatibility matrix — draft inicial

**Status: NÃO CERTIFICADA.** Captura de versões atuais em `main` (2026-10-15). Ranges suportados ainda não existem — serão definidos pelo manifesto (spec cyc8-01) e calibrados por testes de compatibilidade reais. Nenhuma combinação abaixo foi certificada como release integrada.

## Versões atuais (observadas, não certificadas)

| Componente | Versão | Contratos expostos | Estado |
|---|---|---|---|
| the-forge | 0.5.0 | `theforge/<Name>/v1`, provider surface, portal_api | observado |
| forge-cli | 0.1.0 | install/update lifecycle | observado |
| forge-portal | 0.1.0 | portal_api consumer | declarada |
| api-forge | 0.1.0 | specialist_manifest, install_receipt | observado |
| platform-forge | 0.1.0 | specialist_manifest, install_receipt | observado |
| spark-forge-aws | 0.5.0 | specialist_manifest, install_receipt | observado |
| spark-forge-azure | 0.1.0 | specialist_manifest, install_receipt | observado |
| forge-doctor-data | 1.0.0rc1 | specialist_manifest | RC window |
| forge-doctor-api | 0.2.0 | specialist_manifest | RC discipline |

## Ranges de contrato (a preencher por cyc8-01)

| Contrato | Consumidor | Provider | Range suportado | Verificado em |
|---|---|---|---|---|
| `specialist_manifest` | the-forge | especialistas/doctors | `unknown` | — |
| `install_receipt` | forge-cli | instaladores | `unknown` | — |
| `portal_api` | forge-portal | backend the-forge/CLI | `unknown` | — |
| interfaces MCP | hosts | especialistas | `unknown` | — |

> `unknown` é o valor honesto: nenhum teste de compatibilidade versionada rodou ainda. Preenchimento exige o manifesto + gates de compat do CI (cyc8-01, cyc8-04).

## Política-alvo (§8.3)

Versões independentes por componente — Forja, contratos, instalador, assets de host, Portal, interfaces MCP. Sem bump em bloco; release integrada = matriz certificada, não versão única.
