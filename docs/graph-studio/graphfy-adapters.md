# Adapters

Each adapter is `<pkg>/graphview.py` → `build_view(...) -> ForgeGraphView|None`.

| Forge | Engine | Status |
|---|---|---|
| the-forge | capability_graph (live) | SUPPORTED — 190n/214e verified |
| api-forge | graph JSONL store | SUPPORTED |
| spark-forge-aws | codeintel SQLite | SUPPORTED — 252n/269e verified |
| spark-forge-azure | graph.json store | SUPPORTED — 10,280n/23,514e verified |
| platform-forge | graph backend | SUPPORTED |
| forge-doctor-data | evidence graph | SUPPORTED — 208n verified |
| forge-doctor-api | service graph | SUPPORTED — 206n/177e verified |

Adapter rules: project only what the engine produced; translate
epistemic vocab explicitly (`explicit→declared`, `actual→observed`);
record truncations in `descriptor.limitations`; `unresolved_refs` never
become edges.
