# Remaining Risks

1. Real AWS/Azure provider homologation is not performed. It requires explicit
   credentials, account scope, cost approval and a non-production vault.
2. Production Obsidian vault verification is not performed; all vault activity
   in this cycle used temporary fixtures.
3. The codebase-memory graph service was unavailable during the audit; the
   call-graph evidence is source-based.
4. Pages is green on the fresh current-main run, but GitHub-hosted artifact
   retention/configuration remains an external operational dependency.
5. The final CI convergence and release matrix must be updated after the
   Cycle 2.8 branches are merged. Historical green runs cannot close that
   gate.
6. No PyPI/npm publication is claimed; publication requires explicit
   authorization under the cycle rules.

