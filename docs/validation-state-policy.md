# Validation state policy

The Forge separates **code/test outcome** from **CI transport/execution state**.

A workflow run is not a code failure merely because GitHub created jobs but
executed no steps (for example, Actions quota/billing/runner unavailability).
Likewise, a blocked run is never treated as green.

Canonical states:

| State | Meaning |
|---|---|
| `LOCAL_VERIFIED` | required local/static gates executed successfully |
| `REMOTE_VERIFIED` | required remote workflow jobs executed their steps and passed |
| `REMOTE_BLOCKED` | remote workflow could not execute test steps for an external reason |
| `REMOTE_FAILED` | remote workflow executed at least one required gate and that gate failed |
| `NOT_RUN` | no evidence exists yet |

For GitHub Actions specifically:

- jobs with missing/empty `steps` are **not test execution evidence**;
- if every required job has no executed steps, classify the workflow
  `REMOTE_BLOCKED`;
- if required jobs executed steps and a required gate failed, classify
  `REMOTE_FAILED`;
- only executed-and-passing required jobs can produce `REMOTE_VERIFIED`;
- quota/billing/runner failures must never be rewritten as code failures;
- blocked remote validation remains a release blocker when the release policy
  requires remote proof.

The classification logic lives in `scripts/ci/classify_remote_validation.py`
and is intentionally stdlib-only/offline: it consumes a previously exported
GitHub jobs JSON document and never calls GitHub itself.
