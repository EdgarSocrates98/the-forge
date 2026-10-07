"""Human-readable renderers. Pure functions: dict in, text out."""

import re
from typing import Any

from theforge.explain.report import ROUTING_NOTE_PREFIXES

_UNSAFE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")


def _clean(value: object) -> str:
    """Stringify and neutralize control characters (terminal-escape injection)."""
    return _UNSAFE.sub("?", str(value))


clean = _clean

_TRACEBACK = "Traceback (most recent call last):"


def collapse_traceback(text: str) -> str:
    """``text`` with any raw traceback (e.g. a provider's stderr tail) collapsed to its final
    exception line: a raw traceback is never displayed, in text or JSON (13.4)."""
    if _TRACEBACK not in text:
        return text
    head, _, tail = text.partition(_TRACEBACK)
    lines = [line.strip() for line in tail.splitlines() if line.strip()]
    return f"{head}[traceback omitted] {lines[-1] if lines else ''}".rstrip()


def _detail(value: object) -> str:
    """An error detail, traceback collapsed and control characters neutralized (13.4)."""
    return _clean(collapse_traceback(str(value)))


def code_suffix(code: object, family: object) -> str:
    """The governed `[<code> · <family>]` suffix of an error (13.4)."""
    return f"[{_clean(code)} · {_clean(family)}]"


def diagnostic(data: dict[str, Any]) -> list[str]:
    """Lines of a redacted ``Diagnostic`` (already redacted by ``build_diagnostic``)."""
    lines = [f"stage={_clean(data['stage'])} code={_clean(data['code'])} "
             f"family={_clean(data['family'] or 'provider code')}",
             f"error: {_clean(data['error_type'])}: {_clean(data['message'])}"]
    lines.extend(f"cause: {_clean(c['type'])}: {_clean(c['message'])}"
                 for c in data.get("causes", []))
    lines.extend(f"frame: {_clean(f['module'])}:{_clean(f['function'])}:{_clean(f['line'])}"
                 for f in data.get("frames", []))
    return lines


def _short_hashes(value: object) -> str:
    """A hash (or a list of hashes, e.g. negotiation rounds) shortened to 12 chars each."""
    if isinstance(value, list):
        return ",".join(_clean(item or "-")[:12] for item in value)
    return _clean(value or "-")[:12]


def init(data: dict[str, Any]) -> str:
    forge_dir = _clean(data["forge_dir"])
    if not data["created"]:
        return f"{forge_dir} already initialized"
    return "\n".join([f"Initialized {forge_dir}",
                      *(f"  created {_clean(path)}" for path in data["created"])])


def doctor(data: dict[str, Any]) -> str:
    lines = [f"The Forge {_clean(data['forge_version'])} - {_clean(data['root'])}"]
    for check in data["checks"]:
        lines.append(f"{_clean(check['name']):.<32} {_clean(check['status']):<5} "
                     f"{_clean(check['detail'])}")
    lines.append("healthy" if data["healthy"] else "UNHEALTHY")
    return "\n".join(lines)


def status(data: dict[str, Any]) -> str:
    root = _clean(data["root"])
    if not data["initialized"]:
        return f"{root}: not initialized (run `theforge init`)"
    cached = ", ".join(_clean(p) for p in data["cached_providers"]) or "none cached"
    return "\n".join([
        f"Workspace:  {root}",
        f"Providers:  {cached}",
        f"Runs:       {data['runs']} (last: {_clean(data['last_run'] or '-')})",
    ])


def providers(data: dict[str, Any]) -> str:
    lines = []
    for p in data["providers"]:
        line = (f"{_clean(p['id']):<20} {_clean(p['state']):<13} "
                f"trust={_clean(p['trust']):<10} "
                f"source={_clean(p['source']):<8} version={_clean(p['version'] or '-')}")
        if p["error"]:
            line += f"  error: {_clean(p['error'])}"
        lines.append(line)
    return "\n".join(lines) or "no providers"


def provider_detail(data: dict[str, Any]) -> str:
    lines = [providers({"providers": [data]}),
             f"argv:      {_clean(' '.join(data['argv']))}",
             f"protocol:  {_clean(data['protocol'] or '-')}",
             f"manifest:  {_clean(data['manifest_sha256'] or '-')}"]
    for cap in (data["manifest"] or {}).get("capabilities", []):
        lines.append(f"  {_clean(cap['id']):<28} "
                     f"actions={_clean(','.join(cap['actions']))} "
                     f"state={_clean(cap['state'])} class={_clean(cap['operation_class'])}")
    return "\n".join(lines)


def registry_sources(data: dict[str, Any]) -> str:
    lines = [f"local (authoritative): {data['local_entries']} installed providers"]
    for s in data["sources"]:
        line = f"{_clean(s['id']):<20} {_clean(s['kind']):<11} {_clean(s['status']):<12}"
        if s["entries"] is not None:
            line += f" entries={s['entries']} registry={_clean(s['registry'] or '-')}"
        if s.get("from_cache"):
            line += " (cache)"
        if s.get("retrieved_at"):
            line += f" retrieved={_clean(s['retrieved_at'])}"
        if s["detail"]:
            line += f"  {_clean(s['detail'])}"
        lines.append(line)
    return "\n".join(lines)


def capabilities(data: dict[str, Any]) -> str:
    rows = data["capabilities"]
    if not rows:
        return "no capabilities found"
    lines = []
    for c in rows:
        line = f"{_clean(c['id']):<28} {_clean(c['provider']):<20} " \
               f"actions={_clean(','.join(c['actions']))} state={_clean(c['state'])}"
        if c.get("aliases"):
            line += f" aliases={_clean(','.join(c['aliases']))}"
        if c.get("deprecated"):
            line += (f" deprecated (replaced_by {_clean(c['replaced_by'])})"
                     if c.get("replaced_by") else " deprecated (no replacement)")
        if len(c.get("declared_by", [])) > 1:
            line += f" declared_by={_clean(','.join(c['declared_by']))}"
        if c["description"]:
            line += f"  - {_clean(c['description'])}"
        lines.append(line)
    return "\n".join(lines)


