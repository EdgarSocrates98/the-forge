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
This is extraction-only evidence. SQLite persistence, FTS search and Portal
rendering at scale remain separate benchmarks and carry no implied claim here.
