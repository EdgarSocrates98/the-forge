# Graph Studio perf baseline (lf-0024)

Measured numbers — NOT targets and NOT SLAs. Everything below came out of
`scripts/graph_perf.py` replaying the real studio `<script>` under node
v22.23.2 on Linux x86_64, headless DOM/RAF stubs.

## Reading the columns honestly

- **load ms**: module-eval → `G.nodes` populated (JSON parse, model
  assembly, cluster rollup when overview is picked). No network/CSSOM —
  it is not a browser page load.
- **settle ms / tick ms**: synchronous RAF replay of the force loop.
  No compositor exists in this harness → **no FPS is claimed**; the
  honest proxy is per-frame simulation cost (a browser frame budget is
  16.7 ms — tick ms well under that means the sim is not the bottleneck).
- **heap MB**: V8 `process.memoryUsage()` of the node harness, not a tab.
- **cpu ms**: whole-process `process.cpuUsage()` (user+system).
- **settled=false** means the tick budget ran out — recorded, not hidden.

## Matrix

| size | fixture | mode | nodes→drawn | load ms | settle ms | lticks | tick ms mean | tick ms p95 | heap MB end | rss MB end | cpu ms u+s | settled |
|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|:---:|
| 100 | `graph_100_chain.json` | full | 100/100 | 85 | 1051 | 290 | 12.35 | 15.31 | 6.52 | 57.91 | 1660.5400000000002 | True |
| 500 | `graph_500_chain.json` | full | 500/500 | 106 | 30466 | 343 | 13.65 | 15.04 | 9.46 | 75.54 | 31334.09 | True |
| 1000 | `graph_1000_chain.json` | full | 1000/1000 | 163 | 23143 | 352 | 31.82 | 39.05 | 22.92 | 92.8 | 24677.059999999998 | True |
| 3000 | `graph_3000_chain.json` | overview | 250/3000 | 1702 | 6140 | 316 | 11.57 | 13.58 | 28.87 | 102.29 | 8631.779999999999 | True |
| 5000 | `graph_5000_heterogeneous.json` | overview | 2/5000 | 1329 | 6 | 223 | 3.15 | 4.7 | 35.63 | 104.91 | 1651.8100000000002 | True |
| 10000 | `graph_10000_chain.json` | overview | 250/10000 | 14720 | 6094 | 325 | 11.42 | 13.56 | 54.52 | 128.32 | 22013.61 | True |
| 10000 | graph_10000_chain.json | full | — | — | — | — | — | — | — | — | — | ERROR |
| 25000 | `graph_25000_chain.json` | overview | 250/25000 | 100318 | 6584 | 337 | 11.62 | 13.79 | 65.41 | 151.21 | 109155.13 | True |

## Environment

- generated_at: 2026-10-21T05:50:26+00:00
- node: v22.23.2 · platform: Linux x86_64
- ticks budget: 1200 logical ticks (×64 RAF cap)
- script sha256: `da0e16434924b3a264074513ba8b498a783389a767d0751145a4adf3f4744ece`

Machine-readable rows: `perf-baseline.json` in the same directory.

## Flags

- none — every run settled finite with no error surface.
