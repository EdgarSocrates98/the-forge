# Receita — descobrir qual forja atende um requisito

**O quê:** `forge capabilities discover` resolve requisito → provider, sem
você saber o nome dele.
**Por que:** routing por capacidade declarada, não por memória.
**Quando:** antes de instalar/delegar; ao compor planos multi-forge.
**Quando não:** o requisito exige execução — `discover` só negocia, não roda.

## Problema

"Preciso de análise Glue — quem faz, está instalado, o que falta?"

## Passo a passo

```bash
theforge capabilities list --json                              # o catálogo
theforge capabilities discover --capability glue.analysis --json
theforge capabilities search glue                              # por palavra-chave
```

## Saída esperada / interpretação

`local_state: FULL` = um provider local satisfaz; `UNSUPPORTED` + candidatos
remotos = falta instalar (economia de descoberta reportada em
`registry_calls`/`metadata_bytes`).

## Verificação

`forge providers health --json` deve mostrar o provider `ok` com
`surface_fingerprint`.

## Limitações

Descoberta remota precisa de registry configurado; sem fontes, a resposta
honesta é `no registry sources configured`.

## Erros comuns

| Sintoma | Causa | Ação |
|---|---|---|
| `entries_scanned: 0` | capability id errado | `capabilities list` e copie o id |
| `UNSUPPORTED` com provider saudável | ação/capability divergente | confira `actions` no catálogo |

## Uso por agentes

Saída `--json` é o contrato de negociação — um agente pode propor o plano,
a instalação continua decisão humana (`forge install`).
