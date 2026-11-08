# Knowledge authorization contract

Authorization is evaluated immediately before provider injection. A bound session
must match principal, workspace and (when bound) product. Every declared source
must have a non-empty version and an explicit source allowlist grant. Inline items
must carry `item_id`, `source_id`, `document_id`, `workspace_id`, `version` and
`content_hash`; their source/version/workspace/product must agree with the pack.

Reference-only packs remain compatible in `KnowledgeContextPack/v1`. Inline content
is now represented by the typed `KnowledgeContextItem` shape and closed JSON schema.
The Agent Bridge applies the same boundary in its Pydantic contract.
