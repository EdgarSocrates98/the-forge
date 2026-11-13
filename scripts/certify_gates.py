#!/usr/bin/env python3
"""ONDA 1 — certification gate engine (P0-001).

Pure, deterministic evaluation layer: takes evidence artifacts produced by
independent runners (operational-e2e.json, baseline.json,
certification-lock.json, live repo/index/CI probes) and computes every
certification dimension from named required checks. There is NO constant
PASS anywhere in this module — a dimension only passes when every required
check on its evidence passes.

Separation of concerns (Onda 1.6):
- execution: unified_e2e.py, unified_baseline.py, unified_lock.py (producers)
- collection: unified_certify.py loads the artifacts + live probes
- interpretation/decision: THIS module — gates + verdict only

Statuses: PASS / FAIL / BLOCKED / UNVERIFIED / NOT_APPLICABLE.
- FAIL is never converted to UNVERIFIED (a check that ran and failed stays failed);
- BLOCKED never becomes PASS;
- a missing or empty artifact is evidence absence, never success;
- one passed test never passes a whole dimension (required checks are plural).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

REQUIRED_SCENARIO_FIELDS = {
    "status", "steps", "commands", "environment", "os", "python",
    "repo_shas", "versions", "evidence", "limitations",
}

DOMAIN_SCENARIOS = ("A-aws", "B-azure", "C-api", "D-platform", "E-product",
                    "F-doctors", "G-sentinels", "H-atlas", "I-lens")
FED_SCENARIOS = ("federation-routed", "federation-delegated",
                 "federation-multidomain", "federation-ambiguous",
                 "federation-partial")
INTEGRATION_SCENARIOS = ("mcp", "bridge")


@dataclass
class CheckResult:
    """One required check inside a gate."""
    id: str
    ok: bool
    detail: str = ""


@dataclass
class GateResult:
    """Typed evidence model of one certification dimension (Onda 1.2)."""
    gate_id: str
    name: str
    description: str
    scope: str
    repos: list[str]
    shas: dict[str, str]
    environment: dict[str, Any]
    required_checks: list[CheckResult]
    artifacts: list[str]
    provenance: dict[str, Any]
    timestamp: str
    evidence: dict[str, Any]
    status: str = "UNVERIFIED"
    block_reason: str = ""
    acceptance_criteria: str = ""

    def finish(self) -> GateResult:
        """Derive the final status from the checks — decided here, not by caller."""
        if self.status != "UNVERIFIED":
            return self  # terminal state decided by the gate itself (BLOCKED/NA)
        if not self.required_checks:
            self.status = "UNVERIFIED"
            self.block_reason = "no required checks evaluated"
            return self
        if any(not c.ok and c.id.endswith(":missing") for c in self.required_checks):
            self.status = "UNVERIFIED"
            self.block_reason = "required evidence artifact absent"
            return self
        if all(c.ok for c in self.required_checks):
            self.status = "PASS"
            return self
        failed = [c.id for c in self.required_checks if not c.ok]
        self.status = "FAIL"
        self.block_reason = "failed checks: " + ", ".join(failed)
        return self


def _gate(gate_id: str, name: str, description: str, scope: str,
          repos: list[str], acceptance: str, evidence: dict[str, Any],
          provenance: dict[str, Any], timestamp: str) -> GateResult:
    return GateResult(
        gate_id=gate_id, name=name, description=description, scope=scope,
        repos=repos, shas=provenance.get("shas", {}),
        environment=evidence.get("environment", {}),
        required_checks=[], artifacts=provenance.get("artifacts", []),
        provenance=provenance, timestamp=timestamp, evidence=evidence,
        acceptance_criteria=acceptance)


def _scenario(e2e: dict[str, Any], name: str) -> dict[str, Any] | None:
    s = (e2e.get("scenarios") or {}).get(name)
    return s if isinstance(s, dict) else None


def _scenario_ok(s: dict[str, Any] | None) -> CheckResult:
    """A scenario counts only when it ran to PASS with the Onda-13 evidence
    fields populated — not a bare status string."""
    if s is None:
        return CheckResult("scenario:missing", False, "scenario absent")
    if s.get("status") != "PASS":
        return CheckResult("scenario:status", False,
                           f"status={s.get('status')}")
    missing = sorted(
        f for f in REQUIRED_SCENARIO_FIELDS
        if f not in s or s.get(f) is None or s.get(f) == "")
    # steps and evidence-bearing fields: steps empty = nothing executed
    if "steps" not in s or not s.get("steps"):
        missing.append("steps")
    if missing:
        return CheckResult("scenario:fields", False,
                           "missing fields: " + ", ".join(sorted(set(missing))))
    if not s.get("repo_shas"):
        return CheckResult("scenario:shas", False, "no repository SHAs recorded")
    # a scenario marked PASS whose own steps contain a failed check is
    # inconsistent evidence — the inner failure must surface (Onda 1.3)
    bad = [str(st.get("check") or st.get("cmd") or st.get("step") or "?")
           for st in s.get("steps") or []
           if isinstance(st, dict) and st.get("ok") is False]
    if bad:
        return CheckResult("scenario:steps", False,
                           "failed inner checks: " + ", ".join(bad))
    return CheckResult("scenario:ok", True)


def _steps_ok(s: dict[str, Any] | None, *, require_all: bool = True) -> CheckResult:
    """Every recorded step/check inside a scenario must carry ok=True — a
    single failed inner check fails the dimension (Onda 1.3)."""
    if not isinstance(s, dict):
        return CheckResult("steps:missing", False)
    steps = s.get("steps") or []
    if not steps:
        return CheckResult("steps:empty", False, "no executed steps")
    bad = [st.get("check") or st.get("cmd") or st.get("repo") or "?"
           for st in steps if isinstance(st, dict) and st.get("ok") is False]
    if require_all and bad:
        return CheckResult("steps:failed", False,
                           "failed inner checks: " + ", ".join(map(str, bad)))
    return CheckResult("steps:ok", True)


REQUIRED_LOCK_REPOS = 15


def _lock_ok(lock: dict[str, Any] | None,
             states: dict[str, dict[str, Any]]) -> list[CheckResult]:
    """Evidence freshness + completeness (P1-001): the lock must carry
    exactly the 15 canonical entries, each with sha+version+manifest
    checksums, non-empty adapter/contract version maps, and SHAs equal to
    live HEADs — stale or partial evidence is rejected (Onda 1.4)."""
    if not isinstance(lock, dict) or not lock:
        return [CheckResult("lock:missing", False, "certification-lock.json absent")]
    repos = lock.get("repos")
    if not isinstance(repos, dict) or not repos:
        return [CheckResult("lock:repos", False, "lock has no repo entries")]
    checks: list[CheckResult] = []
    checks.append(CheckResult(
        "lock:exact-15", len(repos) == REQUIRED_LOCK_REPOS,
        f"{len(repos)}/{REQUIRED_LOCK_REPOS} canonical entries"))
    missing = [r for r, e in repos.items()
               if not isinstance(e, dict) or not e.get("exists")]
    checks.append(CheckResult("lock:coverage", not missing,
                              f"missing checkouts: {missing}" if missing else "15/15"))
    incomplete = [r for r, e in repos.items()
                  if isinstance(e, dict) and e.get("exists")
                  and not (e.get("sha") and e.get("version")
                           and e.get("manifest_checksums"))]
    checks.append(CheckResult(
        "lock:fields", not incomplete,
        f"entries missing sha/version/manifest_checksums: {incomplete}"
        if incomplete else "all fields"))
    adapters = lock.get("adapters")
    unversioned = ([a for a, v in adapters.items() if not v]
                   if isinstance(adapters, dict) else ["<absent>"])
    checks.append(CheckResult(
        "lock:adapters", isinstance(adapters, dict)
        and bool(adapters) and not unversioned,
        f"unversioned: {unversioned}" if unversioned else
        f"{len(adapters) if isinstance(adapters, dict) else 0} adapters"))
    contracts = lock.get("contracts")
    checks.append(CheckResult(
        "lock:contracts", isinstance(contracts, dict) and bool(contracts),
        f"{len(contracts)} contract versions" if isinstance(contracts, dict)
        else "absent"))
    drifted = []
    for r, e in repos.items():
        if not isinstance(e, dict) or not e.get("exists"):
            continue
        live = (states.get(r) or {})
        if live.get("head") and e.get("sha") and live["head"] != e["sha"]:
            drifted.append(r)
    checks.append(CheckResult("lock:no-drift", not drifted,
                              f"drifted: {drifted}" if drifted else "clean"))
    return checks


def _e2e_freshness(e2e: dict[str, Any],
                   lock: dict[str, Any] | None) -> list[CheckResult]:
    """Onda 1.4 — the E2E's recorded repo_shas must equal the lock SHAs:
    an E2E executed on older commits can never certify the locked state."""
    if not isinstance(lock, dict) or not lock:
        return [CheckResult("e2e:freshness", False, "no lock to bind against")]
    lshas = {r: (e or {}).get("sha") for r, e in
             (lock.get("repos") or {}).items()
             if isinstance(e, dict) and e.get("exists")}
    seen: dict[str, str] = {}
    for sc in (e2e.get("scenarios") or {}).values():
        if isinstance(sc, dict):
            seen.update({r: s for r, s in (sc.get("repo_shas") or {}).items()
                         if s})
    stale = sorted(r for r, s in seen.items()
                   if lshas.get(r) and not str(lshas[r]).startswith(str(s)))
    missing = sorted(r for r in lshas if r not in seen)
    return [CheckResult("e2e:sha-binding", not stale,
                        f"scenarios ran on stale SHAs: {stale}"
                        if stale else "all bound"),
            CheckResult("e2e:sha-coverage", not missing,
                        f"repos never recorded by E2E: {missing}"
                        if missing else "all recorded")]


def evaluate_gates(evidence: dict[str, Any]) -> list[GateResult]:
    """Evaluate every certification dimension against collected evidence.

    ``evidence`` keys: baseline, e2e, lock, states, ci_runs, probe (bool),
    timestamp, environment, out_dir.
    """
    e2e = evidence.get("e2e") or {}
    baseline = evidence.get("baseline") or {}
    lock = evidence.get("lock")
    states = evidence.get("states") or {}
    ci = evidence.get("ci_runs") or {}
    ts = evidence.get("timestamp", "")
    prov = {"producer": "unified_certify/evaluate_gates",
            "shas": {r: (states.get(r) or {}).get("head") for r in states},
            "artifacts": ["operational-e2e.json", "baseline.json",
                          "certification-lock.json"]}
    gates: list[GateResult] = []

    # ---- contracts -----------------------------------------------------
    g = _gate("contracts", "Contracts & manifests", "Forge manifests valid and "
              "context/catalog scenario executed", "platform", list(states),
              "every provider repo has a manifest; host repos declare a role",
              e2e, prov, ts)
    repos = (baseline.get("repos") or {})
    if not repos:
        g.required_checks.append(CheckResult("baseline:missing", False,
                                             "baseline.json absent/empty"))
    else:
        no_man = [r for r, e in repos.items()
                  if isinstance(e, dict) and e.get("exists")
                  and e.get("role") and not e.get("has_manifest")]
        g.required_checks.append(CheckResult(
            "providers:manifests", not no_man,
            f"providers missing manifest: {no_man}" if no_man else "all"))
        no_role = [r for r, e in repos.items()
                   if isinstance(e, dict) and e.get("exists")
                   and not e.get("role") and not e.get("role_justification")]
        g.required_checks.append(CheckResult(
            "hosts:role-declared", not no_role,
            f"repos with neither manifest nor declared role: {no_role}"
            if no_role else "all"))
    sc = _scenario(e2e, "context")
    g.required_checks.append(_scenario_ok(sc))
    gates.append(g.finish())

    # ---- declared_resources ---------------------------------------------
    # Onda 4: counts come from resource-inventory.json (direct dir scan of
    # all 15 repos — host repos included), not only manifest resources.
    g = _gate("declared_resources", "Declared resources", "Resource catalogs "
              "inventoried from a direct per-repo scan", "platform",
              list(states),
              "every existing repo has a real resource inventory", 
              evidence.get("inventory") or baseline, prov, ts)
    inv = (evidence.get("inventory") or {}).get("repos") or {}
    if not inv:
        g.required_checks.append(CheckResult(
            "inventory:missing", False, "resource-inventory.json absent/empty"))
    else:
        no_res = [r for r, e in inv.items()
                  if isinstance(e, dict) and e.get("exists")
                  and not e.get("resource_total")]
        g.required_checks.append(CheckResult(
            "resources:inventoried", not no_res,
            f"repos with zero inventoried resources: {no_res}"
            if no_res else "all"))
        expected = {r for r, s in states.items()
                    if isinstance(s, dict) and s.get("exists")}
        inventoried = {r for r, e in inv.items()
                       if isinstance(e, dict) and e.get("exists")}
        gap = sorted(expected - inventoried)
        g.required_checks.append(CheckResult(
            "resources:coverage", not gap,
            f"checkouts not inventoried: {gap}" if gap else "all"))
        # P1-005 — functional integrity: every advertised unit resolved,
        # readable, non-empty, inside repo bounds; duplicates surfaced.
        broken, escaped = [], []
        for r, e in inv.items():
            if not isinstance(e, dict) or not e.get("exists"):
                continue
            for kind, ke in (e.get("resources") or {}).items():
                f = (ke or {}).get("functional")
                if f is None:
                    broken.append(f"{r}:{kind} (no functional pass)")
                    continue
                broken += [f"{r}:{kind} {b}"
                           for b in (f.get("broken") or [])]
                escaped += [f"{r}:{kind} {b}"
                            for b in (f.get("escaped") or [])]
        g.required_checks.append(CheckResult(
            "resources:functional", not broken,
            f"broken/unverified units: {broken[:10]}"
            if broken else "all units resolved+readable"))
        g.required_checks.append(CheckResult(
            "resources:containment", not escaped,
            f"path escapes: {escaped[:10]}"
            if escaped else "no symlink escapes"))
    gates.append(g.finish())

    # ---- install_lifecycle ----------------------------------------------
    g = _gate("install_lifecycle", "Install lifecycle", "Real apply/status/"
              "update/uninstall on a scratch workspace", "the-forge",
              ["the-forge"], "lifecycle scenario PASS with inner steps ok",
              e2e, prov, ts)
    sc = _scenario(e2e, "lifecycle")
    g.required_checks.append(_scenario_ok(sc))
    if sc and sc.get("status") == "PASS":
        verdicts = {st.get("step"): st for st in sc.get("steps") or []}
        g.required_checks.append(CheckResult(
            "lifecycle:apply",
            bool(verdicts.get("I-install-apply")),
            "governed install apply executed"))
        g.required_checks.append(CheckResult(
            "lifecycle:uninstall",
            bool((verdicts.get("J-install-uninstall") or {}).get("user_file_preserved")),
            "uninstall preserved user data"))
    gates.append(g.finish())

    # ---- federated_operations -------------------------------------------
    g = _gate("federated_operations", "Federated operations",
              "Routing, delegation, multidomain execution, honest ambiguity "
              "and partial states", "platform", list(states),
              "5 federation sub-scenarios PASS incl. >=2 executed providers",
              e2e, prov, ts)
    for name in FED_SCENARIOS:
        g.required_checks.append(_scenario_ok(_scenario(e2e, name)))
    # Onda 8 — MCP handshake/tools + bridge session lifecycle are part of
    # the federated-operations contract, not optional extras.
    for name in INTEGRATION_SCENARIOS:
        g.required_checks.append(_scenario_ok(_scenario(e2e, name)))
    multi = _scenario(e2e, "federation-multidomain")
    if isinstance(multi, dict) and multi.get("status") == "PASS":
        ev = multi.get("evidence") or {}
        g.required_checks.append(CheckResult(
            "federation:correlation", bool(ev.get("correlation_id")),
            "correlation id recorded"))
        exec_steps = [s for s in multi.get("steps") or []
                      if str(s.get("check", "")).startswith("execute:")]
        g.required_checks.append(CheckResult(
            "federation:multi-exec",
            sum(1 for s in exec_steps if s.get("ok")) >= 2,
            "two or more providers executed"))
        # Lens correlation is now a real verified path (telemetry export ->
        # lens ingest -> session trace), no longer an accepted named gap.
        lens_steps = {
            s.get("check"): s for s in multi.get("steps") or []
            if isinstance(s, dict)
        }
        g.required_checks.append(CheckResult(
            "federation:lens-correlation",
            bool((lens_steps.get("lens-traces-session") or {}).get("ok"))
            and bool((lens_steps.get("lens-trace-shape") or {}).get("ok")),
            "correlated trace visible in forge-lens"))
    gates.append(g.finish())

    # ---- security_boundaries --------------------------------------------
    g = _gate("security_boundaries", "Security boundaries",
              "Real protocol/contract/tool refusals", "platform",
              list(states), "security scenario PASS with all refusals verified",
              e2e, prov, ts)
    sc = _scenario(e2e, "security")
    g.required_checks.append(_scenario_ok(sc))
    if sc and sc.get("status") == "PASS":
        refused = [s for s in sc.get("steps") or []
                   if isinstance(s, dict) and s.get("refused")]
        g.required_checks.append(CheckResult(
            "security:refusals", len(refused) >= 3,
            f"{len(refused)} named refusals executed"))
    gates.append(g.finish())

    # ---- portal_real_services --------------------------------------------
    g = _gate("portal_real_services", "Portal real services",
              "Portal service calls return live workspace data",
              "forge-portal", ["forge-portal", "the-forge"],
              "portal scenario PASS with resources > 0", e2e, prov, ts)
    sc = _scenario(e2e, "portal")
    g.required_checks.append(_scenario_ok(sc))
    if sc and sc.get("status") == "PASS":
        n = next((s.get("count") for s in sc.get("steps") or []
                  if s.get("call") == "workspace_resources"), 0)
        g.required_checks.append(CheckResult(
            "portal:live-resources", isinstance(n, int) and n > 0,
            f"{n} live resources"))
    gates.append(g.finish())

    # ---- specialists_standalone ------------------------------------------
    g = _gate("specialists_standalone", "Specialists standalone",
              "Every specialist runs real domain work on fixtures",
              "specialists", list(states),
              "standalone + all 9 domain scenarios PASS", e2e, prov, ts)
    g.required_checks.append(_scenario_ok(_scenario(e2e, "standalone")))
    for name in DOMAIN_SCENARIOS:
        g.required_checks.append(_scenario_ok(_scenario(e2e, name)))
    gates.append(g.finish())

    # ---- ci_federated ------------------------------------------------------
    g = _gate("ci_federated", "CI federated",
              "Federated workflows ran green on pinned refs",
              "ci", list(states),
              "ecosystem-real + provider-surface-drift + release-compat "
              "last runs = success", ci, prov, ts)
    for wf in ("ecosystem-real", "provider-surface-drift", "release-compat"):
        info = ci.get(wf)
        if not isinstance(info, dict):
            g.required_checks.append(CheckResult(f"ci:{wf}", False,
                                                 "no run evidence collected"))
            continue
        g.required_checks.append(CheckResult(
            f"ci:{wf}", info.get("conclusion") == "success",
            f"last run conclusion={info.get('conclusion')}, "
            f"ref={info.get('ref')}"))
        # P1-002 — CI bound to the locked commit, not just last-green:
        # the run's headSha must equal the lock's the-forge sha.
        lock_sha = (((lock or {}).get("repos") or {})
                    .get("the-forge") or {}).get("sha")
        g.required_checks.append(CheckResult(
            f"ci:{wf}:sha-binding",
            bool(lock_sha) and info.get("sha") == lock_sha,
            f"run sha={str(info.get('sha'))[:12]} vs lock "
            f"{str(lock_sha)[:12]}"))
        jobs = info.get("jobs") or {}
        failed_jobs = [j for j, st in jobs.items()
                       if st in ("failure", "cancelled", "timed_out")]
        g.required_checks.append(CheckResult(
            f"ci:{wf}:jobs", bool(jobs) and not failed_jobs,
            f"failed/cancelled jobs: {failed_jobs}" if failed_jobs
            else f"{len(jobs)} jobs executed"))
    gates.append(g.finish())

    # ---- final_versions_traceable ------------------------------------------
    g = _gate("final_versions_traceable", "Versions & SHAs traceable",
              "Locked SHAs/versions equal live state; tags/releases exist",
              "platform", list(states),
              "certification-lock clean + every repo version+tag+release",
              {"lock": lock, "states": states}, prov, ts)
    g.required_checks.extend(_lock_ok(lock, states))
    g.required_checks.extend(_e2e_freshness(e2e, lock))
    untraceable = [r for r, s in states.items()
                   if s.get("exists") and not (s.get("version") and s.get("tags"))]
    g.required_checks.append(CheckResult(
        "versions:complete", not untraceable,
        f"repos lacking version/tag: {untraceable}" if untraceable else "all"))
    # Onda 1.4 — version trinity: baseline == lock == live state per repo.
    diverged = []
    for r, s in states.items():
        if not s.get("exists"):
            continue
        bv = ((baseline.get("repos") or {}).get(r) or {}).get("version")
        lv = (((lock or {}).get("repos") or {}).get(r) or {}).get("version")
        sv = s.get("version")
        if sv and ((bv and bv != sv) or (lv and lv != sv)):
            diverged.append(f"{r}(state={sv},baseline={bv},lock={lv})")
    g.required_checks.append(CheckResult(
        "versions:trinity", not diverged,
        f"version divergence: {diverged}" if diverged else "all equal"))
    gates.append(g.finish())

    # ---- pypi_npm_publication -----------------------------------------------
    g = _gate("pypi_npm_publication", "PyPI/npm publication",
              "Published distributions live-verified on indexes",
              "release", list(states),
              "every repo with an index entry probes PUBLISHED", states,
              prov, ts)
    blocked, unv = [], []
    probed = 0
    for r, s in states.items():
        for idx, st in (s.get("index") or {}).items():
            probed += 1
            if st == "NOT_PUBLISHED":
                blocked.append(f"{r}:{idx}")
            elif st == "UNVERIFIED":
                unv.append(f"{r}:{idx}")
    # zero index entries evaluated = vacuous gate — never a PASS
    g.required_checks.append(CheckResult(
        "index:coverage", probed > 0, f"{probed} index entries evaluated"))
    g.required_checks.append(CheckResult(
        "index:published", not blocked,
        f"not published: {blocked}" if blocked else "all probed published"))
    if unv:
        g.required_checks.append(CheckResult(
            "index:probed", False,
            f"unverified (no probe): {unv}"))
    else:
        g.required_checks.append(CheckResult("index:probed", True))
    # Onda 10 / P1-007 — index presence is not installability: the
    # release-verify artifact must prove real clean installs (entrypoint
    # executed, artifact sha256 == index digest) for the flagship dists.
    rv = evidence.get("release_verify") or {}
    rchecks = rv.get("checks")
    if not isinstance(rchecks, list) or not rchecks:
        g.required_checks.append(CheckResult(
            "release:clean-install", False,
            "release-verify.json absent — clean install never proven"))
    else:
        failed = [c.get("package") for c in rchecks
                  if c.get("status") != "VERIFIED"]
        no_sha = [c.get("package") for c in rchecks
                  if c.get("source") == "pypi"
                  and not ((c.get("artifact") or {}).get("sha256_match"))]
        g.required_checks.append(CheckResult(
            "release:clean-install", not failed,
            f"not clean-install verified: {failed}"
            if failed else f"{len(rchecks)} dists verified"))
        g.required_checks.append(CheckResult(
            "release:checksums", not no_sha,
            f"checksum unverified: {no_sha}"
            if no_sha else "artifact sha256 == index digest"))
    gates.append(g.finish())

    return gates


def verdict(gates: list[GateResult]) -> str:
    """Onda 14.2 decision rules — FAIL => NOT READY; BLOCKED/UNVERIFIED =>
    CONDITIONAL GO; all PASS => PRODUCTION READY."""
    statuses = {g.status for g in gates}
    if "FAIL" in statuses:
        return "NOT READY"
    if statuses == {"PASS"}:
        return "PRODUCTION READY"
    return "CONDITIONAL GO"


def gates_report(gates: list[GateResult]) -> dict[str, Any]:
    return {
        "kind": "forge/certification-gates/1",
        "verdict": verdict(gates),
        "dimensions": {g.gate_id: g.status for g in gates},
        "gates": [asdict(g) for g in gates],
    }
