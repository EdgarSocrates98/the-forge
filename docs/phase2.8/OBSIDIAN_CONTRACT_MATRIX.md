# Obsidian Contract Matrix

| Contract | Version | Body | Producers | Consumers | Compatibility |
|---|---|---|---|---|---|
| `ObsidianNoteRef` | `theforge/ObsidianNoteRef/v1` | No | Ref projections, Atlas/Lens identity boundaries | Code Atlas, Forge Lens, Portal/reference consumers | Existing body-free shape preserved |
| `ObsidianNoteDraft` | `theforge/ObsidianNoteDraft/v1` | Markdown allowed | AWS, Azure, API, Platform adapter builders | Review/export preparation and explicit `to_obsidian_note_ref` adapters | New explicit version; no silent body in NoteRef |
| `ObsidianExportRequest` | `theforge/ObsidianExportRequest/v1` | No | Authorized export planners | Export authorization and idempotent vault operation | Version rejects unknown schema |
| `theforge/ObsidianSyncReceipt/v1` | Existing | No body | Neutral vault engine | Receipts, rollback, Lens | Preserved |

The four specialist adapters now announce `ObsidianNoteDraft` when they carry
Markdown and expose an explicit body-free projection helper. Canonical schema
generation produces `schemas/ObsidianNoteDraft.schema.json` and
`schemas/ObsidianExportRequest.schema.json`. Draft construction validates the
UTF-8 content hash; export requests validate vault/path/hash/idempotency fields.

Contract tests cover valid and invalid references, body exclusion, hash
mismatch, path traversal, unknown version, round-trip projection, and schema
validation. The source and installed federation harnesses both use the
explicit projection before Atlas/Lens boundaries.

