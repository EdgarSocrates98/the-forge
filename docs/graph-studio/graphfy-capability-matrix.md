# Graphfy capability matrix — real capabilities per engine

Status: SUPPORTED / PARTIAL / UNSUPPORTED / UNVERIFIED.

| Capability | the-forge | api-forge | azure | platform | doctor-data | doctor-api | aws |
|---|---|---|---|---|---|---|---|
| snapshot listing | UNSUPPORTED | UNSUPPORTED | PARTIAL (state dir) | SUPPORTED (`graph snapshots`) | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED |
| node inspect | SUPPORTED | SUPPORTED (`graph query`) | SUPPORTED | SUPPORTED | SUPPORTED | SUPPORTED | — |
| edge inspect | SUPPORTED | SUPPORTED | SUPPORTED | SUPPORTED | SUPPORTED | SUPPORTED | — |
| neighbor expand | SUPPORTED | SUPPORTED (`graph query`) | SUPPORTED | SUPPORTED (`deps`/`dependents`) | PARTIAL | SUPPORTED (`edges()`) | — |
| path finding | UNSUPPORTED | SUPPORTED (`graph trace`) | SUPPORTED | SUPPORTED (`paths`, `identity-*`) | UNSUPPORTED | UNSUPPORTED | — |
| dep traversal | SUPPORTED | SUPPORTED | SUPPORTED | SUPPORTED | PARTIAL | SUPPORTED | — |
| impact analysis | UNSUPPORTED | SUPPORTED (`graph impact`) | SUPPORTED (`graph impact`) | SUPPORTED (`blast`) | UNSUPPORTED | SUPPORTED (`blast-radius`) | — |
| snapshot diff | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | SUPPORTED (`diff`) | UNSUPPORTED | UNSUPPORTED | — |
| temporal | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | SUPPORTED (`at`, `timeline`, edge temporal window) | UNSUPPORTED | UNSUPPORTED | — |
| search | PARTIAL (`--ref`) | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | — |
| export | SUPPORTED (JSON) | SUPPORTED (`export`: jsonl/neptune/rdf) | SUPPORTED | SUPPORTED | SUPPORTED (DOT/mermaid) | SUPPORTED (JSON) | — |
| epistemic vocab | explicit/observed/inferred | declared | static/live/artifact/knowledge | observed/planned/declared/inferred | declared | declared (evidence-recorded only) | — |

Capabilities marked PARTIAL exist but through a narrower real path than
the generic capability name suggests — adapters declare exactly these.
