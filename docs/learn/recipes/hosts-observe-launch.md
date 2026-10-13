# Receita — observar e abrir seu host de IA

**O quê:** `forge hosts observe` mede cada host (binário, versão, login,
integração do workspace); `forge hosts launch` abre UM host no terminal.
**Por que:** antes de operar num host você precisa saber se ele está pronto
— e lançar é uma fronteira humana, nunca automação silenciosa.
**Quando:** logo após instalar, ou quando algo falha no host (MCP sumiu,
skill desatualizada, auth expirada).
**Quando não:** para detecção por evidência (env/config), use
`forge hosts list`/`status`; para ativar a integração, `hosts activate`.

## Problema

"Quero saber se o Devin/Claude está pronto neste workspace — e abri-lo."

## Pré-requisitos

O binário do host no PATH. Integração `healthy` exige
`forge install apply` concluído neste workspace.

## Passo a passo

```bash
theforge hosts observe --json      # recibo dos 4 hosts
theforge hosts observe devin       # um só host
theforge hosts launch devin        # abre o Devin aqui (TTY obrigatório)
```

## Saída esperada / interpretação

Cada host recebe um `state`:

| State | Significa |
|---|---|
| `NOT_DETECTED` | binário fora do PATH |
| `SUPPORTED` | binário+versão ok; login desconhecido ou integração `unverified` |
| `READY` | logado + integração `healthy` |
| `NEEDS_LOGIN` | deslogado — recibo traz `login_hint` |
| `INTEGRATION_DEGRADED` | integração com drift — `forge install doctor` |

`launch` recusa com razão nomeada: `host_absent`, `login_required`,
`no_tty` — nunca silencia.

## Verificação

Após `launch`, o recibo traz `launched: true` + `host_exit_code` real do
processo do host — prova de que rodou de verdade, não simulado.

## Limitações

Copilot não tem subcomando de status documentado → `logged_in: null`
honesto. O recibo nunca carrega saída de auth (pode listar caminhos de
credencial).

## Erros comuns

| Sintoma | Causa | Ação |
|---|---|---|
| `INTEGRATION_DEGRADED` | drift nos arquivos gerenciados | `forge install doctor` → `repair` |
| `NEEDS_LOGIN` | auth expirada | rode o `login_hint` do recibo |
| `no_tty` | chamou `launch` num pipe/CI | só observe em headless |

## Uso por agentes

`observe` é read-only e máquina-friendly (`--json`). `launch` exige TTY —
um agente nunca deve tentar abrir host por você; ele lê o recibo e sugere
o comando.