def negotiation(data: dict[str, Any]) -> str:
    results = data["results"]
    if not results:
        return "no providers to negotiate with"
    req = data["requirement"]
    lines = [f"requirement: {_clean(req['capability'])}"
             + (f" actions={_clean(','.join(req['required_actions']))}"
                if req.get('required_actions') else "")
             + (f" tech={_clean(','.join(req['technologies']))}"
                if req.get('technologies') else "")]
    for r in results:
        dims = " ".join(f"{k.split('_')[0]}={v}" for k, v in sorted(r["dimensions"].items())
                        if v not in ("not_applicable",))
        lines.append(f"{r['state']:<12} {_clean(r['provider']):<22} "
                     f"{_clean(r.get('capability') or '-'):<28} {dims}")
        if r.get("history") not in (None, "absent"):
            lines.append(f"             history={r['history']}")
        for item in r.get("missing", []) + r.get("policy_conflicts", []):
            lines.append(f"             - {_clean(item)}")
        for note in r.get("limitations", []):
            lines.append(f"             ~ {_clean(note)}")
    return "\n".join(lines)


# Relation edge kinds in display order; the mechanical structure edges
# (has_capability, has_action, in_domain) are listed last — they derive from
# the manifest boilerplate, not from declared intent.
_GRAPH_EDGE_ORDER = ("produces", "consumes", "requires", "complements",
                     "conflicts", "can_verify", "can_review", "relevant_to",
                     "uses_technology", "in_domain", "has_capability",
                     "has_action")


def _ref_match(node_id: str, ref: str) -> bool:
    """``p/c`` matches exactly; bare ``c`` matches ``capability:*/c``."""
    if not node_id.startswith("capability:"):
        return False
    key = node_id.removeprefix("capability:")
    return key == ref or ("/" not in ref and key.endswith(f"/{ref}"))


def graph(data: dict[str, Any]) -> str:
    """The capability graph (``theforge graph``): every edge of the persisted
    CapabilityGraph, grouped by kind, with the epistemic tag of each edge.
    ``--mesh`` instead prints the domain mesh projection (observe/engineer/
    verify) derived from declared relations."""
    mesh = data.get("mesh")
    if mesh is not None:
        lines = ["Capability mesh (declared relations):"]
        if not mesh.get("domains"):
            lines.append("  (no artifact type is both produced and consumed)")
        for row in mesh.get("domains") or []:
            lines.append(f"DOMAIN: {_clean(row.get('domain', '?'))}")
            for role in ("observe", "engineer", "verify"):
                members = row.get(role) or []
                lines.append(f"  {role}:")
                lines += [f"    {_clean(member)}" for member in members] or \
                         ["    (none declared)"]
        if mesh.get("unplaced_verify"):
            lines += _labelled("Unplaced verify:",
                               [_clean(item) for item in mesh["unplaced_verify"]])
        return "\n".join(lines)
    nodes = [n for n in data.get("nodes") or [] if isinstance(n, dict)]
    edges = [e for e in data.get("edges") or [] if isinstance(e, dict)]
    ref = data.get("ref")
    if ref:
        edges = [e for e in edges
                 if _ref_match(str(e.get("source", "")), ref)
                 or _ref_match(str(e.get("target", "")), ref)]
        keep = {e.get("source") for e in edges} | {e.get("target") for e in edges}
        nodes = [n for n in nodes
                 if _ref_match(str(n.get("id", "")), ref) or n.get("id") in keep]
    counts: dict[str, int] = {}
    for node in nodes:
        kind = _clean(node.get("kind", "?"))
        counts[kind] = counts.get(kind, 0) + 1
    summary = "  ".join(f"{v} {k}" for k, v in sorted(counts.items()))
    head = (f"Capability graph: {summary or 'empty'}  ({len(edges)} edges"
            f"{', ref ' + _clean(ref) if ref else ''})")
    lines = [head]
    by_kind: dict[str, list[dict[str, Any]]] = {}
    for edge in edges:
        by_kind.setdefault(str(edge.get("kind", "?")), []).append(edge)
    ordered = [k for k in _GRAPH_EDGE_ORDER if k in by_kind]
    ordered += sorted(k for k in by_kind if k not in _GRAPH_EDGE_ORDER)
    for kind in ordered:
        lines.append(f"{kind}:")
        for edge in by_kind[kind]:
            lines.append(
                f"  {_clean(edge.get('source', '?'))} -> {_clean(edge.get('target', '?'))} "
                f"({_clean(edge.get('epistemic', '?'))}: "
                f"{_clean(edge.get('evidence', '?'))})")
    lines += _labelled("Limitations:", _list(data.get("limitations")))
    return "\n".join(lines)


def health(data: dict[str, Any]) -> str:
    lines = []
    for p in data["providers"]:
        line = f"{_clean(p['id']):<20} {_clean(p['status'])}"
        if p.get("surface_fingerprint"):
            line += f"  surface:{_clean(p['surface_fingerprint'])[:12]}"
        if p["error"]:
            line += f"  {_clean(p['error']['code'])}: {_detail(p['error']['detail'])}"
        lines.append(line)
    return "\n".join(lines) or "no providers"


def provider_init(data: dict[str, Any]) -> str:
    lines = [f"Scaffolded {_clean(data['provider_id'])} in {_clean(data['directory'])}"]
    for path in data["files"]:
        name = str(path).replace("\\", "/").rsplit("/", 1)[-1]
        lines.append(f"  wrote {_clean(name)}")
    lines.append(f"Capability: {_clean(data['capability'])}")
    lines.append(f"argv:       {_clean(' '.join(data['argv']))}")
    lines.append("Register it in a providers.toml, then `theforge registry refresh` "
                 "(nothing was installed).")
    return "\n".join(lines)


