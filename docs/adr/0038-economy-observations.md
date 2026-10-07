# ADR 0038 — Observações de execução: grão atômico, axes nunca-silenciosos, maturidade por surface

- Status: aceito (2026-10-07)
- Cycle 4, Wave G — phases 41–48

## Contexto

O Cycle 3.1 já agrega `ProviderPerformance` (counters por
provider+capability+surface) e `EconomyRollup` (economia por run de plano).
Faltava o grão: o registro por execução que alimenta tanto o histórico
quanto uma visão global honesta — e a regra de nunca somar o que não foi
medido.

## Decisão

1. **`ExecutionObservation/v1` append-only** em `.forge/metrics/observations.jsonl`,
   um registro por execução que chega a `execute` — métricas numéricas são
   `null` quando não medidas (desconhecido ≠ zero), preservando a regra já
   usada por `EconomyMetric`.
2. **Escopo por fingerprints**: `surface_fingerprint` e
   `environment_fingerprint` fazem parte da identidade da observação; trocar
   a surface do provider marca o histórico antigo `stale` no receipt sem
   apagá-lo (§43).
3. **`task_family` nunca inferido**: vem do `CapabilityRequirement` da task —
   classificação determinística, zero heurística (§44).
4. **`GlobalEconomyReceipt/v1` derivado, nunca persistido**: `economy report`
   agrega o stream sob demanda; cada eixo é `observed`/`unresolved`/
   `conflict`/`not_applicable` e divergências ficam listadas em `conflicts`
   em vez de serem resolvidas pelo agregador (§45).
5. **Store limitado**: compaction determinística (descarta os mais antigos
   quando o arquivo passa de 1 MiB) — economia que cresce sem limite viraria
   ela mesma o desperdício.
6. **Economia de discovery no próprio report**: `registry_calls`,
   `metadata_bytes`, `network_ms` medem o custo da consulta; `--profile`
   (`economy`/`balanced`/`max`) controla quando a rede é sequer tocada (§47-48).

## Consequências

- O receipt global é reproduzível a partir do stream; não há estado paralelo
  para dessincronizar.
- Métricas que o provider não reporta ficam visíveis como `unresolved` —
  budgets futuros (Wave H) veem cobertura real, não zeros otimistas.
- `estimated` existe no vocabulário para forward-compat, mas o agregador v1
  nunca o produz — o core não fabrica valores.
