# Federated Capability Descriptor

Schema: `theforge/FederatedCapabilityDescriptor/v1`  
Source: projection of local `ForgeManifest`, `Capability` and optional `AgenticManifest`.

## Rules

- Local registry remains authority.
- Projection is read-only.
- `human` lists declared human entrypoints.
- `agentic` lists declared protocol/tool surfaces.
- `hosts` lists declared host adapters; empty means unknown, not compatible.
- `confidence=declared` means manifest evidence, not runtime success.
- `cost=unknown` stays unknown until measured observation exists.
- `limitations` preserve local caveats.
- `evidence` points to manifest/capability/surface identity.

## Example

```json
{
  "schema": "theforge/FederatedCapabilityDescriptor/v1",
  "provider": "api-forge",
  "provider_version": "0.1.0",
  "capability": "api.review",
  "actions": ["review"],
  "operation_class": "read_only",
  "invocation": {
    "human": ["cli"],
    "agentic": ["forge-protocol", "mcp"],
    "hosts": ["claude", "codex"]
  },
  "protocols": ["theforge/v1"],
  "features": ["trace-ref/v1"],
  "deterministic": true,
  "confidence": "declared",
  "cost": "unknown",
  "evidence": ["manifest:api-forge", "capability:api.review"],
  "limitations": []
}
```

## Consumer behavior

Consumers must negotiate requirement against descriptor, show missing dimensions, preserve refusal, and avoid fallback silently. Host installation still passes through governed install plan and approval.

Generate schema:

```text
python -m theforge.contracts.schema schemas
```
