# ADR 0033 — Capability Negotiation v2: dimensional, gated, nunca score opaco

- Status: aceito (2026-10-07)
- Cycle 4, Waves A/B — phases 4–14, 89–91, 114–115

## Contexto

O routing de Cycles 1–3 responde "quem tem a capability X?" por signals
(declarados) + tie-break determinístico. Para federação/discovery isso não
basta: um provider remoto ou um candidato a instalação precisa ser julgado pelo
que a capability **oferece** (tecnologias, evidência, runtime, features) contra
o que a tarefa **exige** — antes de qualquer instalação ou execução.

## Decisão

1. **Três contratos v1**: `CapabilityRequirement` (o pedido; só `capability`
   obrigatório), `CapabilityOffer` (oferta rica embutida aditivamente em
   `manifest.capabilities[].offer` — ForgeManifest v1 não quebra), e
   `CapabilityNegotiationResult` (fechado, core-produced).
2. **Hard gates × soft signals separados**. Gates falham → `INCOMPATIBLE` com
   `policy_conflicts`/`missing` nomeados; dimensões soft degradam para
   `PARTIAL` — nunca uma recusa silenciosa nem um `FULL` fabricado.
3. **Dimensões nomeadas, sem score opaco** (`dimensions` +
   `history`): o ranking é lexicográfico e reversível — toda decisão é
   explicável sem consultar pesos ocultos.
4. **Feature versioning aditivo**: `name/vN` exigido é satisfeito por `name/vM`
   com `M ≥ N`; features implícitas (`supported_features`) contam igual às
   declaradas — um manifest pré-features continua negociável.
5. **História escopada por surface**: maturidade (`absent/cold/warming/mature`)
   só conta `ProviderCapabilityPerformance` do fingerprint exato; surface mudou
   → `stale`, história antiga não herda.
6. **Offline e local**: `capabilities negotiate` lê só o registro em cache.
   Provider que não declara a capability é `UNSUPPORTED`; sem manifest é
   `UNRESOLVED` — estados distintos porque são problemas distintos.

## Consequências

- Seleção v3 (Wave B) reutiliza `negotiate_all` como ordenação de candidatos;
  `route`/`ask` continuam idênticos quando nenhum requirement é fornecido.
- Providers antigos sem `offer` ficam em "legacy mode" (PARTIAL quando há
  demandas não respondíveis) — compatibilidade retroativa preservada (§114).
- A negação é *negável*: `UNSUPPORTED`/`INCOMPATIBLE`/`UNRESOLVED` carregam a
  razão exata para discovery decidir se vale buscar remoto (Wave E).
