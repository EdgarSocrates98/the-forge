"""Specialist delegation (FASE 5): real argv execution, honest stages.

The delegation channel is the specialist's own CLI argv — the same
proven channel `install_command` uses. No fabricated invocations:

- DIRECT_CAPABILITY / DIAGNOSTIC_ONLY / SPECIALIST_WORKFLOW execute a
  real subprocess; COMPLETED requires exit_code evidence.
- HOST_AGENTIC is executed *by the host*, not by us — the honest result
  is PREPARED with the envelope for the host to run.
- MULTI_SPECIALIST fans out to per-provider requests; each keeps its own
  stage and a global budget caps the fan-out.
"""

from __future__ import annotations

import subprocess
import time
import uuid
from dataclasses import replace

from theforge.contracts.specialist import (
    DelegationRequest,
    DelegationResult,
)

_TAIL = 20  # lines of stdout/stderr kept as evidence
_DEFAULT_TIMEOUT_S = 600


def new_request(
    *,
    intent: str,
    provider: str,
    execution_mode: str,
    command: list[str],
    target: str = "project",
    constraints: list[str] | None = None,
    expected_outputs: list[str] | None = None,
    verification: list[str] | None = None,
    budget: dict[str, int] | None = None,
) -> DelegationRequest:
    return DelegationRequest(
        task_id=f"task-{uuid.uuid4().hex[:12]}",
        intent=intent,
        provider=provider,
        execution_mode=execution_mode,
        target=target,
        command=command,
        constraints=constraints or [],
        expected_outputs=expected_outputs or [],
        verification=verification or [],
        budget=budget or {},
    )


def prepare(request: DelegationRequest, *, note: str) -> DelegationResult:
    """PREPARED without executing — for HOST_AGENTIC or dry-run."""
    return DelegationResult(
        task_id=request.task_id,
        provider=request.provider,
        stage="PREPARED",
        execution_mode=request.execution_mode,
        evidence=[note],
        limitations=["not executed — staged for host or approval"],
    )


def execute(request: DelegationRequest, *, cwd: str | None = None) -> DelegationResult:
    """Run the request's argv for real and record the honest stage."""
    if request.execution_mode == "HOST_AGENTIC":
        return prepare(request, note="HOST_AGENTIC is executed by the host runtime")
    if not request.command:
        return DelegationResult(
            task_id=request.task_id,
            provider=request.provider,
            stage="BLOCKED",
            execution_mode=request.execution_mode,
            limitations=["no executable command declared for this delegation"],
        )

    started = time.monotonic()
    try:
        proc = subprocess.run(
            request.command,
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=_DEFAULT_TIMEOUT_S,
        )
    except FileNotFoundError:
        return DelegationResult(
            task_id=request.task_id,
            provider=request.provider,
            stage="BLOCKED",
            execution_mode=request.execution_mode,
            limitations=[f"executable not found: {request.command[0]!r}"],
        )
    except subprocess.TimeoutExpired:
        return DelegationResult(
            task_id=request.task_id,
            provider=request.provider,
            stage="FAILED",
            execution_mode=request.execution_mode,
            limitations=[f"timeout after {_DEFAULT_TIMEOUT_S}s"],
            elapsed_ms=int((time.monotonic() - started) * 1000),
        )

    elapsed = int((time.monotonic() - started) * 1000)
    ok = proc.returncode == 0
    return DelegationResult(
        task_id=request.task_id,
        provider=request.provider,
        stage="COMPLETED" if ok else "FAILED",
        execution_mode=request.execution_mode,
        executed_steps=[" ".join(request.command)],
        evidence=[f"exit_code={proc.returncode}", f"elapsed_ms={elapsed}"],
        stdout_tail=proc.stdout.splitlines()[-_TAIL:],
        stderr_tail=proc.stderr.splitlines()[-_TAIL:],
        exit_code=proc.returncode,
        elapsed_ms=elapsed,
    )


def fan_out(
    requests: list[DelegationRequest],
    *,
    max_parallel: int = 4,
    cwd: str | None = None,
) -> list[DelegationResult]:
    """MULTI_SPECIALIST fan-out, sequentially executed with a budget cap.

    Sequential is deliberate: specialists are heavyweight CLIs and the
    budget unit is *providers touched*, not wall-clock parallelism.
    """
    results: list[DelegationResult] = []
    for req in requests[:max_parallel]:
        results.append(execute(replace(req, execution_mode=req.execution_mode), cwd=cwd))
    for req in requests[max_parallel:]:
        results.append(
            DelegationResult(
                task_id=req.task_id,
                provider=req.provider,
                stage="BLOCKED",
                execution_mode=req.execution_mode,
                limitations=[f"budget: max_parallel={max_parallel} reached"],
            )
        )
    return results
