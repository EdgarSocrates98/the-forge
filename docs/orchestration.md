# Orquestração por capability — OrchestrationReport (lf-0031)

A lane de orquestração responde: *"dado um intent e o que existe nesta
máquina, quais especialistas delegar, por quê, com que risco — e o que
voltou consolidado"*. Não é um segundo orquestrador: compõe as superfícies
que já existem (lf-0027 descoberta, lf-0028 delegação governada,
`delegation.py` execução argv). Nenhum caminho novo executa providers.

```text
intent + contexto
   └── discovery.discover_specialists   (lf-0027: quem existe, VERIFIED?)
        └── delegation_router.plan_delegation  (lf-0028: quem serve, justificado)
             └── orchestrate._filter_inputs    (requires ⊆ inputs declarados)
                  └── delegation.execute argv  (governed, um pick por vez)
                       └── EvidenceHandoff → OrchestrationReport
```

Programático: `theforge.orchestrate.orchestrate_plan(intent, ...)` e
`orchestrate_run(intent, ...)` retornam `Orchestration(report, discovery,
plan)`. CLI: `theforge orchestrate plan|run <intent>` com `--delegation
FILE` (declaração do consumer), `--input KIND` (insumos declarados),
`--authorize RISK`, `--no-probe`, `--allow-unverified`, `--max-hops`,
`--timeout-budget`, `--max-providers`.

## A declaração do consumer

`orchestrate.build_delegation()` monta o `theforge/SpecialistDelegation/v1`
default: **todo** especialista do catálogo vira um `SpecialistRef` com
`optional=True` — um forge nunca ganha dependência obrigatória de outro,
por construção. As `intents` declaradas vêm dos `intents`/`technologies`
dos knowledge packages, slugificadas (`"spark on aws"` → `"spark.on.aws"`).
O próprio consumer (`the-forge`) nunca entra como delegate — seria um ciclo
de profundidade zero. `--delegation FILE` substitui a declaração inteira.

## Plano justificado

`plan_delegation` (lf-0028) decide: elegível = declarado ∩ VERIFIED ∩
não-visitado; um intent declarado só é servido por um provider (dois
providers reivindicando o mesmo intent é `ambiguous`, nunca um chute);
cada pick carrega `justification` (intent casado, tokens de capability,
gate de risco, versão/estado). Refusals nomeiam o código da taxonomia —
`provider-absent`, `capability-absent`, `version-incompatible`,
`permission-denied`, `policy-refusal`, `insufficient-evidence`.

Acima disso, `_filter_inputs` aplica a regra do spec: uma capability cujo
`requires` declara insumos que o chamador não forneceu (`--input`) sai do
plano como `insufficient-evidence` — **nunca** se força um diagnóstico
(ex.: análise de event log) sem o dado que ele exige. É a mesma regra que
impede o Sentinel de "diagnosticar" sem logs/plans/runs declarados.

## Execução governada

Cada pick vira um hop na cadeia (`start_chain`/`admit_hop`: correlation id,
`visited_providers`, `max_hops`, `timeout_budget_s`), re-gateado pelo
`gate_capability` na hora da execução. `entrypoint` do manifesto é um
template argv (`{cli}`/`{python}`/`{checkout}`/`{target}`) resolvido por
`resolve_capability_argv` — `{cli}` só resolve se o binário existir de
verdade; sem resolução o pick é recusado `invalid-input`, nunca inventado.
Capability sem `entrypoint` (só Forge Protocol) reporta `prepared` —
honesto: planejada, não executada. A execução é `delegation.execute`
(FASE 5): subprocess argv, sem shell, timeout, tails de saída.

## `theforge/OrchestrationReport/v1`

Em `contracts/orchestration.py`, schema em
`schemas/OrchestrationReport.schema.json`. `kind`: `plan` (picks+refusals)
ou `run` (+estágios de execução, handoffs). Campos:

- `entries[]` — um por pick: status (`planned|prepared|completed|failed|
  blocked|refused`), `finding_class`, risks, justification, argv,
  `handoff_status` (`received|absent|invalid`).
- `findings[]` — consolidado por id de finding: `finding_class`
  (`STATIC|RUNTIME|ARCHITECTURAL|UNSPECIFIED` — a classe **declarada**
  pela capability, upper-cased; undeclared é UNSPECIFIED, nunca
  reclassificado), severidade/confiança do emissor original,
  `providers[]` e `correlated` (mesmo id em dois providers —
  co-ocorrência registrada, **nunca** promovida a prova independente).
- `unresolved[]` — cada gap com `code` da taxonomia + detalhe: ausências,
  recusas, runs sem handoff, integridade inválida.
- `recommended[]` — próximos passos determinísticos derivados das recusas
  (instalar o ausente — opcional —, autorizar riscos, declarar inputs).
- `provenance` — `discovery_digest`, `plan_sha256`, `delegation_tasks`,
  `receipts` — o relatório inteiro rastreia o que o produziu.

`orchestrate.persist_report(report, root)` grava o relatório redigido em
`.forge/orchestrations/<correlation>-<ts>.json` (redação obrigatória —
secret-shaped é recusado, nunca gravado).

## `finding_class`: quem declara a classe

O campo `finding_class` existe nos dois contratos: `DeclaredCapability`
(SpecialistCapability) e `Capability` do `theforge/ForgeManifest/v1`
(aditivo v1). Os adapters declaram nos seus catálogos o que cada
capability lê: `static` (revisão de fonte/artefato, sem run), `runtime`
(logs, métricas, evidência de execução) e `architectural` (contrato,
topologia, fronteira). O `capability_manifest` deriva a propaganda de
descoberta do manifesto vivo — a declaração do adapter vence; sem
declaração, `""` e o relatório agrupa em UNSPECIFIED. Nada no core infere
classe por nome ou heurística.

## O gap honesto: `data-sentinel-forge`

`forge-knowledge/data-sentinel-forge.json` documenta o especialista que
existe mas **não tem adapter**: sem superfície Forge Protocol ele nunca
atinge VERIFIED; todo pick vira `provider-absent` (ou
`capability-absent`) — recusa nomeada + recomendação opcional, nunca
silêncio e nunca diagnóstico fabricado. Um adapter mínimo é escopo de spec
futura; até lá, o relatório diz o que falta.
