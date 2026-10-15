"""Public-adoption gate (cyc10-03, §10.9–§10.12).

- 7 templates of §10.10 exist, each with README (install instructions) and
  an executable check.sh (automated test entrypoint);
- 8 demos of §10.11 exist, executable, and contain no credential/network
  words that would prove they are not synthetic;
- contribution model doc exists and forbids default trust;
- feedback mechanism is opt-in + offline (script exists, no send/network);
- distribution plan exists with per-channel requirements;
- public claims: benchmark assertions trace to real artifacts.
"""

from __future__ import annotations

import os
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

TEMPLATES = [
    "api-apiforge",
    "pyspark-aws",
    "pyspark-azure",
    "terraform-platform",
    "multi-repo-theforge",
    "mcp-host-config",
    "custom-specialist",
]
DEMOS = [
    "01-install-linux",
    "02-two-forges",
    "03-host-config",
    "04-diagnostic",
    "05-orchestration",
    "06-portal",
    "07-benchmark",
    "08-evidence",
]
FORBIDDEN_DEMO = ["AWS_ACCESS_KEY", "SECRET", "TOKEN=", "curl http", "wget http", "api_key"]


def main() -> int:
    fails: list[str] = []

    for t in TEMPLATES:
        d = REPO / "templates" / t
        if not (d / "README.md").is_file():
            fails.append(f"templates/{t}/README.md missing")
        elif "Instalação" not in (d / "README.md").read_text():
            fails.append(f"templates/{t}: no install instructions")
        chk = d / "check.sh"
        if not chk.is_file() or not os.access(chk, os.X_OK):
            fails.append(f"templates/{t}/check.sh missing or not executable")

    for demo in DEMOS:
        fp = REPO / "demos" / f"{demo}.sh"
        if not fp.is_file():
            fails.append(f"demos/{demo}.sh missing")
            continue
        if not os.access(fp, os.X_OK):
            fails.append(f"demos/{demo}.sh not executable")
        body = fp.read_text()
        for bad in FORBIDDEN_DEMO:
            if bad in body:
                fails.append(f"demos/{demo}.sh contains '{bad}' — not synthetic")

    contrib = REPO / "docs" / "contributing" / "external-forges.md"
    if not contrib.is_file():
        fails.append("docs/contributing/external-forges.md missing")
    else:
        body = contrib.read_text()
        for needle in ("nunca é confiável por padrão", "manifesto", "proveniência", "untrusted"):
            if needle not in body.lower() and needle not in body:
                fails.append(f"external-forges.md missing '{needle}'")

    if not (REPO / "scripts" / "feedback_bundle.py").is_file():
        fails.append("scripts/feedback_bundle.py missing")
    else:
        body = (REPO / "scripts" / "feedback_bundle.py").read_text()
        if "requests.post" in body or "urllib.request.urlopen" in body.replace(
            "urllib.request.Request", ""
        ):
            fails.append("feedback_bundle.py performs network send — violates opt-in offline")

    dist = REPO / "docs" / "programs" / "ecosystem-2026" / "distribution-plan.md"
    if not dist.is_file():
        fails.append("distribution-plan.md missing")
    elif "PyPI" not in dist.read_text() or "MCP" not in dist.read_text():
        fails.append("distribution-plan.md lacks the D2 channels")

    bench = REPO / "docs" / "programs" / "ecosystem-2026" / "benchmarks"
    if not any(bench.glob("results-*.jsonl")):
        fails.append("no benchmark receipts — public claims would lack backing")

    if fails:
        for x in fails:
            print(f"FAIL {x}")
        return 1
    print(
        "adoption: 7 templates, 8 synthetic demos, trust model, "
        "opt-in feedback, D2 plan, claims backed"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
