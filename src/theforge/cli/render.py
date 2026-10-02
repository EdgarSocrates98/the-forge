"""Human-readable renderers. Pure functions: dict in, text out."""

from typing import Any


def init(data: dict[str, Any]) -> str:
    if not data["created"]:
        return f"{data['forge_dir']} already initialized"
    return "\n".join([f"Initialized {data['forge_dir']}",
                      *(f"  created {path}" for path in data["created"])])


def doctor(data: dict[str, Any]) -> str:
    lines = [f"The Forge {data['forge_version']} - {data['root']}"]
    for check in data["checks"]:
        lines.append(f"{check['name']:.<32} {check['status']:<5} {check['detail']}")
    lines.append("healthy" if data["healthy"] else "UNHEALTHY")
    return "\n".join(lines)


def status(data: dict[str, Any]) -> str:
    if not data["initialized"]:
        return f"{data['root']}: not initialized (run `theforge init`)"
    return "\n".join([
        f"Workspace:  {data['root']}",
        f"Providers:  {', '.join(data['cached_providers']) or 'none cached'}",
        f"Runs:       {data['runs']} (last: {data['last_run'] or '-'})",
    ])


def providers(data: dict[str, Any]) -> str:
    lines = []
    for p in data["providers"]:
        line = (f"{p['id']:<20} {p['state']:<13} trust={p['trust']:<10} "
                f"source={p['source']:<8} version={p['version'] or '-'}")
        if p["error"]:
            line += f"  error: {p['error']}"
        lines.append(line)
    return "\n".join(lines) or "no providers"


def provider_detail(data: dict[str, Any]) -> str:
    lines = [providers({"providers": [data]}),
             f"argv:      {' '.join(data['argv'])}",
             f"protocol:  {data['protocol'] or '-'}",
             f"manifest:  {data['manifest_sha256'] or '-'}"]
    for cap in (data["manifest"] or {}).get("capabilities", []):
        lines.append(f"  {cap['id']:<28} actions={','.join(cap['actions'])} "
                     f"state={cap['state']} class={cap['operation_class']}")
    return "\n".join(lines)


def capabilities(data: dict[str, Any]) -> str:
    rows = data["capabilities"]
    if not rows:
        return "no capabilities found"
    lines = []
    for c in rows:
        line = f"{c['id']:<28} {c['provider']:<20} actions={','.join(c['actions'])} " \
               f"state={c['state']}"
        if c["description"]:
            line += f"  - {c['description']}"
        lines.append(line)
    return "\n".join(lines)


def health(data: dict[str, Any]) -> str:
    lines = []
    for p in data["providers"]:
        line = f"{p['id']:<20} {p['status']}"
        if p["error"]:
            line += f"  {p['error']['code']}: {p['error']['detail']}"
        lines.append(line)
    return "\n".join(lines) or "no providers"


def ask(data: dict[str, Any]) -> str:
    decision = data["decision"]
    lines = [f"Run {data['run_id']}: {data['status']}"]
    if decision["selected"]:
        sel = decision["selected"][0]
        lines.append(f"Selected:   {sel['provider']} {sel['capability']}:{sel['action']} "
                     f"(confidence {decision['confidence']['level']})")
    lines.append(f"Reason:     {decision['reason']}")
    if data["status"] in ("ambiguous", "no_route"):
        for cand in decision["candidates"]:
            lines.append(f"  candidate {cand['provider']}/{cand['capability']} "
                         f"rank={cand['rank_key']}")
        lines.append("Hint:       pass --capability <id> (see `theforge capabilities list`)")
    result = data["result"]
    if result:
        lines.append(f"Findings:   {len(result['findings'])}   "
                     f"Evidence: {len(result['evidence'])}")
        lines.extend(f"  [{f['severity']}] {f['title']}" for f in result["findings"])
    error = data["error"]
    if error:
        lines.append(f"Error:      {error['code']}: {error['detail']}")
        if error.get("unlock"):
            lines.append(f"Unlock:     {error['unlock']}")
    lines.append(f"Explain:    theforge explain {data['run_id']}")
    return "\n".join(lines)


def _signals(matched: dict[str, list[str]]) -> str:
    parts = [f"{key}[{','.join(hits)}]" for key in ("dependencies", "file_globs", "keywords")
             if (hits := matched.get(key))]
    return " ".join(parts) or "requested"


def explain(data: dict[str, Any]) -> str:
    task = data.get("task") or {}
    routing = data.get("routing") or {}
    context = data.get("context")
    result = data.get("result")
    receipt = data.get("receipt") or {}
    lines = [f"Run:         {data['run_id']}  status: {receipt.get('status', 'incomplete')}"]
    if task:
        lines.append(f"Task:        \"{task['intent']}\" (targets: {', '.join(task['targets'])};"
                     f" profile: {task['budget_profile']})")
    if routing:
        candidates = routing.get("candidates", [])
        if not candidates:
            lines.append("Candidates:  none")
        for index, cand in enumerate(candidates):
            label = "Candidates:" if index == 0 else ""
            lines.append(f"{label:<13}{cand['provider']}/{cand['capability']}  "
                         f"{_signals(cand['matched'])}  rank={cand['rank_key']}")
        selected = ", ".join(f"{s['provider']} {s['capability']}:{s['action']} ({s['role']})"
                             for s in routing.get("selected", [])) or "none"
        lines.append(f"Selected:    {selected}   pattern: {routing['pattern']}")
        lines.append(f"Reason:      {routing['reason']}")
        conf = routing["confidence"]
        lines.append(f"Confidence:  {conf['level']}   measured: {conf['measured_signals']}"
                     f"   unresolved: {conf['unresolved']}")
        lines.append(f"Fallbacks:   {', '.join(routing.get('fallbacks_used', [])) or 'none'}")
    if context:
        lines.append(f"Context:     {len(context['files'])} files, {context['used_bytes']}/"
                     f"{context['budget_bytes']} bytes ({context['status']}); "
                     f"excluded {len(context['excluded'])}")
    if result:
        lines.append(f"Result:      {result['status']}: {len(result['findings'])} findings, "
                     f"{len(result['evidence'])} evidence")
    error = receipt.get("error")
    if error:
        unlock = f" (unlock: {error['unlock']})" if error.get("unlock") else ""
        lines.append(f"Error:       {error['code']}: {error['detail']}{unlock}")
    if receipt:
        inputs = receipt["inputs"]
        hashes = " ".join(f"{key.removesuffix('_sha256')}={(value or '-')[:12]}"
                          for key, value in sorted(inputs.items()))
        lines.append(f"Receipt:     {hashes} result={(receipt.get('result_sha256') or '-')[:12]}")
    return "\n".join(lines)
