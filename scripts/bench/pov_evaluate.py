#!/usr/bin/env python3
"""Conservative PoV CSV assessor. Never manufactures evidence or missing metrics."""
import csv
import json
import math
import statistics
import sys
from typing import Any

SCENARIOS = ("S1", "S2", "S3")
ARMS = ("A", "B", "C", "D")
METRICS = (
    "wall_seconds", "tokens_input", "tokens_output",
    "cost_usd", "human_interventions", "handoffs",
)


def number(value: str | None) -> float | None:
    if value is None or value.strip().lower() in ("", "null", "unknown"):
        return None
    x = float(value)
    if not math.isfinite(x) or x < 0:
        raise ValueError("non-finite or negative number")
    return x


def flag(value: str | None) -> bool | None:
    if value is None or value.strip().lower() in ("", "null", "unknown"):
        return None
    if value.strip().lower() in ("true", "yes", "1"):
        return True
    if value.strip().lower() in ("false", "no", "0"):
        return False
    raise ValueError("invalid boolean")


def assess(path: str) -> dict[str, Any]:
    with open(path, encoding="utf-8-sig", newline="") as fp:
        reader = csv.DictReader(fp)
        rows = list(reader)
        columns = set(reader.fieldnames or ())
    required = {"scenario", "repeat", "arm", "run_id", "repo_sha", "model", "effort",
                "completed", "security_pass", "quality_passed", "quality_total",
                "evidence_uri", *METRICS}
    if not required.issubset(columns):
        return {"status": "invalid_schema", "missing_columns": sorted(required - columns)}
    clean: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    seen: set[tuple[str, int, str]] = set()
    for line, r in enumerate(rows, 2):
        try:
            key = (r["scenario"], int(r["repeat"]), r["arm"])
            if key[0] not in SCENARIOS or key[1] not in (1, 2, 3) or key[2] not in ARMS:
                raise ValueError("invalid scenario, repeat or arm")
            if key in seen:
                raise ValueError("duplicate identity")
            seen.add(key)
            if not all(r.get(k, "").strip() for k in ("run_id", "repo_sha", "model", "effort")):
                raise ValueError("missing provenance")
            completed, secure = flag(r["completed"]), flag(r["security_pass"])
            passed, total = number(r["quality_passed"]), number(r["quality_total"])
            if (passed is None) != (total is None):
                raise ValueError("partial quality score")
            if total is not None and (
                total <= 0 or (passed is not None and passed > total)
                or passed is None or not passed.is_integer() or not total.is_integer()
            ):
                raise ValueError("invalid test counts")
            metrics = {k: number(r[k]) for k in METRICS}
            if completed is True and (
                secure is None or total is None or not r.get("evidence_uri", "").strip()
            ):
                raise ValueError("completed without independent evidence")
            quality = passed / total if total and passed is not None else None
            clean.append({"key": key, "completed": completed, "security": secure,
                          "quality": quality, "metrics": metrics})
        except (ValueError, TypeError, KeyError) as exc:
            errors.append({"line": line, "error": str(exc)})
    # Security failure is a disqualifier (README §primary endpoint): an
    # insecure-but-completed run is still an observation but never enters
    # the quality comparison pairs.
    by_key: dict[tuple[str, int, str], dict[str, Any]] = {
        r["key"]: r
        for r in clean
        if r["completed"] is True and r["security"] is True
    }
    pairs: dict[str, Any] = {}
    for arm in ("B", "C", "D"):
        aligned: list[dict[str, Any]] = []
        for scenario in SCENARIOS:
            for rep in (1, 2, 3):
                a = by_key.get((scenario, rep, "A"))
                b = by_key.get((scenario, rep, arm))
                if a and b:
                    aligned.append({
                        "scenario": scenario, "repeat": rep,
                        "quality_delta": b["quality"] - a["quality"],
                        "both_secure": a["security"] is True and b["security"] is True,
                        "cost_delta_usd": b["metrics"]["cost_usd"] - a["metrics"]["cost_usd"]
                        if (b["metrics"]["cost_usd"] is not None
                            and a["metrics"]["cost_usd"] is not None) else None
                    })
        pairs[arm + "_vs_A"] = {
            "n": len(aligned), "observations": aligned,
            "median_quality_delta": (
                statistics.median(x["quality_delta"] for x in aligned) if aligned else None
            )
        }
    completed_count = sum(r["completed"] is True for r in clean)
    if errors:
        status = "invalid_input"
    elif completed_count == 36:
        status = "complete_requires_independent_review"
    else:
        status = "incomplete"
    return {"schema": "theforge-pov/v1", "status": status, "observed": len(clean),
            "completed": completed_count, "required": 36, "invalid_rows": errors,
            "pairs": pairs, "proof_of_superiority": False,
            "limitations": ["Results require blinded independent acceptance and security review.",
                            "Three repeats per cell are exploratory, "
                            "not statistically conclusive."]}


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: pov_evaluate.py observations.csv")
    result = assess(sys.argv[1])
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if result["status"].startswith("invalid"):
        raise SystemExit(2)
