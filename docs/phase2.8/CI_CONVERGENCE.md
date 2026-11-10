# Cycle 2.8 CI Convergence

## Baseline current-main evidence

Before modifications, the ten in-scope `main` heads had no open PRs. Current
green evidence included Platform Forge `42867920506`, The Forge `42864197031`,
API Forge CI `42844903701`, specialist package runs `42851531014`,
`42851527774`, `42851527596`, `42851527863`, `42851528746`, and Portal CI
`42810286796`.

The historical Platform failure was not reused as evidence: the current
Platform `main` run was green. The historical API Pages failure was separately
revalidated by fresh run `42876078863`.

## Final-cycle rule

This document must be updated after each Cycle 2.8 PR merge with the exact
merged SHA, workflow run ID, required-job result, artifact/version and skipped
or externally blocked lanes. A green run on an older SHA is never used as
evidence for a final SHA.

PyPI/npm publication was not triggered by this cycle because the execution
rules prohibit publication without explicit authorization. Existing successful
publication evidence is recorded as historical evidence only.

