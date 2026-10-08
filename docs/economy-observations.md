# Observações de economia (Cycle 4, Wave G)

Cada execução de provider que chega a `execute` grava uma
`theforge/ExecutionObservation/v1` em `.forge/metrics/observations.jsonl` —
o grão atômico da economia, append-only, gitignored, escrito após
`security.redact`. Falha de escrita vira `limitation` do run, nunca run falho.

## ExecutionObservation/v1

Campos de identidade (o que rodou):

- `run_id`, `provider`, `capability`, `status`, `created_at`
- `task_family` — rótulo determinístico vindo do `CapabilityRequirement`
  (nunca inferido; `null` quando a task não declara)
- `surface_fingerprint` — a surface do manifest usada na execução; trocar a
  surface inicia história nova, a antiga permanece registrada mas responde
  apenas pelo próprio fingerprint
- `environment_fingerprint` — classe de ambiente (SO + arquitetura + Python
  major.minor); agrupa histórias comparáveis sem identificar a máquina
- `profile`, `complexity` — perfil efetivo e nível medido da task

Métricas (todas `null` quando não medidas — desconhecido nunca é zero):

- Contexto: `context_bytes`, `context_items`, `context_items_cited`
  (ROI de contexto: bytes entregues, itens entregues, itens citados pela
  evidência retornada)
- Chamadas: `provider_calls` (sempre 1 — o execute), `tool_calls`,
  `semantic_calls` (planner/resolver semânticos do run)
- Custo: `tokens`, `cost_usd` (do `ProviderEconomyReceipt` do provider;
  `unresolved`/`not_applicable` viram `null`), `wall_time_ms` (medido pelo
  core)
- Resultado: `verification` (`passed`/`failed`/`not_performed`),
  `evidence_count`, `artifact_count`

## GlobalEconomyReceipt/v1

`theforge economy report` agrega o stream por eixo — read-only, offline:

```text
economy: 12 observation(s) across 12 run(s)
  context_bytes    observed = 140228  (12 observed, 0 unknown)
  cost_usd         unresolved  (3 observed, 9 unknown)
  tokens           conflict  (11 observed, 1 unknown)
history maturity:
  fixture-spark/spark.performance@f2ab…  mature
conflict: r9 fixture-spark/spark.performance tokens: 100.0 vs 240.0
```

Regras por eixo (nunca-silencioso):

- `observed` — toda observação contada carregava valor; `value` é a soma
- `unresolved` — cobertura parcial; soma parcial nunca é mostrada
- `conflict` — duas observações do mesmo `(run_id, provider, capability)`
  divergem; o desacordo fica listado em `conflicts`, o eixo não escolhe lado
- `not_applicable` — nenhuma observação registrada
- `estimated` — reservado: o core não inventa estimativas (aceito no decode
  para forward-compat)

Duplicatas idênticas do mesmo `(run_id, provider, capability)` colapsam —
replay/regravação não infla o histórico.

## Maturidade do histórico

`maturity` no receipt mapeia cada chave `provider/capability@surface` do
`ProviderPerformance` para `absent`/`cold`/`warming`/`mature`/`stale`
(mesmos limiares de `negotiation.maturity`: cold < 3, warming < 8 runs).
Quando a surface muda, as entradas do fingerprint antigo viram `stale` —
história preservada, nunca reutilizada silenciosamente.

## Compaction

`observations.jsonl` é limitado a `MAX_OBSERVATIONS_BYTES` (1 MiB): ao
estourar, o arquivo regrava mantendo os registros mais novos que couberem
em metade do orçamento — determinístico e explícito (`limitation` no run).

## Economia de discovery (§47-48)

`capabilities discover` reporta o custo da própria consulta:
`registry_calls` (fontes que serviram documento), `metadata_bytes` (bytes
consumidos), `network_ms` (latência real de rede; `null` quando só cache
ou `local-file`). `--profile` controla a ansiedade da consulta remota:

- `economy` — remote só quando nenhum provider local declara a capability
  (`UNSUPPORTED`/`INCOMPATIBLE`); qualquer claimant local dispensa a rede
- `balanced` (default) — remote só quando nada local satisfaz `FULL`
- `max` — sempre consulta: compara claims remotos mesmo com fit local FULL
- `--remote` — força a consulta sob qualquer profile


## Plan retries e budget global

A observação atômica de um child run continua registrando `provider_calls = 1`
quando aquele run alcança `execute`. No plan run, porém, retries são contabilizados
individualmente:

- `RunBudget.provider_calls = plan_nodes × retry.max_attempts` — teto autorizado;
- `RunTelemetry.providers_executed` — chamadas `execute` realmente realizadas;
- a reserva extra aparece em `RunBudget.adjustments`;
- se ainda houver gaps unresolved e o gasto real atingir o teto, o
  `GlobalStopDecision` usa `stop_budget_exhausted`;
- se a execução já resolveu e verificou o trabalho, consumir o teto não substitui
  `stop_sufficient_evidence`.

Assim retry deixa de ser custo invisível sem transformar reserva de pior caso em
gasto observado.
