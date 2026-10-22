# Evals taxonomy & verification — the-forge (install-2.0 §7, lf-0038)

The-forge is the control plane: it owns no domain eval corpus. Its evals are
the verifications a host can invoke to prove a change — classified per §7.1,
exposed through the §7.2 conceptual ops, governed by §7.3 rules, driven by the
§7.4 flow. The declared catalog lives in `src/theforge/evals.py`
(`theforge.evals.SUITES`) and is persisted into the `forge/context/v1`
manifest (`eval_suites` + `discovery.ops`) by `install apply`.

## 7.1 — Classified inventory

| Suite | Kind | Surface | Environment |
|---|---|---|---|
| `unit-tests` | developer | `python -m pytest tests -q` | real |
| `cli-smoke` | developer | `python -m theforge --version` | real |
| `forgecontext-contract` | developer | `pytest tests/test_forgecontext.py tests/test_installkit_schemas.py` | real |
| `agent-assets` | developer | `pytest tests/test_agent_registry.py tests/test_agentic_parity.py` | real |
| `lab-collect` | runtime-decision | `theforge lab collect --mode A` (federated, offline fixtures) | simulated |
| `lab-gate` | runtime-decision | `theforge lab gate --results {r} --baseline {b}` | real |
| `replay-verify` | output-verification | `theforge replay {run_id} --mode verify` | real |
| `provider-conformance` | host-conformance | `theforge provider check -- {argv}` | real |

Counts: 4 developer, 2 runtime-decision, 1 output-verification,
1 host-conformance.

## 7.2 — Conceptual ops → real verbs

| Op | Command | Notes |
|---|---|---|
| `evals.list` | `theforge evals list` | classified catalog, metadata only |
| `evals.describe` | `theforge evals describe <suite>` | one suite; sealed content never inlined |
| `evals.run` | `theforge evals run <suite> [--input name=value]` | declared argv only; missing inputs = blocked |
| `evals.result` | `theforge evals result [receipt_id]` | receipts under `.forge/evals/` |
| `verification.plan` | `theforge verify plan <changed...> --risk <r> [--out plan.json]` | selects by triggers + risk floor; never executes |
| `verification.run` | `theforge verify run --plan <file> [--input name=value]` | authorized suites only; evidence receipt |

All six are declared in `discovery.ops` of the installed `forge/context/v1`
manifest — the `DISCOVERY_OPS` enum grew 8 → 14 (`_FORGECONTEXT_VERSION`
1.2.0; `ForgeContext.schema.json` `maxProperties` 14). Sibling forges vendor
the same engine copy, so their manifests may use the same op names.

## 7.3 — Security rules enforced

- **Holdout answers never exposed.** Suite payloads carry ids, kinds, argv,
  triggers and environment markers — there is no field for expected answers.
  `describe` reports declared `baselines`/`holdouts` as *path + sha256 +
  count* with the literal marker `sealed — never inlined into agent-facing
  output`; contents are never read into output. A test injects a synthetic
  suite with a sealed file and asserts the answer bytes never appear.
- **Executor ≠ evaluator.** `evals run` executes the declared argv; verdicts
  come from exit codes recorded in the receipt — the runner never grades its
  own content. Verification suites that *evaluate* (`lab-gate`,
  `replay-verify`, `provider-conformance`) are separate declarations.
- **Baselines hash-protected.** Every file input (`--input name=path`) is
  recorded in the receipt as `inputs_recorded[name] = {path, sha256}` —
  tampering a baseline between runs is visible. `lab gate` still fails on
  regression.
- **No destructive tests, no cloud mutation.** `destructive=True` suites are
  refused (`verdict: blocked`) — the flag exists as a guard; nothing is
  declared destructive today. Eval subprocesses run under `safe_env()` —
  credentials never propagate. No suite performs cloud mutation.
- **Simulated ≠ real.** Each suite is marked `environment: real|simulated`;
  receipts carry `environment` + `simulated_proof` and a proof note.
  `lab-collect` is `simulated` (offline fixtures, `not_applicable` semantics
  — never live-environment proof).

## 7.4 — Plan → run → evidence

```text
theforge verify plan src/theforge/evals.py --risk low --out plan.json
theforge verify run --plan plan.json [--input results=cur.jsonl --input baseline=base.jsonl]
theforge evals result <receipt_id>
```

- Selection is deterministic: suite `triggers` (globs) vs the changed set;
  the risk floor widens it (`medium` adds all developer evals, `high` sweeps
  the catalog); an empty selection escalates to the full sweep and says why.
- A selected suite with unfilled inputs is planned `blocked`, runs
  `blocked`, and names `unresolved: input:<name>` — explicit, never silent.
- Verdicts: `pass | fail | inconclusive | blocked`; a run receipt concludes
  proportionally — inconclusive/blocked never reads as a pass.

## 7.5 — Agent contracts

Canonical specs: `agentic/agents/*.toml` (`theforge/AgentSpec/v1`), registry
`theforge agents list`; Codex mirror `.codex/agents/*.toml` rendered by
`scripts/agentic/render_agents.py` (`--check` green). Coverage of the §7.5
concerns:

- **protocols** → `input_contracts`/`output_contracts` per spec;
- **handoff + risk restrictions** → `authority` (closed literal) +
  `allowed_actions`/`forbidden_actions` + `UNIVERSAL_FORBIDDEN`
  (`check_authority`, ADR-0054);
- **knowledge retrieval / tools** → `required_skills` + `max_skills` +
  `context_budget_bytes` bounds;
- **validators / escalation / case persistence** → spec contracts reference
  `VerifyRequest`/`VerifyVerdict` etc.; the shared runtime contract is the
  canonical `AGENT_PROTOCOL.md` generated per consumer workspace by
  `forge_context.install_docs` — referenced, never duplicated into each spec.
- `python scripts/agentic/audit_assets.py` → no failing findings;
  `render_agents.py --check` → 8 specs in sync.

## Gates

Focused: `pytest tests/test_evals_cycle5.py tests/test_forgecontext.py
tests/test_installkit_schemas.py -q`. Full suite: deferred to CI
(`python -m pytest` > 15 min).
