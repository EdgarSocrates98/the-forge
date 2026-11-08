"""Run the Phase 1 knowledge path across the four owning repositories.

This is intentionally a process-level smoke, not a shared-import unit test:
each step runs in the specialist repository's own virtual environment and
communicates only through the versioned JSON envelope.  The path is:

Product Forge Markdown chunk -> Code Atlas KnowledgeContextPack ->
Agent Bridge re-authorization -> Forge Lens redacted provenance.

No network, cloud credentials or repository writes are used.  The receipt is
safe to attach to an audit because it contains counts and hashes, not document
bodies.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent


def _python(repo: str) -> Path:
    candidates = (
        WORKSPACE / repo / ".venv" / "Scripts" / "python.exe",
        WORKSPACE / repo / ".venv" / "bin" / "python",
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise RuntimeError(f"{repo}: virtual environment not found")


def _run(repo: str, code: str, payload: dict[str, Any], *, timeout: int = 60) -> dict[str, Any]:
    proc = subprocess.run(
        [_python(repo), "-c", code],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=WORKSPACE / repo,
        timeout=timeout,
        check=False,
    )
    if proc.returncode:
        detail = (proc.stderr or proc.stdout).strip()[-1200:]
        raise RuntimeError(f"{repo}: subprocess exited {proc.returncode}: {detail}")
    try:
        value = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{repo}: subprocess did not emit JSON: {proc.stdout[-1200:]}") from exc
    if not isinstance(value, dict):
        raise RuntimeError(f"{repo}: subprocess emitted a non-object envelope")
    return value


PRODUCT_CODE = r"""
import json, sys
from dataclasses import asdict
from product_forge.knowledge.ingest import chunk_markdown

request = json.load(sys.stdin)
chunks = chunk_markdown(request["markdown"])
print(json.dumps({"chunks": [asdict(chunk) for chunk in chunks]}, ensure_ascii=False))
"""

ATLAS_CODE = r"""
import json, sys
from code_atlas.context.contracts import (
    Budget, ContextItem, ContextPack, PackDiagnostics, PackEvidence, PackManifest,
)
from code_atlas.context.knowledge import to_knowledge_context_pack

request = json.load(sys.stdin)
chunk = request["chunk"]
pack = ContextPack(
    manifest=PackManifest(
        schema_version=2, repository="workspace/demo", snapshot_id=7,
        level="focus", estimator="smoke-v1", tokens_estimated=True,
        selected=1, omitted=0, truncated=False, freshness="snapshot:7",
        ranking_explanation="direct source capture",
    ),
    budget=Budget(
        limit=1000, reserved_meta=10, reserved_evidence=10,
        reserved_diagnostics=10, available_items=970, estimator="smoke-v1",
    ),
    items=(ContextItem(
        item_id="source:" + chunk["content_hash"][:16], kind="file",
        priority=1, title="captured markdown", body=chunk["text"],
        est_tokens=chunk["token_estimate"], path="docs/brief.md",
        evidence=(PackEvidence(kind="occurrence", ref="doc:brief.md:0"),),
    ),),
    selected_symbols=(), relevant_files=("docs/brief.md",), dependencies=(),
    unresolved_refs=(), expansion_refs=(), diagnostics=PackDiagnostics(),
)
print(json.dumps(to_knowledge_context_pack(
    pack, query="diagnose the brief", workspace_id="ws-smoke", principal="agent-smoke"
), ensure_ascii=False))
"""

BRIDGE_CODE = r"""
import json, sys, tempfile
from pathlib import Path
from forge_agent_bridge.context import (
    ContextStore, KnowledgeContextPack, ProductAgentSessionContext,
)
from forge_agent_bridge.adapter import BridgeError

pack = KnowledgeContextPack.validate_contract(json.load(sys.stdin))
with tempfile.TemporaryDirectory() as directory:
    store = ContextStore(path=Path(directory))
    store.bind("session-smoke", ProductAgentSessionContext(
        identity="agent-smoke", workspace_id="ws-smoke",
        allowed_knowledge_sources=["workspace/demo"]
    ))
    authorized = store.authorize_knowledge_pack("session-smoke", pack)
    try:
        store.authorize_knowledge_pack(
            "session-smoke", pack.model_copy(update={"workspace_id": "ws-other"}))
    except BridgeError:
        workspace_denied = True
    else:
        workspace_denied = False
    print(json.dumps(
        {"pack": authorized.model_dump(mode="json", by_alias=True),
         "workspace_denied": workspace_denied}, ensure_ascii=False
    ))
"""

LENS_CODE = r"""
import json, sys
from datetime import UTC, datetime
from forge_lens.contracts.v1.trace import Trace
from forge_lens.knowledge import attach_context_pack_provenance

pack = json.load(sys.stdin)
trace = Trace(trace_id="a" * 32, started_at=datetime.now(UTC))
trace = attach_context_pack_provenance(trace, pack, authorized=True)
print(json.dumps({"resource_attributes": trace.resource_attributes}, ensure_ascii=False))
"""


def run() -> dict[str, Any]:
    markdown = "# Spark diagnosis\n\nThe `orders` pipeline has a latency p95 metric.\n"
    product = _run("product-forge", PRODUCT_CODE, {"markdown": markdown})
    chunks = product.get("chunks") or []
    if not chunks:
        raise RuntimeError("Product Forge emitted no Markdown chunks")
    atlas = _run("code-atlas-forge", ATLAS_CODE, {"chunk": chunks[0]})
    if atlas.get("schema") != "theforge/KnowledgeContextPack/v1":
        raise RuntimeError("Code Atlas emitted an unsupported knowledge schema")
    bridge = _run("forge-agent-bridge", BRIDGE_CODE, atlas)
    authorized = bridge.get("pack") or {}
    if bridge.get("workspace_denied") is not True:
        raise RuntimeError("Agent Bridge did not reject a cross-workspace pack")
    lens = _run("forge-lens", LENS_CODE, authorized)
    attrs = lens.get("resource_attributes") or {}
    if attrs.get("knowledge.pack_id") != authorized.get("pack_id"):
        raise RuntimeError("Forge Lens did not preserve the authorized pack id")
    if "Spark diagnosis" in json.dumps(attrs):
        raise RuntimeError("Forge Lens telemetry leaked document content")
    return {
        "schema": "forge/phase1-knowledge-interop-smoke/v1",
        "status": "PASS",
        "stages": ["product-forge", "code-atlas-forge", "forge-agent-bridge", "forge-lens"],
        "knowledge_schema": atlas["schema"],
        "chunk_count": len(chunks),
        "pack_id": authorized["pack_id"],
        "selected_items": len(authorized.get("selected_items") or []),
        "evidence_ids": len(authorized.get("evidence_ids") or []),
        "telemetry_attribute_count": len(attrs),
        "body_leakage": False,
        "content_sha256": hashlib.sha256(markdown.encode("utf-8")).hexdigest(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, help="write the JSON receipt to this path")
    args = parser.parse_args()
    try:
        receipt = run()
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        receipt = {
            "schema": "forge/phase1-knowledge-interop-smoke/v1",
            "status": "BLOCKED",
            "detail": str(exc),
        }
    text = json.dumps(receipt, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if receipt["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
