#!/usr/bin/env python3
"""Classify a GitHub Actions jobs payload without network access.

Input is the JSON returned by GitHub's jobs endpoint (or a compatible fixture).
This deliberately separates transport/execution blockage from actual gate
failure. It does not decide whether a release may proceed; policy consumes the
classification.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REMOTE_VERIFIED = "REMOTE_VERIFIED"
REMOTE_BLOCKED = "REMOTE_BLOCKED"
REMOTE_FAILED = "REMOTE_FAILED"
NOT_RUN = "NOT_RUN"


def _jobs(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict) and isinstance(payload.get("jobs"), list):
        jobs = payload["jobs"]
    elif isinstance(payload, list):
        jobs = payload
    else:
        raise ValueError("payload must be a jobs object or a list of jobs")
    if not all(isinstance(job, dict) for job in jobs):
        raise ValueError("jobs must contain JSON objects")
    return jobs


def classify(payload: Any) -> dict[str, Any]:
    jobs = _jobs(payload)
    if not jobs:
        return {
            "state": NOT_RUN,
            "jobs": 0,
            "jobs_with_steps": 0,
            "failed_jobs_with_steps": [],
            "blocked_jobs": [],
        }

    with_steps: list[dict[str, Any]] = []
    blocked: list[str] = []
    failed_with_steps: list[str] = []

    for job in jobs:
        name = str(job.get("name") or job.get("id") or "unknown-job")
        steps = job.get("steps")
        if not isinstance(steps, list) or not steps:
            blocked.append(name)
            continue
        with_steps.append(job)
        conclusion = job.get("conclusion")
        if conclusion == "skipped":
            blocked.append(name)
        elif conclusion != "success":
            failed_with_steps.append(name)

    if failed_with_steps:
        state = REMOTE_FAILED
    elif not with_steps:
        state = REMOTE_BLOCKED
    elif blocked:
        # Partial execution is not sufficient proof for the required matrix.
        state = REMOTE_BLOCKED
    elif all(job.get("conclusion") == "success" for job in with_steps):
        state = REMOTE_VERIFIED
    else:
        state = REMOTE_FAILED

    return {
        "state": state,
        "jobs": len(jobs),
        "jobs_with_steps": len(with_steps),
        "failed_jobs_with_steps": failed_with_steps,
        "blocked_jobs": blocked,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("jobs_json", type=Path)
    parser.add_argument(
        "--require-verified",
        action="store_true",
        help="return exit 1 unless the classified state is REMOTE_VERIFIED",
    )
    args = parser.parse_args(argv)
    try:
        payload = json.loads(args.jobs_json.read_text(encoding="utf-8"))
        result = classify(payload)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"validation-classifier: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    if args.require_verified and result["state"] != REMOTE_VERIFIED:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
