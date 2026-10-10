# Graph Studio architecture

```text
┌─ browser ────────────────────────────────────────┐
│ single-file HTML+canvas app (embedded, no Node)   │
│ force-directed layout · zoom/pan · inspect ·      │
│ kind+edge filters · epistemic dash styles · search│
└──────────────▲───────────────────────────────────┘
               │ GET only, 127.0.0.1
┌──────────────┴───────────────────────────────────┐
│ _graphstudio.py — stdlib ThreadingHTTPServer      │
│ / /api/health /api/graphs /api/graph/<id>         │
│ read-only (POST/PUT/DELETE → 405), no-store,      │
│ ephemeral port default, --no-browser for SSH      │
└──────────────▲───────────────────────────────────┘
               │ ForgeGraphView/v1 dicts
┌──────────────┴───────────────────────────────────┐
│ per-repo graphview adapter → `graph view --json`  │
│ maps real engine → contract, declares only real   │
│ capabilities, preserves provenance verbatim       │
└──────────────▲───────────────────────────────────┘
               │ each forge's own engine (authoritative)
        platformforge.graph · apiforge.graph ·
        sparkforge_azure.graph · ServiceGraph ·
        capability_graph · core/graph
```

Key decisions:

- **No FastAPI/Node/React**: the prompt allows "outra solução de baixo
  custo operacional". A stdlib server + vanilla canvas keeps every repo
  zero-dependency and the studio installable under Economy.
- **Vendored `_graphstudio.py`** per repo (installkit convention): each
  forge opens its own Studio without the-forge (§4.6); the-forge adds
  the federated merge.
- **`graph view --json` is the uniform producer**: the-forge federation
  subprocesses sibling CLIs (same channel as delegation) — no
  cross-imports, works from checkouts without installed launchers.
- **CLI surface lands where it fits**: `graph ui` subcommand on group
  CLIs, `ui` positional on platform-forge's choice list, `--ui` flag on
  command-style `graph` (the-forge, doctor-api). Documented, not forced.
- **Browser opens only when asked**; `--no-browser` prints the URL +
  SSH `-L` hint (§1.3, §5.15).
