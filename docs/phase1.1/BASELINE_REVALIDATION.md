# Baseline revalidation

Executed on Windows PowerShell, Python 3.12, uv-managed environments, 2026-11-08.

| Repository | Baseline / candidate evidence | Result |
|---|---|---|
| forge-agent-bridge | full suite after authorization fix | `128 passed` |
| product-forge | full suite after URL, Defuddle and vendored-copy fixes | `225 passed, 1 skipped` |
| the-forge | KnowledgeContextPack + schema focused suite | `23 passed` |
| code-atlas-forge | full suite after adapter fix | `1663 passed, 21 skipped` |
| forge-lens | full baseline suite on main | `VERIFIED` (exit 0; benchmark suite included) |
| forge-portal | Python suite on main | `200 passed, 15 skipped` |

The skips are platform/credential/optional-tool cases and remain classified in
`REMAINING_RISKS.md`; they are not counted as passes.