def provider_check(data: dict[str, Any]) -> str:
    lines = []
    for c in data["checks"]:
        line = f"{_clean(c['id']):<22} {c['status']}"
        if c["detail"]:
            line += f"  {_detail(c['detail'])}"
        lines.append(line)
    lines.append("conformance: " + ("ok" if data["ok"] else "FAILED"))
    return "\n".join(lines)


def ask(data: dict[str, Any]) -> str:
    decision = data["decision"]
    run_id = _clean(data["run_id"])
    lines = [f"Run {run_id}: {_clean(data['status'])}"]
    if decision["selected"]:
        sel = decision["selected"][0]
        lines.append(f"Selected:   {_clean(sel['provider'])} "
                     f"{_clean(sel['capability'])}:{_clean(sel['action'])} "
                     f"(confidence {_clean(decision['confidence']['level'])})")
    lines.append(f"Reason:     {_clean(decision['reason'])}")
    negotiation = decision.get("negotiation") or []
    if negotiation:
        lines.append("Fit:")
        for res in negotiation:
            gaps = [*_list(res.get("missing")), *_list(res.get("policy_conflicts"))]
            lines.append(f"  {_clean(res['provider'])}: {_clean(res['state'])}"
                         + (f" ({_clean(', '.join(gaps))})" if gaps else ""))
    if data["status"] in ("ambiguous", "no_route"):
        for cand in decision["candidates"]:
            lines.append(f"  candidate {_clean(cand['provider'])}/{_clean(cand['capability'])} "
                         f"rank={_clean(cand['rank_key'])}")
        lines.append("Hint:       pass --capability <id> (see `theforge capabilities list`)")
    result = data["result"]
    if result:
        lines.append(f"Findings:   {len(result['findings'])}   "
                     f"Evidence: {len(result['evidence'])}")
        lines.extend(f"  [{_clean(f['severity'])}] {_clean(f['title'])}"
                     for f in result["findings"])
    error = data["error"]
    if error:
        family = data.get("error_family")
        suffix = f" {code_suffix(error['code'], family)}" if family else ""
        lines.append(f"Error:      {_clean(error['code'])}: {_detail(error['detail'])}{suffix}")
        if error.get("unlock"):
            lines.append(f"Unlock:     {_clean(error['unlock'])}")
    lines.append(f"Explain:    theforge explain {run_id}")
    return "\n".join(lines)


def _signals(matched: dict[str, list[str]]) -> str:
    parts = [f"{key}[{','.join(_clean(h) for h in hits)}]"
             for key in ("dependencies", "file_globs", "keywords")
             if (hits := matched.get(key))]
    return " ".join(parts) or "requested"


_DIMENSIONS = ("read_only", "local_mutation", "external_read", "external_mutation",
               "destructive", "credentials", "cross_account")


def _risk(risk: dict[str, Any] | None) -> list[str]:
    if not risk:
        return ["Risk:        not recorded"]
    policy = risk.get("policy") or {}
    dims = risk.get("dimensions") or {}
    approved = "yes" if policy.get("approved") else "no"
    lines = [f"Risk:        {_clean(risk.get('operation_class', '?'))} "
             f"(source: {_clean(risk.get('source', '?'))})",
             f"Policy:      {_clean(policy.get('decision', '?'))}   "
             f"rule: {_clean(policy.get('rule', '?'))}   approved: {approved}",
             "Dimensions:  " + " ".join(f"{name}={_clean(dims.get(name, '?'))}"
                                        for name in _DIMENSIONS)]
    if policy.get("unlock"):
        lines[1] += f"   unlock: {_clean(policy['unlock'])}"
    return lines


# Text output contract of ``explain`` for context and telemetry (context-intelligence-v2
# 4.5). cross-forge-foundation rewrites ``explain`` over ExplainReport and MUST keep these
# headings (in this order) and the tests in test_cli.py that check them, reading the
# sections from ``artifacts.context``, ``artifacts.context-r*`` and ``artifacts.telemetry``.
EXPLAIN_CONTEXT_SECTIONS = ("Context:", "Tiers:", "Items:", "Excluded:", "Unmatched:", "Git:",
                            "Rounds:", "Drift:", "Telemetry:")
_ROUNDS = ("context-r1", "context-r2")
_DRIFT_PREFIX = "context-drift:"


def _labelled(label: str, rows: list[str]) -> list[str]:
    """One row per line: the label on the first, the others aligned under it."""
    return [f"{label if i == 0 else '':<13}{row}" for i, row in enumerate(rows or ["none"])]


def _item(item: dict[str, Any]) -> str:
    lines = item.get("lines") or {}
    span = f":{_clean(lines.get('start', '?'))}-{_clean(lines.get('end', '?'))}" if lines else ""
    signals = (", ".join(_clean(s) for s in item.get("signals") or [])
               or _clean(item.get("reason") or "-"))
    return (f"{_clean(item.get('tier') or 'reference')} {_clean(item.get('path', '?'))}{span}"
            f"  signals: {signals}")


def _excluded(entry: dict[str, Any]) -> str:
    return f"{_clean(entry.get('path', '?'))} ({_clean(entry.get('reason', '?'))})"


def _pack_summary(pack: dict[str, Any]) -> str:
    return (f"{len(pack.get('files') or [])} files, {_clean(pack.get('used_bytes', '?'))}/"
            f"{_clean(pack.get('budget_bytes', '?'))} bytes ({_clean(pack.get('status', '?'))});"
            f" excluded {len(pack.get('excluded') or [])}")


def _git(pack: dict[str, Any]) -> str:
    """``branch@head dirty changed=N`` or why git could not be read (its limitation)."""
    limits = [_clean(x) for x in pack.get("limitations") or []
              if isinstance(x, str) and x.startswith("git:")]
    note = f" ({'; '.join(limits)})" if limits else ""
    git = (pack.get("workspace") or {}).get("git")
    if not git:
        return f"not read{note}" if limits else "not recorded"
    if not git.get("available"):
        return f"unavailable{note}"
    where = _clean(git.get("branch") or ("detached" if git.get("detached") else "?"))
    dirty = {True: "dirty", False: "clean"}.get(git.get("dirty"), "dirty=unknown")
    changed = git.get("changed_files")
    states = "".join(f" {_clean(s)}" for s in git.get("state") or [])
    return (f"{where}@{_clean(git.get('head') or 'none')[:12]} {dirty} "
            f"changed={_clean(changed) if changed is not None else 'unknown'}{states}{note}")


