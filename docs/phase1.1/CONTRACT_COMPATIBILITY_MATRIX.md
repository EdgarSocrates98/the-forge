# Contract compatibility matrix

| Producer/consumer | Contract | Compatibility |
|---|---|---|
| Code Atlas → The Forge | `theforge/KnowledgeContextPack/v1` | `IMPLEMENTED_UNVERIFIED`: inline provenance added; PR #174 pending CI |
| The Forge → Agent Bridge | `KnowledgeContextPack/v1` | `VERIFIED`: Bridge accepts refs and validates inline items |
| Agent Bridge → Forge Lens | redacted pack provenance | `VERIFIED`: ids/counts/versions only |
| Product Forge embedded Bridge | Bridge Python + manifests | `VERIFIED` locally and by dedicated parity gate |

Schema regeneration command: `uv run python -m theforge.contracts.schema schemas`.
