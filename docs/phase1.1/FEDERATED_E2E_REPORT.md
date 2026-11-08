# Federated E2E report

`uv run python scripts/knowledge_interop_smoke.py` passed with real subprocesses:
Product Forge Markdown chunking → Code Atlas projection → Agent Bridge
authorization → Forge Lens redacted provenance. Receipt: one chunk, one selected
item, one evidence id, seven telemetry attributes, `body_leakage=false`.

The same run attempted a cross-workspace pack and confirmed typed rejection. The
broader The Forge federation lab remains `PASS_WITH_LIMITATIONS`: external Agent
Bridge session `NOT_RUN` and cloud provider execution `BLOCKED` without authorized
credentials.
