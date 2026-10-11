# Receita — federar várias forjas num workspace

**O quê:** um workspace com checkouts irmãos das forjas + `forge init`
descobre especialistas, roteia intents e funde grafos federados.
**Por que:** cada forja é soberana (seu repo, seu release) mas o trabalho
real atravessa fronteiras — "o blast radius desta API nos clusters Spark".
**Quando:** você opera >1 forja no mesmo projeto e quer roteamento
automático + visão unificada.
**Quando não:** para usar uma forja sozinha — cada uma funciona standalone
com seus próprios CLI/MCP/skills; a federação adiciona coordenação, não
dependência.

## Problema

"Tenho api-forge e spark-forge-aws no mesmo projeto — quero que `forge
ask` escolha e que o grafo mostre as duas juntas."

## Pré-requisitos

Checkouts irmãos com `forge.agentic.json` (manifesto declarativo) dentro
do workspace; `forge init` feito.

## Passo a passo

```bash
theforge init                                    # .forge/ no workspace
theforge specialists                             # quem foi descoberto
theforge capabilities list --json                # catálogo federado
theforge ask "<intent>" --json                   # roteamento real
theforge graph                                   # grafo federado (views por forja)
```

## Saída esperada / interpretação

`specialists` lista cada forja com `installation_state` real
(CONFIGURED/REGISTERED/HEALTHY). `graph` funde as views com namespace
por forja — arestas cross-forge carregam proveniência.

## Verificação

`forge ask "analisar contrato"` deve rotear para a forja de APIs quando
ela existe no workspace — e recusar honestamente quando não existe.

## Limitações

Federação é leitura/coordenação: a autoridade de execução fica em cada
forja (o `task run` executa o argv real da forja dona). Grafos federados
dependem dos manifests declarados — ausência de manifesto = invisível.

## Erros comuns

| Sintoma | Causa | Ação |
|---|---|---|
| forja não aparece em `specialists` | sem `forge.agentic.json` no checkout | adicione o manifesto na forja |
| `no delegable specialists` | nenhum workflow declarado | veja o manifesto da forja alvo |
| grafo sem a forja | view não produzida | rode o grafo local da forja primeiro |

## Uso por agentes

`capabilities list`/`ask`/`graph` são `--json`-first — o agente consulta
o catálogo federado em vez de adivinhar a forja.
