# Phase 1 performance report

The new adapters are linear over already-selected items/chunks and use SHA-256
only for stable IDs/content hashes. No embeddings or network calls were added.

Product Forge's reproducible extraction benchmark (`scripts/knowledge_scale_bench.py`)
passed at 100, 1,000 and 10,000 documents with three iterations per size:

| documents | chunks | best elapsed | best throughput |
| ---: | ---: | ---: | ---: |
| 100 | 200 | 2.195 ms | 45,564 docs/s |
| 1,000 | 2,000 | 18.390 ms | 54,376 docs/s |
| 10,000 | 20,000 | 191.103 ms | 52,328 docs/s |

Receipt: `E:\projetos\FORJAS\.audit-work\product-knowledge-scale-20261107.json`.

The local SQLite Store + FTS benchmark (`productforge.knowledge.store_benchmark`)
also passed at the requested scales in one iteration on this Windows host:

| documents | write/index median | FTS search median | database |
| ---: | ---: | ---: | ---: |
| 100 | 129.920 ms | 0.495 ms | 140 KiB |
| 1,000 | 1,416.275 ms | 0.429 ms | 824 KiB |
| 10,000 | 14,166.374 ms | 0.870 ms | 7.61 MiB |

Both receipts are local baselines, not production SLOs. Portal rendering at
scale remains a separate benchmark and carries no implied claim here.
