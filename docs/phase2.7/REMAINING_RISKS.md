# Remaining Risks

- All configured post-merge CI and publish workflows are green on exact main
  SHAs except the standalone `forge-obsidian` publish, which is blocked by the
  missing PyPI Trusted Publisher configuration for its workflow.
- Linux installation/E2E and package smoke checks are represented in the
  merged release evidence; no local-only green run is promoted as hosted CI.
- External provider credentials are not fabricated; any unavailable provider
  remains explicitly BLOCKED (Cycle10.2 S12/S13).
- Local uncommitted audit artifacts in worktrees are outside the candidate
  release unless separately reviewed and committed.
