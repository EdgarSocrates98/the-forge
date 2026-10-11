# Receita — perguntar em linguagem natural e deixar o roteador escolher

**O quê:** `forge ask "<intent>"` resolve linguagem natural para o
especialista/capacidade certos via roteador determinístico.
**Por que:** com 6 forges e dezenas de capacidades, escolher "quem faz
isso" é dado, não julgamento — o roteador lê os manifestos declarados.
**Quando:** você sabe o problema, não a forja — ex.: "analisar meu
contrato openapi", "medir custo deste run do Glue".
**Quando não:** quando você já sabe a forja — vá direto
(`forge task plan --provider`); e nunca deixe o roteador executar sem
revisão (o plano é a fronteira).

## Problema

"Não sei qual forja responde 'avalie o blast radius desta mudança'."

## Pré-requisitos

Workspace inicializado (`forge init`) com especialistas irmãos
descobertos (`forge specialists`).

## Passo a passo

```bash
theforge init                                     # cria .forge/ no workspace
theforge ask "analisar o contrato openapi deste projeto" --json
theforge task plan "<intent>" --json              # do ask ao plano delegável
theforge task run "<intent>" --provider <forge> --json
```

## Saída esperada / interpretação

O `ask` devolve o `provider`+`capability` escolhidos com `signals` —
quais pistas do intent casaram. `task plan` devolve `stage: PREPARED`
com o argv real que rodaria; `task run` devolve `COMPLETED`/`FAILED` com
`exit_code` + `evidence`.

## Verificação

`forge capabilities list --json` mostra o catálogo que o roteador consulta
— o provider escolhido deve aparecer lá com o capability casado.

## Limitações

Sem especialista compatível no workspace o recibo diz
`no delegable specialists` — honesto, não inventa forja. Intents
ambíguos retornam nota `ambiguous` pedindo `--workflow`/`--provider`.

## Erros comuns

| Sintoma | Causa | Ação |
|---|---|---|
| `not initialized` | falta `.forge/` | `forge init` |
| `no delegable specialists` | nenhuma forja irmã no workspace | clone o checkout irmão ao lado |
| nota `ambiguous` | >1 workflow elegível | refine o intent ou passe `--provider` |

## Uso por agentes

`ask`/`task plan` aceitam `--json` e são o caminho agent-first: o agente
propõe o plano, o humano aprova `task run`.
