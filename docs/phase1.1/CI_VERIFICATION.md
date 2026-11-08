# CI verification

Merged prerequisites: Agent Bridge PR #13 (`1c560542`), Product Forge PR #31
(`a73c36f`) and The Forge PR #173 (`d9cce9f`). The new contract/parity changes are
open as Agent Atlas PR #37 and The Forge PR #174; their GitHub checks must be green
before those candidate commits are merged.

Local CI-equivalent gates are recorded in `evidence-manifest.json`. A skipped
conditional job is not interpreted as a pass.