def _rounds(data: dict[str, Any], initial: dict[str, Any]) -> list[str]:
    """Negotiation rounds: summary, requested items and the new exclusions of each round."""
    rows: list[str] = []
    seen = {e.get("path") for e in initial.get("excluded") or []}
    for name in _ROUNDS:
        pack = data.get(name)
        if not pack:
            continue
        rows.append(f"{name.removeprefix('context-')}: {_pack_summary(pack)}")
        rows.extend(f"    {_item(f)}" for f in pack.get("files") or []
                    if f.get("tier") == "requested")
        for entry in pack.get("excluded") or []:
            if entry.get("path") not in seen:
                seen.add(entry.get("path"))
                rows.append(f"    excluded {_excluded(entry)}")
    return rows


def _context_sections(data: dict[str, Any], context: dict[str, Any]) -> list[str]:
    telemetry = data.get("telemetry") or {}
    tier_bytes = context.get("tier_bytes") or {}
    effective = list((telemetry.get("profile") or {}).get("effective_tiers") or tier_bytes)
    if effective:
        sizes = " ".join(f"{_clean(k)}={_clean(v)}" for k, v in tier_bytes.items()) or "unknown"
        tiers = f"effective: {', '.join(_clean(t) for t in effective)}   bytes: {sizes}"
    else:
        tiers = "not recorded"
    unmatched = (context.get("workspace") or {}).get("unmatched_files")
    return [f"Context:     {_pack_summary(context)}", f"Tiers:       {tiers}",
            *_labelled("Items:", [_item(f) for f in context.get("files") or []]),
            *_labelled("Excluded:", [_excluded(e) for e in context.get("excluded") or []]),
            "Unmatched:   unmatched (no_signal): "
            f"{_clean(unmatched) if unmatched is not None else 'unknown'}",
            f"Git:         {_git(context)}",
            *_labelled("Rounds:", _rounds(data, context))]


def _drift(data: dict[str, Any]) -> str:
    telemetry = data.get("telemetry")
    if telemetry:
        paths = list(telemetry.get("context_drift") or [])
    else:  # run without telemetry: the receipt limitations carry the drifted paths
        paths = [x.removeprefix(_DRIFT_PREFIX).strip()
                 for x in (data.get("receipt") or {}).get("limitations") or []
                 if isinstance(x, str) and x.startswith(_DRIFT_PREFIX)]
    return ", ".join(_clean(p) for p in paths) or "none"


def _metric(telemetry: dict[str, Any], name: str, unit: str = "") -> str:
    """A telemetry Metric: ``unknown`` unless measured/estimated with a numeric value."""
    metric = telemetry.get(name) or {}
    value = metric.get("value")
    kind = metric.get("kind", "unknown")
    if kind == "unknown" or isinstance(value, bool) or not isinstance(value, int | float):
        return "unknown"
    return f"{'~' if kind == 'estimated' else ''}{round(value)}{unit}"


def _num(value: object) -> str:
    """A plain float field (complexity score/confidence), two decimals."""
    return (f"{value:.2f}" if isinstance(value, (int, float))
            and not isinstance(value, bool) else "?")


def _telemetry(telemetry: dict[str, Any] | None) -> str:
    if not telemetry:
        return "Telemetry:   not recorded"
    m = telemetry
    return ("Telemetry:   "
            f"profile={_clean((m.get('profile') or {}).get('name', '?'))} "
            f"scan={_metric(m, 'scan_ms', 'ms')} routing={_metric(m, 'routing_ms', 'ms')} "
            f"context={_metric(m, 'context_ms', 'ms')} "
            f"provider={_metric(m, 'provider_ms', 'ms')} "
            f"files={_metric(m, 'files_selected')}/{_metric(m, 'files_scanned')} "
            f"cache={_metric(m, 'cache_hits')}/{_metric(m, 'cache_misses')} "
            f"context_bytes={_metric(m, 'context_bytes')} "
            f"providers={_metric(m, 'providers_executed')} "
            f"fallbacks={_metric(m, 'fallbacks_used')} "
            f"rounds={_metric(m, 'negotiation_rounds')} "
            f"verification={_clean(m.get('verification_performed') or 'none')}")


