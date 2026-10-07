# ADR 0039 — Shadow champion/challenger: recomendação por história, nunca promoção

- Status: aceito (2026-10-07)
- Cycle 4, Wave H — phases 51–55, 102–104

## Contexto

Com `ProviderPerformance` (Wave H do Cycle 3) e `ExecutionObservation` (Wave
G), o sistema já mede o suficiente para *recomendar* alternativas de
execução — mas agir sobre a recomendação exigiria auto-promoção, que o spec
proíbe: "before maturity: recommendation only" (§55) e "promote only when
enough observations, quality not degraded, cost improvement observed" (§52).

## Decisão

1. **`RoutingDecision.shadow` aditivo** (`ShadowRecommendation`, nested):
   provider/capability/maturity/evidence. `advisory: True` é literal —
   não existe variante executável do shadow no contrato.
2. **Cálculo puro e determinístico** em `strategy.shadow_recommendation`:
   challengers são os candidatos do mesmo capability id, escopo por surface
   fingerprint, ordenados por `performance.score` com desempate por id.
3. **Barra de promoção como condição de emissão**: challenger só é nomeado
   quando `warming`/`mature`, `verified_rate ≥` incumbente e contexto
   estritamente mais barato (ou incumbente sem história e challenger com
   runs verificados). A barra inteira vai em `evidence` — auditável.
4. **Zero efeito na seleção**: `selected` não muda; o tie-break por
   história já existente (H5) continua sendo o único lugar onde a história
   decide — e lá ela só desempata, nunca vence trust.
5. **Sem corpus de treino separado**: o shadow deriva do mesmo
   `ProviderPerformance` store de sempre — nenhum dataset paralelo, nenhum
   modelo.

## Consequências

- Um provider novo pode aparecer como challenger sem nunca ter sido
  selecionado — visibilidade, não ação.
- Quando a história em si decide (tie-break H5), não há shadow: o vencedor
  já é o medido, a recomendação seria circular.
- Cold history (1–2 runs) nunca aconselha — amostras pequenas não viram
  estratégia.
