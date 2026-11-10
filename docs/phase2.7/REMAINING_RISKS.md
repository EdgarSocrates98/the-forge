# Remaining Risks

- Hosted CI must be green on exact post-merge SHAs.
- Linux installation/E2E must be executed before a cross-OS certification.
- External provider credentials are not fabricated; any unavailable provider
  remains explicitly BLOCKED.
- Local uncommitted audit artifacts in worktrees are outside the candidate
  release unless separately reviewed and committed.
