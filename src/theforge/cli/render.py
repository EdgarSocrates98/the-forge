"""Human-readable renderers. Pure functions: dict in, text out."""

import re
from typing import Any

_UNSAFE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")


def _clean(value: object) -> str:
    """Stringify and neutralize control characters (terminal-escape injection)."""
    return _UNSAFE.sub("?", str(value))


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


def health(data: dict[str, Any]) -> str:
    lines = []
    for p in data["providers"]:
        line = f"{_clean(p['id']):<20} {_clean(p['status'])}"
        if p["error"]:
            line += f"  {_clean(p['error']['code'])}: {_clean(p['error']['detail'])}"
        lines.append(line)
    return "\n".join(lines) or "no providers"


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
        lines.append(f"Error:      {_clean(error['code'])}: {_clean(error['detail'])}")
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
        lines.append(f"Task:        \"{_clean(task.get('intent', '?'))}\" "
                     f"(targets: {targets}; profile: {_clean(task.get('budget_profile', '?'))})")
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
    if task:
        lines.extend(_risk(data.get("risk")))
    if context:
        lines.append(f"Context:     {len(context.get('files') or [])} files, "
                     f"{_clean(context.get('used_bytes', '?'))}/"
                     f"{_clean(context.get('budget_bytes', '?'))} bytes "
                     f"({_clean(context.get('status', '?'))}); "
                     f"excluded {len(context.get('excluded') or [])}")
    if result:
        lines.append(f"Result:      {_clean(result.get('status', '?'))}: "
                     f"{len(result.get('findings') or [])} findings, "
                     f"{len(result.get('evidence') or [])} evidence")
    error = receipt.get("error")
    if error:
        unlock = f" (unlock: {_clean(error['unlock'])})" if error.get("unlock") else ""
        lines.append(f"Error:       {_clean(error.get('code', '?'))}: "
                     f"{_clean(error.get('detail', '?'))}{unlock}")
    if receipt:
        inputs = receipt.get("inputs") or {}
        hashes = " ".join(f"{_clean(key).removesuffix('_sha256')}={_clean(value or '-')[:12]}"
                          for key, value in sorted(inputs.items()))
        lines.append(f"Receipt:     {hashes} "
                     f"result={_clean(receipt.get('result_sha256') or '-')[:12]}")
    return "\n".join(lines)
