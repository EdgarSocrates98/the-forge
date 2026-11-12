"""Execute the real-process Cycle 0.5 API Operations lab.

The lab is intentionally explicit about what it can and cannot prove.  It
executes local CLIs and a local HTTP service, writes only to a temporary lab
directory plus the requested output directory, and records unavailable agent
providers instead of faking a session.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import urlopen

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]


def _redact(value: str) -> str:
    for marker in ("AWS_SECRET_ACCESS_KEY=", "AWS_SESSION_TOKEN=", "Authorization:"):
        if marker in value:
            prefix, _, _ = value.partition(marker)
            value = prefix + marker + "[REDACTED]"
    return value


def _run(
    argv: list[str],
    *,
    cwd: Path,
    timeout: int = 180,
    env: dict[str, str],
) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        result = subprocess.run(
            argv,
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
        status = "PASSED" if result.returncode == 0 else "FAILED"
        return {
            "argv": argv,
            "cwd": str(cwd),
            "status": status,
            "returncode": result.returncode,
            "duration_ms": round((time.perf_counter() - started) * 1000, 3),
            "stdout": _redact(result.stdout[-12000:]),
            "stderr": _redact(result.stderr[-12000:]),
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "argv": argv,
            "cwd": str(cwd),
            "status": "BLOCKED",
            "returncode": None,
            "duration_ms": round((time.perf_counter() - started) * 1000, 3),
            "stdout": _redact((exc.stdout or "")[-12000:]),
            "stderr": _redact((exc.stderr or "")[-12000:]),
            "error": "timeout",
        }


def _request(url: str) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        with urlopen(url, timeout=10) as response:  # noqa: S310 - loopback URL built below
            body = response.read().decode("utf-8")
            return {
                "url": url,
                "status_code": response.status,
                "body": json.loads(body),
                "duration_ms": round((time.perf_counter() - started) * 1000, 3),
            }
    except HTTPError as exc:
        return {
            "url": url,
            "status_code": exc.code,
            "body": json.loads(exc.read().decode("utf-8")),
            "duration_ms": round((time.perf_counter() - started) * 1000, 3),
        }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _native_lens_payload(records: list[dict[str, Any]]) -> dict[str, Any]:
    traces = []
    for record in records:
        trace_id = record["trace_id"]
        span_id = trace_id[:16]
        status = "error" if record["status_code"] >= 500 else "ok"
        span = {
            "schema_version": "1.0.0",
            "trace_id": trace_id,
            "span_id": span_id,
            "parent_span_id": None,
            "name": f"HTTP {record['method']} {record['path']}",
            "kind": "tool",
            "start_time": record["started_at"],
            "end_time": record["ended_at"],
            "status": {"code": status, "message": None},
            "attributes": {
                "http.method": record["method"],
                "http.route": record["path"],
                "http.status_code": record["status_code"],
                "http.duration_ms": record["duration_ms"],
            },
            "events": [],
            "links": [],
            "integrity_flags": [],
            "provenance": "observed",
        }
        traces.append(
            {
                "schema_version": "1.0.0",
                "project_id": "cycle-0-5-api-operations",
                "trace_id": trace_id,
                "root_span_id": span_id,
                "started_at": record["started_at"],
                "ended_at": record["ended_at"],
                "status": {"code": status, "message": None},
                "session_id": None,
                "source": {
                    "system": "cycle-0-5-api",
                    "sdk_name": "forge-cycle-0-5-lab",
                    "sdk_version": "1",
                    "host": "127.0.0.1",
                    "language": "python",
                    "runtime": sys.version.split()[0],
                },
                "resource_attributes": {"service.name": "cycle-0-5-api"},
                "spans": [span],
                "provenance": "observed",
            }
        )
    return {
        "project_id": "cycle-0-5-api-operations",
        "schema_version": "1.0.0",
        "sent_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "source": {"system": "cycle-0-5-api"},
        "traces": traces,
    }


def run(*, workspace_root: Path, output: Path) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    commands: list[dict[str, Any]] = []
    checks: list[dict[str, Any]] = []
    env = os.environ.copy()
    env.update({"NO_COLOR": "1", "PYTHONIOENCODING": "utf-8", "FORGE_LAB": "cycle-0.5"})
    with tempfile.TemporaryDirectory(prefix=".forge-cycle-0-5-", dir=workspace_root) as raw_tmp:
        lab = Path(raw_tmp)
        app = lab / "service.py"
        openapi = lab / "openapi.yaml"
        telemetry = lab / "telemetry.jsonl"
        ready = lab / "ready.json"
        sql = lab / "workload.sql"
        for name in ("service.py", "openapi.yaml"):
            shutil.copy2(HERE / name, lab / name)
        sql.write_text(
            "SELECT order_id, customer_id FROM orders WHERE status = 'ready';\n",
            encoding="utf-8",
        )
        server = subprocess.Popen(
            [
                sys.executable,
                str(app),
                "--port",
                "0",
                "--telemetry",
                str(telemetry),
                "--ready-file",
                str(ready),
            ],
            cwd=lab,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            deadline = time.time() + 10
            while time.time() < deadline and not ready.exists():
                time.sleep(0.05)
            if not ready.exists():
                raise RuntimeError("local API did not publish its ready file")
            endpoint = json.loads(ready.read_text(encoding="utf-8"))
            base = f"http://{endpoint['host']}:{endpoint['port']}"
            requests = [
                _request(f"{base}/health"),
                _request(f"{base}/items"),
                _request(f"{base}/degraded?latency_ms=40"),
            ]
        finally:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=5)

        records = [json.loads(line) for line in telemetry.read_text(encoding="utf-8").splitlines()]
        checks.append(
            {
                "id": "HTTP_REAL",
                "status": "PASSED"
                if [r["status_code"] for r in requests] == [200, 200, 503]
                else "FAILED",
                "detail": requests,
            }
        )
        checks.append(
            {
                "id": "DEGRADATION_REAL",
                "status": "PASSED"
                if any(
                    r["path"] == "/degraded" and r["status_code"] == 503 and r["duration_ms"] >= 35
                    for r in records
                )
                else "FAILED",
                "detail": "controlled latency and 503 were observed",
            }
        )
        checks.append(
            {
                "id": "TELEMETRY_REAL",
                "status": "PASSED"
                if len(records) == 3 and all(r.get("trace_id") for r in records)
                else "FAILED",
                "detail": f"{len(records)} JSONL observations",
            }
        )

        lens_payload = lab / "lens-native.json"
        lens_payload.write_text(
            json.dumps(_native_lens_payload(records), indent=2) + "\n", encoding="utf-8"
        )
        lens_db = lab / "forge-lens.db"
        data_out = lab / "data-sentinel-report.json"
        commands.append(
            _run(
                [
                    "uv",
                    "run",
                    "--project",
                    str(workspace_root / "forge-doctor-api"),
                    "forge-doctor-api",
                    "contract",
                    "inspect",
                    str(openapi),
                    "--json",
                ],
                cwd=workspace_root,
                env=env,
            )
        )
        commands.append(
            _run(
                [
                    "uv",
                    "run",
                    "--project",
                    str(workspace_root / "code-atlas-forge"),
                    "code-atlas",
                    "index",
                    str(lab),
                    "--json",
                ],
                cwd=workspace_root,
                env=env,
            )
        )
        commands.append(
            _run(
                [
                    "uv",
                    "run",
                    "--project",
                    str(workspace_root / "data-sentinel-forge"),
                    "data-sentinel",
                    "analyze",
                    "--file",
                    str(telemetry),
                    "--platform",
                    "generic",
                    "--json",
                    "--no-persist",
                    "--output",
                    str(data_out),
                ],
                cwd=workspace_root,
                env=env,
            )
        )
        commands.append(
            _run(
                [
                    "uv",
                    "run",
                    "--project",
                    str(workspace_root / "forge-lens"),
                    "forge-lens",
                    "ingest",
                    str(lens_payload),
                    "--db",
                    str(lens_db),
                    "--project",
                    "cycle-0-5-api-operations",
                ],
                cwd=workspace_root,
                env=env,
            )
        )
        commands.append(
            _run(
                ["uv", "run", "forge", "doctor", "--root", str(workspace_root), "--json"],
                cwd=workspace_root / "the-forge",
                env=env,
            )
        )
        specialists_command = _run(
            [
                "uv",
                "run",
                "forge",
                "specialists",
                "list",
                "--root",
                str(workspace_root),
                "--json",
                "--no-probe",
            ],
            cwd=workspace_root / "the-forge",
            env=env,
        )
        commands.append(specialists_command)
        roster_status = "FAILED"
        roster_detail: dict[str, Any] | str
        try:
            # The CLI receipt deliberately bounds stdout for storage.  Use the
            # same real collector in-process for the structured roster gate so
            # a large catalog cannot make JSON validation depend on a log tail.
            from theforge.specialists import collect, to_rows

            entries = to_rows(collect(workspace_root=workspace_root, probe_cli=False))
            nonconformant = [
                entry.get("provider", "?")
                for entry in entries
                if (entry.get("agent_roster") or {}).get("state") != "CONFORMANT"
                or not (entry.get("agent_roster") or {}).get("routable", False)
            ]
            roster_status = (
                "PASSED"
                if specialists_command["status"] == "PASSED" and entries and not nonconformant
                else "FAILED"
            )
            roster_detail = {
                "catalog_entries": len(entries),
                "nonconformant": nonconformant,
            }
        except (TypeError, AttributeError, OSError, ValueError) as exc:
            roster_detail = f"catalog parse failed: {exc}"
        checks.append(
            {
                "id": "SPECIALIST_ROSTER",
                "status": roster_status,
                "detail": roster_detail,
            }
        )
        bridge_command = _run(
            [
                "uv",
                "run",
                "--project",
                str(workspace_root / "forge-agent-bridge"),
                "forge-bridge",
                "status",
            ],
            cwd=workspace_root,
            env=env,
        )
        commands.append(bridge_command)

        for item in commands[:4]:
            checks.append(
                {
                    "id": item["argv"][4] if len(item["argv"]) > 4 else item["argv"][0],
                    "status": item["status"],
                    "detail": item["returncode"],
                }
            )
        agent_status = "UNAVAILABLE"
        agent_detail: str = "provider inventory recorded; no session was fabricated"
        try:
            bridge_status = json.loads(bridge_command.get("stdout", ""))
            authenticated = [
                item.get("id", "?")
                for item in bridge_status.get("providers", [])
                if item.get("installed") and item.get("auth_state") == "authenticated"
            ]
            if authenticated:
                agent_status = "NOT_RUN"
                agent_detail = (
                    "authenticated provider(s) detected, but this deterministic lab "
                    f"did not invoke a session: {authenticated}"
                )
        except (json.JSONDecodeError, TypeError, AttributeError):
            if bridge_command["status"] != "PASSED":
                agent_status = "BLOCKED"
                agent_detail = "provider inventory command failed"
        checks.append(
            {
                "id": "AGENT_PROVIDER",
                "status": agent_status,
                "detail": agent_detail,
            }
        )
        checks.append(
            {
                "id": "PORTAL",
                "status": "SURFACE_ONLY",
                "detail": (
                    "PortalApi/1 and visual gates are validated by forge-portal "
                    "suites, not by a live API in this isolated lab"
                ),
            }
        )

        artifacts = {}
        for path in (openapi, telemetry, lens_payload, lens_db, data_out):
            if path.exists():
                target = output / path.name
                shutil.copy2(path, target)
                artifacts[path.name] = {
                    "path": str(target),
                    "sha256": _sha256(target),
                    "bytes": target.stat().st_size,
                }
        receipt = {
            "schema": "forge/Cycle05E2EReceipt/v1",
            "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "workspace_root": str(workspace_root),
            "status": "PASS_WITH_LIMITATIONS"
            if all(
                c["status"] in {"PASSED", "UNAVAILABLE", "NOT_RUN", "SURFACE_ONLY"} for c in checks
            )
            else "FAILED",
            "checks": checks,
            "commands": commands,
            "artifacts": artifacts,
            "limitations": [
                "Agent Bridge provider session was not created because "
                "availability is environment-dependent.",
                "Portal was validated as a surface; no fake live Portal backend was introduced.",
                "The specialist catalog proves roster conformance and routing "
                "evidence only; it does not prove live specialist execution.",
            ],
        }
    receipt_path = output / "cycle-0.5-api-operations-receipt.json"
    receipt_path.write_text(
        json.dumps(receipt, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace-root", type=Path, default=REPO_ROOT.parent)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    receipt = run(workspace_root=args.workspace_root.resolve(), output=args.output.resolve())
    print(
        json.dumps(
            {
                "status": receipt["status"],
                "receipt": str(args.output / "cycle-0.5-api-operations-receipt.json"),
            }
        )
    )
    return 0 if receipt["status"] == "PASS_WITH_LIMITATIONS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