def explain(data: dict[str, Any]) -> str:
    task = data.get("task") or {}
    routing = data.get("routing") or {}
    context = data.get("context")
    result = data.get("result")
    receipt = data.get("receipt") or {}
    lines = [f"Run:         {_clean(data.get('run_id', '?'))}  "
             f"status: {_clean(receipt.get('status', 'incomplete'))}"]
    if task:
        targets = ", ".join(_clean(t) for t in task.get("targets") or [])
        profile = _clean(task.get('budget_profile', '?'))
        complexity = data.get("complexity") or {}
        if task.get("budget_profile") == "auto" and complexity.get("selected_profile"):
            profile = f"auto->{_clean(complexity.get('selected_profile'))}"
        lines.append(f"Task:        \"{_clean(task.get('intent', '?'))}\" "
                     f"(targets: {targets}; profile: {profile})")
        if complexity:
            requested = _clean(complexity.get("requested_profile", "auto"))
            selected = _clean(complexity.get("selected_profile", "?"))
            lines.append(
                f"Complexity:  {_clean(complexity.get('level', '?'))} "
                f"score={_num(complexity.get('score'))} "
                f"confidence={_num(complexity.get('confidence'))}   "
                f"{requested}->{selected}: "
                f"{_clean(complexity.get('profile_reason') or '-')}")
    budget = data.get("budget")
    if budget:
        head = (f"Budget:      {_clean(budget.get('profile', '?'))}  "
                f"context {_clean(budget.get('context_bytes', '?'))}B/"
                f"{_clean(budget.get('max_files', '?'))} files  "
                f"providers≤{_clean(budget.get('provider_calls', '?'))}  "
                f"{_clean(budget.get('wall_time_s', '?'))}s")
        adjustments = budget.get("adjustments") or []
        lines.append(head if not adjustments
                     else f"{head}  (+{_clean(adjustments[0])})")
    if routing:
        candidates = routing.get("candidates") or []
        if not candidates:
            lines.append("Candidates:  none")
        for index, cand in enumerate(candidates):
            label = "Candidates:" if index == 0 else ""
            lines.append(f"{label:<13}{_clean(cand.get('provider', '?'))}/"
                         f"{_clean(cand.get('capability', '?'))}  "
                         f"{_signals(cand.get('matched') or {})}  "
                         f"rank={_clean(cand.get('rank_key', '?'))}  "
                         f"state={_clean(cand.get('state', 'supported'))}")
        selected = ", ".join(
            f"{_clean(s.get('provider', '?'))} {_clean(s.get('capability', '?'))}:"
            f"{_clean(s.get('action', '?'))} ({_clean(s.get('role', '?'))})"
            for s in routing.get("selected") or []) or "none"
        lines.append(f"Selected:    {selected}   pattern: {_clean(routing.get('pattern', '?'))}")
        lines.append(f"Reason:      {_clean(routing.get('reason', '?'))}")
        conf = routing.get("confidence") or {}
        lines.append(f"Confidence:  {_clean(conf.get('level', '?'))}   "
                     f"measured: {_clean(conf.get('measured_signals', '?'))}"
                     f"   unresolved: {_clean(conf.get('unresolved', '?'))}")
        fallbacks = ", ".join(_clean(f) for f in routing.get("fallbacks_used") or []) or "none"
        lines.append(f"Fallbacks:   {fallbacks}")
        # Wave B routing notes (alias, deprecation, overlap), verbatim; only when present.
        notes = [_clean(note) for note in routing.get("limitations") or []
                 if isinstance(note, str) and note.startswith(ROUTING_NOTE_PREFIXES)]
        if notes:
            lines.extend(_labelled("Notes:", notes))
        # Wave K: an ambiguous decision resolved by a semantic resolver — the
        # proposal is the evidence of the pick (ADR 0025).
        proposal = data.get("routing-proposal") or {}
        if proposal:
            choice = proposal.get("choice") or {}
            lines.append(
                f"Resolved:    semantically -> {_clean(choice.get('provider', '?'))}/"
                f"{_clean(choice.get('capability', '?'))}:{_clean(choice.get('action', '?'))} "
                f"(confidence {_clean(proposal.get('confidence') or '-')})")
            if proposal.get("reason"):
                lines.append(f"  rationale: {_clean(proposal['reason'])}")
            alternatives = _list(proposal.get("alternatives"))
            if alternatives:
                lines.append(f"  alternatives: {', '.join(alternatives)}")
    if task:
        lines.extend(_risk(data.get("risk")))
    telemetry = data.get("telemetry")
    if context:
        lines.extend(_context_sections(data, context))
    if context or telemetry:
        lines.append(f"Drift:       {_drift(data)}")
    if task or telemetry:
        lines.append(_telemetry(telemetry))
    if result:
        lines.append(f"Result:      {_clean(result.get('status', '?'))}: "
                     f"{len(result.get('findings') or [])} findings, "
                     f"{len(result.get('evidence') or [])} evidence")
    provider_receipt = (result or {}).get("provider_receipt")
    if provider_receipt:  # nested receipt: the provider-native run record to drill into
        lines.append(f"Native rcpt: {_clean(provider_receipt.get('ref', '?'))}  "
                     f"sha256={_clean(provider_receipt.get('sha256', '?'))[:12]}")
    native_trace = (result or {}).get("native_trace")
    if native_trace:  # trace federation: the native ref; spans stay provider-side
        lines.append(f"Native trace: {_clean(native_trace.get('ref', '?'))}"
                     + (f"  {_clean(native_trace['summary'])}"
                        if native_trace.get("summary") else ""))
    error = receipt.get("error")
    if error:
        unlock = f" (unlock: {_clean(error['unlock'])})" if error.get("unlock") else ""
        lines.append(f"Error:       {_clean(error.get('code', '?'))}: "
                     f"{_detail(error.get('detail', '?'))}{unlock}")
    if receipt:
        inputs = receipt.get("inputs") or {}
        hashes = " ".join(
            f"{_clean(key).removesuffix('_sha256')}={_short_hashes(value)}"
            for key, value in sorted(inputs.items())
            # no negotiation rounds, or no handoff (not a plan node run): omit
            if not (isinstance(value, list) and not value)
            and not (key == "handoff_sha256" and value is None))
        lines.append(f"Receipt:     {hashes} "
                     f"result={_clean(receipt.get('result_sha256') or '-')[:12]}")
    return "\n".join(lines)


# --- cross-forge-foundation: ExplainReport sections, plan, workspace and replay -------------
# Appended after the Wave B/C ``explain`` text, whose lines never change format (7.3).

_CHECKS = ("self_report", "provider_evidence", "forge", "independent")


def _list(values: object) -> list[str]:
    return [_clean(v) for v in values] if isinstance(values, list) else []


def _counts(by_epistemic: dict[str, Any] | None) -> str:
    return " ".join(f"{_clean(k)}={_clean(v)}" for k, v in (by_epistemic or {}).items())


def _divergence_rows(divergences: list[dict[str, Any]]) -> list[str]:
    return [f"  {_clean(d.get('kind', '?'))} {_clean(d.get('artifact', '?'))}"
            for d in divergences]


def _integrity(integrity: dict[str, Any]) -> list[str]:
    divergences = integrity.get("divergences") or []
    if not divergences:
        unrecorded = integrity.get("unrecorded") or []
        extra = f", {len(unrecorded)} unrecorded" if unrecorded else ""
        return [f"Integrity:   ok ({len(integrity.get('checked') or [])} checked{extra})"]
    return [f"Integrity:   {len(divergences)} divergence(s)", *_divergence_rows(divergences)]


