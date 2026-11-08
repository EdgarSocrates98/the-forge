# Doctor roster closure — 2026-11-08

This receipt records the repository-level closure of the two missing Doctor
rosters in the federated catalog. It does not claim a live provider session or
cloud execution.

| Provider | PR / merge | Packaged specialists | Portal proof |
|---|---|---|---|
| Doctor API | PR #99, merged as `fe99013` after full CI | `api-diagnostic-investigator`, `api-contract-reviewer`, `api-handoff-governor` | `tests/test_forge_portal.py`: 16 passed locally after the fallback-path fix |
| Doctor Data | PR #78, merged as `2fc30f4` | `data-diagnostic-investigator`, `data-quality-reviewer`, `data-platform-reviewer` | `tests/test_portal_adapter.py`: 19 passed before merge |

The implementation uses each provider's declared `agent_roster_paths`, checks
that resolved assets remain inside the roster directory, and exposes the
canonical frontmatter through the Portal adapter. The post-merge catalog
capture reports `agent_roster.state=CONFORMANT` and `routable=true` for both
providers. Across the 12 specialist entries exposed by The Forge, every roster
is now conformant and routable; installation state is still reported
independently (`INSTALLED`, `DISCOVERED` or `INSTALLABLE`).
