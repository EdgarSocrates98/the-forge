"""Tiny local HTTP service used by the Cycle 0.5 E2E lab.

The service deliberately uses only the Python standard library.  It emits one
bounded JSONL span-like record per real HTTP request so the lab can prove that
telemetry came from execution rather than from a fixture pretending to be a
runtime observation.
"""

from __future__ import annotations

import argparse
import json
import time
import uuid
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


class Handler(BaseHTTPRequestHandler):
    server_version = "forge-cycle-0.5-api/1"

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
        started = time.perf_counter()
        started_at = _now()
        trace_id = uuid.uuid4().hex
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        status = 404
        payload: dict[str, Any] = {"error": "not_found"}
        if parsed.path == "/health":
            status = 200
            payload = {"status": "ok", "service": "cycle-0-5-api"}
        elif parsed.path == "/items":
            status = 200
            payload = {"items": [{"id": "order-1", "state": "ready"}]}
        elif parsed.path == "/degraded":
            delay_ms = int(query.get("latency_ms", ["40"])[0])
            time.sleep(max(0, min(delay_ms, 500)) / 1000)
            status = 503
            payload = {"error": "dependency_degraded", "retryable": True}

        body = json.dumps(payload, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Forge-Trace-Id", trace_id)
        self.end_headers()
        self.wfile.write(body)
        self.wfile.flush()
        record = {
            "schema": "forge/Cycle05HttpSpan/v1",
            "trace_id": trace_id,
            "service": "cycle-0-5-api",
            "method": "GET",
            "path": parsed.path,
            "status_code": status,
            "started_at": started_at,
            "ended_at": _now(),
            "duration_ms": round((time.perf_counter() - started) * 1000, 3),
            "dependency": "controlled-lab-latency" if parsed.path == "/degraded" else None,
        }
        telemetry = self.server.telemetry  # type: ignore[attr-defined]
        with telemetry.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--telemetry", type=Path, required=True)
    parser.add_argument("--ready-file", type=Path, required=True)
    args = parser.parse_args()
    args.telemetry.parent.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    server.telemetry = args.telemetry  # type: ignore[attr-defined]
    args.ready_file.write_text(
        json.dumps({"host": "127.0.0.1", "port": server.server_port}),
        encoding="utf-8",
    )
    try:
        server.serve_forever(poll_interval=0.05)
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