def _verification(verification: dict[str, Any]) -> list[str]:
    indep = verification.get("independent") or {}
    verifier = next((str(b).removeprefix("verifier:") for b in indep.get("basis") or []
                     if str(b).startswith("verifier:")), None)
    lines = ["Verification: " + " ".join(
        f"{name}={_clean((verification.get(name) or {}).get('status', '?'))}"
        + (f" ({_clean(verifier)})" if name == "independent" and verifier else "")
        for name in _CHECKS)]
    for name in _CHECKS:
        check = verification.get(name) or {}
        status = check.get("status")
        # ``why the verifier`` and ``why no verifier`` are both routing evidence.
        if status == "failed" or (name == "independent" and status == "not_performed"):
            lines.extend(f"  {name}: {detail}" for detail in _list(check.get("details")))
    return lines


def _dependency(dep: dict[str, Any]) -> str:
    rule = f", {_clean(dep['rule'])}" if dep.get("rule") else ""
    return (f"{_clean(dep.get('node', '?'))} ({_clean(dep.get('epistemic', '?'))}{rule}: "
            f"{_clean(dep.get('evidence', '?'))})")


def _node_row(node: dict[str, Any], outcome: dict[str, Any] | None) -> str:
    row = (f"{_clean(node.get('id', '?'))} {_clean(node.get('provider', '?'))} "
           f"{_clean(node.get('capability', '?'))}:{_clean(node.get('action', '?'))}")
    deps = ", ".join(_dependency(d) for d in node.get("depends_on") or [])
    if deps:
        row += f"  after {deps}"
    if outcome:
        row += f"  -> {_clean(outcome.get('status', '?'))}"
        if outcome.get("run_id"):
            row += f" run={_clean(outcome['run_id'])}"
        if outcome.get("reused"):
            row += " (reused)"
        attempts = outcome.get("attempts") or 0
        if isinstance(attempts, int) and attempts > 1:
            row += f" x{attempts} attempts"
        if outcome.get("blocked_by"):
            row += f" blocked_by={_clean(outcome['blocked_by'])}"
    return row


def _synthesis_lines(result: dict[str, Any]) -> list[str]:
    synthesis = result.get("synthesis") or {}
    lines = _labelled("Handoffs:", [
        f"{_clean(h.get('source', '?'))} -> {_clean(h.get('target', '?'))}: "
        f"{_clean(h.get('items', 0))} items" + (" (truncated)" if h.get("truncated") else "")
        for h in synthesis.get("handoffs") or []])
    lines += _labelled("Synthesis:", [
        f"{_clean(n.get('node', '?'))} {_clean(n.get('status', '?'))}: "
        f"{len(n.get('findings') or [])} findings"
        + (f", evidence {_counts(n.get('evidence_by_epistemic'))}"
           if n.get("evidence_by_epistemic") else "")
        for n in synthesis.get("nodes") or []])
    failures = _list(synthesis.get("failures"))
    if failures:
        lines += _labelled("Failures:", failures)
    level = (result.get("reproducibility") or {}).get("level", "unknown")
    lines.append(f"Plan result: {_clean(result.get('status', '?'))}  "
                 f"order: {', '.join(_list(result.get('order'))) or 'none'}  "
                 f"reproducibility: {_clean(level)}")
    return lines


def _economy_lines(economy: dict[str, Any]) -> list[str]:
    """The EconomyRollup lines: per-metric totals, then per-node receipts."""
    totals = economy.get("totals") or {}
    cells = []
    for name in ("cost_usd", "provider_tokens", "context_bytes", "tool_calls",
                 "model_calls", "wall_time_ms"):
        metric = totals.get(name) or {}
        value = metric.get("value")
        cells.append(f"{name}={_num(value)}" if value is not None
                     else f"{name}={_clean(metric.get('status') or 'unresolved')}")
    lines = [f"Economy:     {'  '.join(cells)}"]
    lines += _labelled("  per-node:", [
        f"{_clean(entry.get('node'))}={(entry.get('receipt') or {}).get('provider', '?')}"
        for entry in economy.get("receipts") or []])
    lines += _labelled("  conflicts:", _list(economy.get("conflicts")))
    lines += _labelled("  notes:", _list(economy.get("limitations")))
    return lines


def _decision_lines(decision: dict[str, Any]) -> list[str]:
    """The DecisionRecord of a debate plan: options, choice, rationale, confidence."""
    lines = _labelled("Options:", [
        f"{_clean(o.get('node', '?'))} {_clean(o.get('provider', '?'))}/"
        f"{_clean(o.get('capability', '?'))} -> {_clean(o.get('status', '?'))}"
        + (f"  {_detail(o['position'])}" if o.get("position") else "")
        + (f"  (risks: {_clean('; '.join(str(r) for r in o['risks']))})"
           if o.get("risks") else "")
        for o in decision.get("options") or []])
    chosen = _clean(decision.get("chosen", "?"))
    rejected = ", ".join(_clean(r) for r in _list(decision.get("rejected"))) or "none"
    lines.append(f"Decision:    {chosen}  (rejected: {rejected}; "
                 f"confidence: {_clean(decision.get('confidence', '?'))})")
    rationale = _clean(decision.get("rationale") or "")
    if rationale:
        lines.append(f"Rationale:   {rationale}")
    return lines


