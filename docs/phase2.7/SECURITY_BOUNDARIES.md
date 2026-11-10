# Security Boundaries

The Forge owns discovery/orchestration; Product Forge owns the neutral
Obsidian engine; specialists own domain intelligence; Agent Bridge owns
session/provider authorization; Code Atlas and Lens receive references, not
document bodies; Portal renders authorized, redacted responses.

Required invariants: explicit principal/workspace/session binding, no arbitrary
vault path, no secret/token persistence, no note content as instructions, no
ACL bypass, and no silent concurrent overwrite.
