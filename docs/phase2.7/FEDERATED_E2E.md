# Federated E2E

The final run must use pinned candidate commits and isolated installs for the
four specialists plus shared components. Required positive and negative
scenarios include authorization refusal, wrong workspace, conflict, rollback,
redaction, body-free traces, package installation and Portal integration.
Unavailable external providers remain `BLOCKED`, never simulated as success.

## Fail-closed gating (cycle 16.1 §5.1)

`scripts/federated_e2e.py` exits `0` only when **every** scenario and **every**
required eval is clean. The gate is `compute_gating(receipt)`:

- per-eval entries are normalized to `{id, required, verdict, state, detail}`;
  `state` is a closed set: `ok | failed | not-run | contradictory | invalid`;
- a required eval that failed, never ran, contradicted itself
  (`ok: true` alongside `FAIL`/`ERROR` or an `error` field), or has no result
  field is a blocking reason — optional evals (`required: false`) are counted
  but never block;
- every expected eval id (`EXPECTED_ROUTING_EVALS`,
  `EXPECTED_RESOURCE_EVALS`) must appear — a missing one blocks as
  `eval-not-run:<id>`;
- scenario verdicts outside `PASS`/`SKIP` (e.g. `FAIL`, `BLOCKED`, or a
  missing verdict) block;
- the written receipt is re-read and validated — an unreadable or
  structurally corrupt receipt adds `receipt-*` blocking reasons;
- a runner exception produces an error receipt (`runner_error` + traceback)
  and exit `2`; a clean run exits `0`, any blocking reason exits `1`.

All blocking reasons land on `receipt["gating"]["blocking_reasons"]` with
required/optional eval counts. Regression coverage:
`tests/test_federated_e2e.py` (deliberate eval failure, missing evals,
contradiction, receipt errors, runner exception, subprocess exit-code
propagation).

## SHA ↔ evidence binding (cycle 16.1 §5.6)

Receipts record `tested_commit` and `repo_shas` captured at run time through
`theforge.context.git.head_sha` (`git rev-parse --verify HEAD` via the
hardened runner) — never a hand-written value. `scripts/final_audit.py`
carries the same binding. When git cannot prove the commit the field is
`None` and the gap is honest — a missing SHA is never invented. Coverage:
`tests/test_evidence_binding.py`.

## Offline boundary (cycle 16.1 §5.2)

The deterministic core performs no outbound network I/O — proven, not
assumed: `tests/test_offline_e2e.py` instruments socket creation, connection
and DNS resolution to fail loudly under install → plan → resources → status →
uninstall and asserts zero attempts. The declared client boundary is pinned:
`theforge/registry/remote.py` (remote registry sync) is the only network
client import in the core; `_forge_portal*`/`graphstudio` are loopback
**server** boundaries; `service.update` shells out to `pip` and is not
claimed offline; `forge_bootstrap --allow-download` is the explicit opt-in.
