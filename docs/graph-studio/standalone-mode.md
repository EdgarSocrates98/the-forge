# Standalone mode

Every forge with a graph surface runs its own Studio without The Forge:

| CLI | Graph source | Studio |
|---|---|---|
| `theforge graph --ui` | capability graph (built live) | yes |
| `apiforge graph ui --graph DIR` | JSONL store from `graph build` | yes |
| `sparkforge-aws graph ui --root .` | codeintel SQLite (`code index`) | yes |
| `sparkforge-azure graph ui` | graph.json (`graph build`) | yes |
| `platformforge graph ui` | backend (`graph build`) | yes |
| `forge-doctor-data graph ui` | evidence graph (analyzers) | yes |
| `forge-doctor-api graph . --ui` | service graph | yes |

Missing graph → named refusal (`*-GRAPH-NO*`) with the unlock command,
never a fabricated empty canvas.