def plan_sections(plan_data: dict[str, Any] | None, result: dict[str, Any] | None,
                  descriptor: dict[str, Any] | None,
                  installation: dict[str, Any] | None,
                  decision: dict[str, Any] | None = None,
                  semantic_proposal: dict[str, Any] | None = None,
                  capability_graph: dict[str, Any] | None = None,
                  economy: dict[str, Any] | None = None) -> list[str]:
    """Plan, node states with their runs, handoffs, synthesis, workspace and installation."""
    lines: list[str] = []
    if capability_graph:
        lines.append(f"Graph:       {len(capability_graph.get('nodes') or [])} nodes, "
                     f"{len(capability_graph.get('edges') or [])} edges "
                     "(the declared+observed relations the planner could see)")
    if plan_data:
        lines.append(f"Plan:        {_clean(plan_data.get('status', '?'))}  "
                     f"pattern: {_clean(plan_data.get('pattern', '?'))}  "
                     f"source: {_clean(plan_data.get('source', '?'))}  "
                     f"profile: {_clean(plan_data.get('profile', '?'))}")
    if semantic_proposal:  # tier-2 planner (Wave C): its rationale is the why
        lines.append(f"Planner:     semantic proposal  "
                     f"(confidence {_clean(semantic_proposal.get('confidence') or '-')})")
        rationale = _clean(semantic_proposal.get("rationale") or "")
        if rationale:
            lines.append(f"  rationale: {rationale}")
        assumptions = _list(semantic_proposal.get("assumptions"))
        if assumptions:
            lines += _labelled("  assumptions:", assumptions)
    if plan_data:
        outcomes = {n.get("node"): n for n in (result or {}).get("nodes") or []}
        lines += _labelled("Nodes:", [_node_row(node, outcomes.get(node.get("id")))
                                      for node in plan_data.get("nodes") or []])
        violations = [f"{_clean(v.get('code', '?'))} {_clean(v.get('node') or '-')}: "
                      f"{_clean(v.get('detail', ''))}"
                      for v in plan_data.get("violations") or []]
        if violations:
            lines += _labelled("Violations:", violations)
    if result:
        lines += _synthesis_lines(result)
    if decision:
        lines += _decision_lines(decision)
    if economy:
        lines += _economy_lines(economy)
    if descriptor:
        repositories = [_clean(r.get("path", "?")) for r in descriptor.get("repositories") or []]
        lines.append(f"Workspace:   {len(repositories)} repositories "
                     f"({', '.join(repositories) or 'none'}); "
                     f"{len(descriptor.get('technologies') or [])} technologies; "
                     f"{len(descriptor.get('relations') or [])} relations")
    if plan_data:
        lines += _labelled("Install:", [
            f"{_clean(i.get('provider', '?'))} {_clean(i.get('state', '?'))}: "
            f"{_clean(i.get('suggested_action', ''))} "
            f"(nodes: {', '.join(_list(i.get('nodes'))) or 'none'})"
            for i in (installation or {}).get("items") or []])
    return lines


def report_sections(report: dict[str, Any]) -> list[str]:
    """The sections of an ``ExplainReport`` (as a dict) the Wave B/C text does not show."""
    lines: list[str] = []
    provider = report.get("provider")
    if provider:
        observed = provider.get("observed_version")
        note = (f"; observed {_clean(observed)}"
                if observed and observed != provider.get("version") else "")
        lines.append(f"Provider:    {_clean(provider.get('id', '?'))} "
                     f"{_clean(provider.get('version', '?'))} "
                     f"(trust: {_clean(provider.get('trust', '?'))}{note})")
    result = report.get("result")
    if result:
        by_epistemic = result.get("evidence_by_epistemic") or {}
        total = sum(v for v in by_epistemic.values() if isinstance(v, int))
        lines.append(f"Evidence:    {total} ({_counts(by_epistemic) or 'none'})   "
                     f"duration={_metric({'d': result.get('duration_ms')}, 'd', 'ms')}")
    verification = report.get("verification")
    if verification:
        lines += _verification(verification)
    elif report.get("kind") == "run":
        lines.append("Verification: not recorded")
    reproducibility = report.get("reproducibility") or {}
    reasons = "; ".join(_list(reproducibility.get("reasons")))
    lines.append(f"Reproducibility: {_clean(reproducibility.get('level', 'unknown'))}"
                 + (f" ({reasons})" if reasons else ""))
    if report.get("parent_run"):
        node = ((report.get("artifacts") or {}).get("receipt") or {}).get("plan_node")
        lines.append(f"Plan run:    {_clean(report['parent_run'])}"
                     + (f" (node {_clean(node)})" if node else ""))
    if report.get("replay_of"):
        lines.append(f"Replay of:   {_clean(report['replay_of'])}")
    if report.get("resumed_from"):
        lines.append(f"Resumed from: {_clean(report['resumed_from'])}")
    section = report.get("plan") or {}
    if section:
        artifacts = report.get("artifacts") or {}
        lines += plan_sections(section.get("plan"), section.get("result"),
                               section.get("workspace_descriptor"), section.get("installation"),
                               artifacts.get("decision"),
                               artifacts.get("semantic-proposal"),
                               artifacts.get("capability-graph"),
                               section.get("economy"))
    if report.get("error"):
        lines.append(f"Error family: {_clean(report.get('error_family') or 'provider code')}")
    lines += _labelled("Limitations:", _list(report.get("limitations")))
    lines += _labelled("Unknowns:", _list(report.get("unknowns")))
    lines += _integrity(report.get("integrity") or {})
    lines.append(f"Not recorded: {', '.join(_list(report.get('not_recorded'))) or 'none'}")
    return lines


def explain_report(report: dict[str, Any]) -> str:
    """Text of an ``ExplainReport``: the Wave B/C text over its raw artifacts, unchanged,
    followed by the sections added by cross-forge-foundation."""
    base = explain({"run_id": report.get("run_id", "?"), **(report.get("artifacts") or {})})
    return "\n".join([base, *report_sections(report)])


