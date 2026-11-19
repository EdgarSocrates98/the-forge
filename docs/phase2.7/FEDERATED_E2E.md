# Federated E2E

The final run must use pinned candidate commits and isolated installs for the
four specialists plus shared components. Required positive and negative
scenarios include authorization refusal, wrong workspace, conflict, rollback,
redaction, body-free traces, package installation and Portal integration.
Unavailable external providers remain `BLOCKED`, never simulated as success.

## Fail-closed gating (cycle 16.1 §5.1, hardened in 16.1.1 §4.1)

`scripts/federated_e2e.py` exits `0` only when **every required scenario is
`PASS`** and **every required eval is clean**. Scenario requiredness is no
longer implicit — a versioned `SCENARIOS` inventory declares every emitted
scenario id with `required` (default `true`) or an explicit justification
(e.g. `L-portal-cli` is optional where `portal_core` is absent). Emitting a
scenario the inventory does not declare is itself a blocking outcome, so no
required claim can be silently renamed away.

The gate distinguishes **disproof** from **inconclusion**:

- `blocking_reasons` — scenario `FAIL`/`ERROR`/unknown-verdict, a required
  scenario absent from the receipt (`scenario-not-run`), an undeclared
  scenario id, eval failures, corrupt/unreadable receipt, runner exception
  (exit `2`);
- `unverified_reasons` — a required scenario that is `UNVERIFIED`,
  `BLOCKED`, `SKIPPED` or `NOT_APPLICABLE`: no proof either way. These do
  **not** masquerade as failures, but they are equally fatal to
  certification — a required claim without proof is not `PRODUCTION_READY`.
- optional/inventory-justified scenarios may be inconclusive without
  blocking; an optional `FAIL` still blocks (optionality forgives
  inconclusion, never disproof).

Per-eval rules are unchanged: entries normalize to
`{id, required, verdict, state, detail}` with closed state
`ok | failed | not-run | contradictory | invalid`; a required eval that
failed, never ran, contradicted itself or lacks a result blocks as
`eval-*`; `EXPECTED_ROUTING_EVALS`/`EXPECTED_RESOURCE_EVALS` must all
appear.

The receipt now carries `certification_verdict`
(`"PASS"` only when both reason lists are empty), `commands` (argv),
`environment` (python/platform), `gating.required_coverage`
(`{required, passed, failed, inconclusive}`), `gating.unverified_reasons`
and `gating.scenario_inventory`, alongside the existing SHA binding. Exit
codes: `0` iff verdict PASS, `1` on any gating failure, `2` on runner
crash. Regression coverage: `tests/test_federated_e2e.py` +
`tests/test_federated_e2e_gating.py` (every inconclusive state, empty
scenario set, unknown verdicts, eval negatives, receipt validation).

## SHA ↔ evidence binding (cycle 16.1 §5.6)

Receipts record `tested_commit` and `repo_shas` captured at run time through
`theforge.context.git.head_sha` (`git rev-parse --verify HEAD` via the
hardened runner) — never a hand-written value. `scripts/final_audit.py`
carries the same binding. When git cannot prove the commit the field is
`None` and the gap is honest — a missing SHA is never invented. Coverage:
`tests/test_evidence_binding.py`.

## Offline boundary (cycle 16.1 §5.2, real proof in 16.1.1 §4.2)

The deterministic core performs no outbound network I/O — proven, not
assumed. `tests/test_offline_e2e.py` instruments socket creation, connection
and DNS resolution to fail loudly under install → plan → resources → status →
uninstall and asserts zero attempts; the `I-offline` federated scenario
repeats the same instrumentation **inside the runner** — it patches
`socket.socket`/`create_connection`/`getaddrinfo` to record-then-explode,
runs discovery, resource listing/retrieval and `plan_context` over the
materialized workspace underneath, proves the block is live with an injected
outbound probe, and passes only on `zero-outbound-attempts` (the attempt log
is bound to the scenario evidence). The declared client boundary is pinned:
`theforge/registry/remote.py` (remote registry sync) is the only network
client import in the core; `_forge_portal*`/`graphstudio` are loopback
**server** boundaries; `service.update` shells out to `pip` and is not
claimed offline; `forge_bootstrap --allow-download` is the explicit opt-in.
