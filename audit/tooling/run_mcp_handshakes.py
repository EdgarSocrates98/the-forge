"""Bounded real MCP initialize/list/call probes for Forge products."""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import queue
import shutil
import subprocess
import threading
import time
from pathlib import Path

PREFIX_BY_REPO = {
    "spark-forge-aws": "SPARK_FORGE_AWS",
    "spark-forge-azure": "SPARK_FORGE_AZURE",
    "api-forge": "API_FORGE",
    "platform-forge": "PLATFORM_FORGE",
    "forge-doctor-api": "FORGE_DOCTOR_API",
    "forge-doctor-data": "FORGE_DOCTOR_DATA",
}

# Prefer bounded, read-only probes over a full project scan. A no-argument
# schema does not imply cheap execution: Doctor's first tool is an analysis
# scan and can exceed the handshake budget on a large checkout.
PREFERRED_PROBES = {
    "forge-doctor-api": [("doctor.get_contract", {})],
    "forge-doctor-data": [("diagnose_log", {"text": ""})],
}


def _read_env(name: str) -> str | None:
    value = os.environ.get(name)
    if value:
        return value
    if os.name != "nt":
        return None
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            return str(winreg.QueryValueEx(key, name)[0])
    except OSError:
        return None


def _command(repo: str, declared: list[str], root: Path | None = None) -> list[str]:
    prefix = PREFIX_BY_REPO.get(repo)
    cli = _read_env(f"{prefix}_CLI") if prefix else None
    if cli:
        first = Path(cli).parent / f"{declared[0]}.exe"
        if first.is_file():
            return [str(first), *declared[1:]]
    if root is not None and shutil.which(declared[0]) is None:
        venv_bin = root / ".venv" / "bin" / declared[0]
        if venv_bin.is_file():
            return [str(venv_bin), *declared[1:]]
    return declared


def _reader(stream, out: queue.Queue[str]) -> None:
    try:
        for line in stream:
            out.put(line)
    finally:
        out.put("")


def _next_json(out: queue.Queue[str], deadline: float) -> dict:
    while time.monotonic() < deadline:
        try:
            line = out.get(timeout=max(0.01, deadline - time.monotonic()))
        except queue.Empty as exc:
            raise TimeoutError("no JSON-RPC response before timeout") from exc
        if not line:
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    raise TimeoutError("no JSON-RPC response before timeout")


def probe(repo: str, root: Path, declared: list[str], timeout: float) -> dict:
    command = _command(repo, declared, root)
    result: dict[str, object] = {"repo": repo, "command": command}
    process = subprocess.Popen(
        command,
        cwd=root,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    output: queue.Queue[str] = queue.Queue()
    threading.Thread(target=_reader, args=(process.stdout, output), daemon=True).start()

    def send(message: dict) -> dict:
        assert process.stdin is not None
        process.stdin.write(json.dumps(message) + "\n")
        process.stdin.flush()
        return _next_json(output, time.monotonic() + timeout)

    def notify(message: dict) -> None:
        assert process.stdin is not None
        process.stdin.write(json.dumps(message) + "\n")
        process.stdin.flush()

    phase = "initialize"
    try:
        init = send(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "forge-e2e-audit", "version": "1"},
                },
            }
        )
        result["initialize"] = "PASS" if "result" in init else "FAIL"
        notify({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})
        phase = "tools_list"
        listed = send({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        tools = (
            ((listed.get("result") or {}).get("tools") or []) if isinstance(listed, dict) else []
        )
        result["tools_list"] = "PASS" if "result" in listed and isinstance(tools, list) else "FAIL"
        result["tool_count"] = len(tools)
        if tools:
            available = {tool.get("name"): tool for tool in tools}
            candidate = None
            arguments: dict[str, object] = {}
            for preferred_name, preferred_args in PREFERRED_PROBES.get(repo, []):
                if preferred_name in available:
                    candidate = available[preferred_name]
                    arguments = preferred_args
                    break
            if candidate is None:
                candidate = next(
                    (
                        tool
                        for tool in tools
                        if not ((tool.get("inputSchema") or {}).get("required") or [])
                    ),
                    tools[0],
                )
            name = candidate.get("name")
            phase = "tools_call"
            called = send(
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {"name": name, "arguments": arguments},
                }
            )
            result["invoked_tool"] = name
            result["tools_call"] = "PASS" if "result" in called else "FAIL"
        else:
            result["tools_call"] = "UNVERIFIED"
    except (OSError, TimeoutError, AssertionError) as exc:
        result["error"] = str(exc)
        result.setdefault(phase, "BLOCKED")
    finally:
        with contextlib.suppress(OSError):
            process.kill()
        process.wait(timeout=2)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=8.0)
    args = parser.parse_args()
    results = []
    for repo, _prefix in PREFIX_BY_REPO.items():
        root = args.workspace_root / repo
        manifest = root / "forge.json"
        if not manifest.is_file():
            results.append({"repo": repo, "status": "NOT_APPLICABLE"})
            continue
        data = json.loads(manifest.read_text(encoding="utf-8"))
        declared = data.get("mcp_command") or []
        if isinstance(declared, str):
            declared = declared.split()
        if not declared:
            results.append({"repo": repo, "status": "NOT_APPLICABLE"})
            continue
        try:
            result = probe(repo, root, list(declared), args.timeout)
            if result.get("initialize") != "PASS" or result.get("tools_list") != "PASS":
                result["status"] = "FAIL"
            elif result.get("tool_count", 0) and result.get("tools_call") != "PASS":
                result["status"] = "BLOCKED" if result.get("tools_call") == "BLOCKED" else "FAIL"
            else:
                result["status"] = "PASS"
        except FileNotFoundError as exc:
            result = {"repo": repo, "status": "BLOCKED", "error": str(exc)}
        results.append(result)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps({"schema": "forge/mcp-handshake/v1", "results": results}, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(results, indent=2))
    return (
        0 if all(item["status"] in {"PASS", "NOT_APPLICABLE", "BLOCKED"} for item in results) else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