def plan(data: dict[str, Any]) -> str:
    run_id = _clean(data["run_id"])
    lines = [f"Run {run_id}: {_clean(data['status'])}"]
    if data.get("resumed_from"):
        lines.append(f"Resumed from: {_clean(data['resumed_from'])}")
    lines += plan_sections(data.get("plan"), data.get("result"), None,
                           data.get("installation"), data.get("decision"),
                           data.get("semantic_proposal"), data.get("capability_graph"),
                           data.get("economy"))
    error = data.get("error")
    if error:
        lines.append(f"Error:       {_clean(error['code'])}: {_detail(error['detail'])} "
                     f"{code_suffix(error['code'], data.get('error_family'))}")
        if error.get("unlock"):
            lines.append(f"Unlock:      {_clean(error['unlock'])}")
    if data["status"] == "planned":
        lines.append("Execute:     nothing was executed; re-run with --execute")
    lines.append(f"Explain:     theforge explain {run_id}")
    return "\n".join(lines)


def workspace(data: dict[str, Any]) -> str:
    repositories = []
    for repo in data.get("repositories") or []:
        git = _git({"workspace": {"git": repo.get("git")},
                    "limitations": repo.get("limitations") or []})
        deps = ", ".join(_list(repo.get("dependency_files"))) or "none"
        repositories.append(f"{_clean(repo.get('path', '?'))}  git: {git}  "
                            f"dependencies: {deps}")
    technologies = [
        f"{_clean(t.get('name', '?'))} in {_clean(t.get('repository', '?'))} "
        f"({_clean(t.get('source', '?'))}: {_clean(t.get('evidence', '?'))})"
        + (f" matched_by {','.join(_list(t.get('matched_by')))}" if t.get("matched_by") else "")
        for t in data.get("technologies") or []]
    relations = [
        f"{_clean(r.get('source', '?'))} {_clean(r.get('kind', '?'))} "
        f"{_clean(r.get('target', '?'))} ({_clean(r.get('epistemic', '?'))}: "
        f"{_clean(r.get('evidence', '?'))})" for r in data.get("relations") or []]
    return "\n".join([f"Workspace:   {_clean(data.get('root', '?'))}",
                      *_labelled("Repos:", repositories),
                      *_labelled("Tech:", technologies),
                      *_labelled("Relations:", relations),
                      *_labelled("Limitations:", _list(data.get("limitations"))),
                      *_labelled("Unknowns:", _list(data.get("unknowns")))])


def decisions(data: dict[str, Any]) -> str:
    """The reusable-decision memory: one line per remembered decision."""
    entries = data.get("entries") or []
    lines = []
    for entry in sorted(entries, key=lambda e: (e.get("kind") or "",
                                                e.get("subject") or "")):
        runs = _list(entry.get("runs"))
        lines.append(
            f"{_clean(entry.get('kind', '?'))}: {_clean(entry.get('subject', '?'))} -> "
            f"{_clean(entry.get('choice', '?'))}  "
            f"({entry.get('corroborations', 1)}x, last {_clean(entry.get('updated_at', '?'))}"
            f"{'; runs ' + ','.join(runs[-3:]) if runs else ''})\n"
            f"    basis: {_clean(entry.get('basis', '?'))}")
    return "\n".join([f"Decision memory: {len(entries)} entr"
                      f"{'y' if len(entries) == 1 else 'ies'}", *lines,
                      *_labelled("Limitations:", _list(data.get("limitations")))])


_TRACE_ATTRS = ("node", "provider", "capability", "action", "role", "round",
                "outcome", "attempts", "reused")


def _span_line(span: dict[str, Any]) -> str:
    """One span row: name, the interesting attributes, duration, error marker."""
    attrs = span.get("attributes") or {}
    shown = " ".join(f"{key}={_clean(attrs[key])}" for key in _TRACE_ATTRS
                     if key in attrs)
    name = _clean(span.get("name", "?"))
    if shown:
        name = f"{name} ({shown})"
    try:
        ms = float(span.get("duration_ms") or 0.0)
    except (TypeError, ValueError):
        ms = 0.0
    marker = "  ERROR" if span.get("status") == "error" else ""
    return f"{name}  {ms:.1f}ms{marker}"


def trace(data: dict[str, Any]) -> str:
    """The run's local trace (Wave J): *what happened* — spans in start order,
    nested by parent. ``explain`` answers why; ``trace`` answers what."""
    spans = [s for s in (data.get("spans") or []) if isinstance(s, dict)]
    total = 0.0
    for span in spans:
        try:
            total = max(total, float(span.get("start_ms") or 0.0)
                        + float(span.get("duration_ms") or 0.0))
        except (TypeError, ValueError):
            continue
    lines = [f"trace {_clean(data['run_id'])}  {_clean(data.get('status') or 'unknown')}  "
             f"{total:.0f}ms"]
    ids = {s.get("id") for s in spans}
    children: dict[Any, list[dict[str, Any]]] = {}
    for span in spans:
        parent = span.get("parent")
        children.setdefault(parent if parent in ids else None, []).append(span)
    for group in children.values():
        group.sort(key=lambda s: (float(s.get("start_ms") or 0.0),
                                  str(s.get("id") or "")))

    def _level(parent: Any, prefix: str) -> None:
        group = children.get(parent) or []
        for index, span in enumerate(group):
            last = index == len(group) - 1
            lines.append(f"{prefix}{'└─ ' if last else '├─ '}{_span_line(span)}")
            _level(span.get("id"), prefix + ("   " if last else "│  "))

    _level(None, "")
    if not spans:
        lines.append("  no spans recorded")
    return "\n".join([*lines, *_labelled("Limitations:", _list(data.get("limitations")))])


def replay(data: dict[str, Any]) -> str:
    run_id = _clean(data["run_id"])
    if data["mode"] == "render":
        return explain_report(data["report"])
    if data["mode"] == "verify":
        divergences = data.get("divergences") or []
        head = f"{len(divergences)} divergence(s)" if divergences else "no divergence"
        return "\n".join([f"Replay verify of {run_id}: {head}",
                          *_divergence_rows(divergences)])
    new_run = _clean(data.get("new_run") or "?")
    return "\n".join([f"Replay execute of {run_id}: new run {new_run} "
                      f"({_clean(data.get('new_status') or '?')})",
                      f"Comparison:  {_clean(data.get('comparison') or '?')}",
                      f"Explain:     theforge explain {new_run}"])
