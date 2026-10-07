"""Remote validation classification stays evidence-honest."""

import json

from scripts.ci.classify_remote_validation import (
    NOT_RUN,
    REMOTE_BLOCKED,
    REMOTE_FAILED,
    REMOTE_VERIFIED,
    classify,
    main,
)


def job(name: str, conclusion: str, *, steps: list[dict[str, object]] | None):
    return {"name": name, "conclusion": conclusion, "steps": steps}


def test_no_jobs_is_not_run() -> None:
    assert classify({"jobs": []})["state"] == NOT_RUN


def test_jobs_without_steps_are_remote_blocked_not_failed() -> None:
    result = classify({
        "jobs": [
            job("linux", "failure", steps=None),
            job("windows", "failure", steps=None),
        ]
    })
    assert result["state"] == REMOTE_BLOCKED
    assert result["jobs_with_steps"] == 0
    assert result["failed_jobs_with_steps"] == []


def test_executed_failing_gate_is_remote_failed() -> None:
    result = classify({
        "jobs": [
            job(
                "linux",
                "failure",
                steps=[{"name": "pytest", "conclusion": "failure"}],
            )
        ]
    })
    assert result["state"] == REMOTE_FAILED
    assert result["failed_jobs_with_steps"] == ["linux"]


def test_all_executed_green_jobs_are_remote_verified() -> None:
    result = classify({
        "jobs": [
            job(
                "linux",
                "success",
                steps=[{"name": "pytest", "conclusion": "success"}],
            ),
            job(
                "windows",
                "success",
                steps=[{"name": "pytest", "conclusion": "success"}],
            ),
        ]
    })
    assert result["state"] == REMOTE_VERIFIED


def test_partial_matrix_execution_remains_blocked() -> None:
    result = classify({
        "jobs": [
            job(
                "linux",
                "success",
                steps=[{"name": "pytest", "conclusion": "success"}],
            ),
            job("windows", "failure", steps=None),
        ]
    })
    assert result["state"] == REMOTE_BLOCKED


def test_skipped_required_job_is_not_remote_verified() -> None:
    result = classify({
        "jobs": [
            job(
                "linux",
                "success",
                steps=[{"name": "pytest", "conclusion": "success"}],
            ),
            job(
                "windows",
                "skipped",
                steps=[{"name": "pytest", "conclusion": "skipped"}],
            ),
        ]
    })
    assert result["state"] == REMOTE_BLOCKED
    assert "windows" in result["blocked_jobs"]


def test_require_verified_exit_code(tmp_path) -> None:
    blocked = tmp_path / "blocked.json"
    blocked.write_text(
        json.dumps({"jobs": [job("linux", "failure", steps=None)]}),
        encoding="utf-8",
    )
    green = tmp_path / "green.json"
    green.write_text(
        json.dumps({
            "jobs": [
                job(
                    "linux",
                    "success",
                    steps=[{"name": "pytest", "conclusion": "success"}],
                )
            ]
        }),
        encoding="utf-8",
    )
    assert main([str(blocked), "--require-verified"]) == 1
    assert main([str(green), "--require-verified"]) == 0
