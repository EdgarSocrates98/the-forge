# Provider Distribution & Installation Plan v2

Como um candidato remoto **viraria** um provider instalado — hoje, como plano
determinístico e aprovado, nunca como efeito colateral (§27-30, ADR 0037).

```text
RemoteProviderCandidate / ForgeRegistryEntry
   ↓  theforge install plan --provider P --version V --source S
InstallationPlan/v2 (documento)
   ↓  approval (--approve registra o gate; execução = milestone separado)
download → verify → isolated-install → provider-check → surface-fingerprint → health
```

**`planning_only: true` é contratual** — o schema literalmente exige `true`;
nenhum caminho do codebase executa o plano.

## `theforge install plan`

```text
theforge install plan --provider acme-forge --version 1.2.3 --source feed [--approve] [--json]
```

- Resolve `provider@version` **exato** na fonte configurada — versão ausente
  lista as disponíveis; nunca assume outra versão.
- Fonte desabilitada ou inexistente → erro com instrução.
- Metadata `stale` → o plano carrega a limitação "source metadata is stale" —
  quem aprova vê a freshness do que está aprovando.
- Sem `distribution` na entry → `UsageError` (nada verificável para instalar).

## O que o plano carrega

| campo | de onde vem |
|---|---|
| `provider`, `version` | entry — pinned SemVer; `latest` é rejeitado pelo contrato |
| `distribution` | `DistributionRef` (pip-package/file/vcs/container); pip exige `package`+`version` pinned |
| `expected_hashes` | `entry.hashes` + `manifest_sha256` + `distribution.sha256` |
| `signature` | primeira `SignatureRef` declarada (verificação é do stage `verify`, futura) |
| `runtime` | `RuntimeRequirements` declarados |
| `environment` | `venv:providers/<id>-<version>` — isolado por default |
| `dependencies` | `entry.dependencies`; não-pinned (`!=`, `>=`) vira limitation |
| `permissions` | derivado dos claims de runtime (`network`, `credentials`, `non-offline-runtime`) |
| `post_install_checks` | `provider-check`, `surface-fingerprint`, `health` |
| `rollback` | `restore-previous` (versão + manifest hash + surface fingerprint anteriores) ou `remove-new` |
| `steps` | as 8 fases governadas, todas `pending` |
| `approval` | `required=true`, `granted` só via `--approve` |

## O estágio de aprovação

`--approve` registra `granted_by: cli-user` + timestamp — o plano aprovado
continua sendo um documento: os stages permanecem `pending` porque a execução
(download real, verify, venv) é um milestone separado. O valor de `--approve`
hoje é *declarar* que o gate foi exercido — útil quando o executor chegar.

## Por que plan-only

Instalação é supply-chain: baixar código de terceiros e executá-lo localmente.
O design mantém a barreira dura — discovery (Wave E) nunca instala, o plano
(Wave F) nunca executa, e quando a execução chegar ela herda: hashes
esperados, ambiente isolado, checks pós-instalação e rollback já modelados.
