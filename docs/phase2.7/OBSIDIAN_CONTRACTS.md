# Obsidian Contracts

`ObsidianNoteRef` identifies an existing note; `ObsidianNoteDraft` represents
candidate content; `ObsidianExportRequest` governs an explicit export. These
are not interchangeable and consumers must validate the canonical schemas.
Product Forge remains the implementation owner; specialists consume the
shared boundary rather than implementing another parser or vault engine.
