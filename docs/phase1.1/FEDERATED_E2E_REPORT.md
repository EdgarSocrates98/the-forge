# Federated E2E report

`uv run python scripts/knowledge_interop_smoke.py` passed with real subprocesses:
Product Forge Markdown chunking → Code Atlas projection → Agent Bridge
authorization → Forge Lens redacted provenance. Receipt: one chunk, one selected
item, one evidence id, seven telemetry attributes, `body_leakage=false`.

The same run attempted a cross-workspace pack and confirmed typed rejection. The
broader The Forge federation lab remains `PASS_WITH_LIMITATIONS`: external Agent
Bridge session `NOT_RUN` and cloud provider execution `BLOCKED` without authorized
credentials.

The local Forge Lab was independently rerun on 2026-11-08 with the real
subprocess collector. `compat-manifest-parity` passed 14/14, and all seven
declared MultiForge scenarios passed, including the API, Platform and Spark
participants (`2/2` or `3/3` declared labs according to the scenario). The
portable `{python}` command token and explicit `lab.extras: []` declarations
were exercised on Windows. This closes the local L1 federation path; it does
not change the external-session or cloud boundary above.
