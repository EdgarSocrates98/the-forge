# Capability Negotiation v2

Negociação determinística entre o que uma tarefa exige (`CapabilityRequirement/v1`)
e o que um provider declara (`ForgeManifest` + `CapabilityOffer/v1`). Nenhum score
opaco: o resultado é dimensional e explicável (ver `docs/adr/0033`).

```text
Task → CapabilityRequirement → CapabilityOffer(s) → Negotiation → best valid fit
```

## Contratos

- `theforge/CapabilityRequirement/v1` — o pedido. Só `capability` é obrigatório;
  todo o resto é uma demanda opcional (`required_actions`, `technologies`,
  `required_evidence`, `offline_required`, `network_allowed`,
  `credentials_allowed`, `mutation_allowed`, `operation_class_ceiling`,
  `minimum_trust`, `protocol_features`, `handoff_required`, `trace_required`,
  `economy_required`, `graph_required`, `task_family`, artifact types…).
  Campo não preenchido = nenhuma demanda.
- `theforge/CapabilityOffer/v1` — oferta rica, embutida aditivamente em
  `manifest.capabilities[].offer`: `technologies`, `produces_evidence`,
  `consumes`/`produces_artifact_types`, `features` por capability
  (`<name>/v<major>`), refinamentos de execução (`offline`, `read_only`,
  `network_required`, `credentials_required`) e `limitations` declaradas.
- `theforge/CapabilityNegotiationResult/v1` — resultado por provider:
  `state`, `dimensions` (match cru por dimensão), `history` (maturidade),
  `matched`, `missing`, `limitations`, `policy_conflicts`, `surface_fingerprint`.

## Estados

| state | significado |
|---|---|
| `FULL` | todos os gates passaram e toda dimensão avaliada é `full`/`not_applicable` |
| `PARTIAL` | gates passaram mas algo exigido está `missing`, `unknown`, `partial` ou `none` |
| `UNSUPPORTED` | o provider não declara a capability (nem por alias) |
| `INCOMPATIBLE` | um hard gate falhou — o conflito está nomeado |
| `UNRESOLVED` | não dá para decidir (sem manifest, estado `invalid`, …) |

## Hard gates × soft signals

Hard gates sempre vencem (ordem de avaliação — o primeiro que falha decide):

1. **policy** — trust `blocked` ou abaixo de `minimum_trust` → `policy_conflicts`.
2. **protocol** — `forge/v1` ausente de `protocols`.
3. **features** — `protocol_features` exigidas e não suportadas
   (`<name>/vN` aceita `vM`, `M ≥ N` — versionamento aditivo por nome).
4. **operation_class** — `operation_class` acima de `operation_class_ceiling`.
5. **mutation** — `mutation_allowed=false` com classe mutadora.
6. **technology** — `technologies` exigidas e `offer.technologies` declarado
   sem elas (offer ausente não falha: degrada a dimensão para `unknown`).
7. **evidence** — `required_evidence` declarado e a união
   `relations.produces ∪ offer.produces_evidence` não cobre.
8. **runtime** — `offline_required` × `execution.offline`/`offer.offline`,
   `network_allowed=false` × `requires_network`/`offer.network_required`,
   `credentials_allowed=false` × `offer.credentials_required`.

Soft signals **não** reprovam: `history` (maturidade da execução medida por
`provider+capability+surface_fingerprint` — `absent/cold/warming/mature`, e
`stale` quando a surface mudou, §43) só desempata entre resultados que já
passaram por todos os gates. Um `FULL` sem história vence um `INCOMPATIBLE`
com história perfeita — custo nunca supera segurança.

## Legacy mode

Capability sem `offer` negocia pelo manifest plano (`actions`, `state`,
`operation_class`, `execution`, `relations`, features implícitas). Toda demanda
que o manifest não consegue responder cai em `missing` como
`undeclared:<dimensão>` e o resultado vira `PARTIAL` — nunca `FULL` fingido,
nunca `INCOMPATIBLE` por ausência de declaração.

## CLI

```bash
theforge capabilities negotiate --requirement req.json [--root DIR] [--json]
theforge ask "diagnose this job" --requirement req.json [--use PROVIDER]
theforge plan "build the pipeline" --requirement req.json
```

`req.json` é um `CapabilityRequirement/v1`. `capabilities negotiate` lê o
registro local em cache — não dispara providers, não faz rede. Saída `--json`:
`{requirement, results[]}` ordenada deterministicamente (estado → dimensões →
história → fingerprint → id).

## Routing e planning

Quando a task carrega um `requirement`, o router troca o desempate
trust/história/id pela **ordenação de negociação**: só `FULL`/`PARTIAL` são
selecionáveis, `INCOMPATIBLE`/`UNRESOLVED`/`UNSUPPORTED` ficam fora de
`candidates` mas **permanecem em `decision.negotiation`** — a explicação do
"por que não" é parte do contrato, não log descartável. Vencedor `PARTIAL`
rota com `confidence: low` e seus `missing` em `unresolved`; alias que resolve
para capabilities diferentes continua `ambiguous` (a divergência não é fit).

- `theforge ask --requirement req.json` — o requirement vai no `TaskSpec`
  persistido (replay reproduz a mesma negociação) e cada resultado é gravado
  no artefato `routing` do run (`decision.negotiation`).
- `theforge ask --use PROVIDER` — pin de provider (§91): só vale se o provider
  for candidato negociável; um `INCOMPATIBLE` pinado cai em `no_route` com o
  estado e os conflitos nomeados — nenhum pin sobrevive a hard gate.
- `theforge plan --requirement req.json` — decomposição usa a seleção por fit;
  nós filhos recebem o requirement **canonicalizado** só quando o capability do
  nó resolve ao mesmo id no manifest do provider do nó (uma demanda por
  capability nunca contamina nós de outras capabilities). Em plan file
  (`--from`), `check_plan` vira gate de negociação: nó pinado `INCOMPATIBLE` é
  violação; `PARTIAL` vira limitation do plano, não violação.

## Ranking

Lexicográfico, sem aritmética: `state` (FULL>PARTIAL>UNSUPPORTED>UNRESOLVED>
INCOMPATIBLE) → tupla de dimensões (ordem canônica) → `history`
(mature>warming>cold>absent=stale) → `surface_fingerprint` → `provider id`.

## Limitações

- `platform_constraints`, `runtime_constraints` e `task_family` viajam no
  contrato mas ainda não têm gate — declarados, avaliados como `unknown` quando
  exigidos contra ofertas sem declaração correspondente.
- `capabilities negotiate` não executa nada; `ask --requirement`/`plan
  --requirement` executam o selecionado normalmente depois do fit.
