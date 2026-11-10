from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from theforge.contracts import (
    ContractError,
    ObsidianExportRequest,
    ObsidianNoteDraft,
)

ROOT = Path(__file__).parents[1]


def test_note_draft_validates_and_projects_to_body_free_ref():
    body = "---\ntitle: Safe\n---\n# Safe\n"
    draft = ObsidianNoteDraft(
        workspace="ws",
        vault_id="vault",
        path="notes/safe.md",
        source="fixture-adapter",
        content=body,
        content_hash=hashlib.sha256(body.encode()).hexdigest(),
        provenance={"adapter": "fixture-adapter", "source_version": "v1"},
    )
    payload = {
        **draft.__dict__,
        "provenance": dict(draft.provenance),
        "warnings": list(draft.warnings),
        "unresolved": list(draft.unresolved),
    }
    schema = json.loads((ROOT / "schemas/ObsidianNoteDraft.schema.json").read_text())
    Draft202012Validator(schema).validate(payload)
    ref = draft.note_ref()
    assert "content" not in ref.__dict__
    ref_schema = json.loads((ROOT / "schemas/ObsidianNoteRef.schema.json").read_text())
    Draft202012Validator(ref_schema).validate(ref.__dict__)


def test_note_draft_rejects_hash_mismatch_and_traversal():
    with pytest.raises(ContractError):
        ObsidianNoteDraft(
            workspace="ws", vault_id="vault", path="../secret.md",
            source="fixture", content="body", content_hash="0" * 64,
        )


def test_export_request_is_body_free_and_idempotent():
    request = ObsidianExportRequest(
        workspace="ws", vault_id="vault", path="notes/safe.md",
        source="fixture-adapter", idempotency_key="run-1",
        operation="reviewed_sync", approval_ref="approval-1",
    )
    assert "content" not in request.__dict__
    schema = json.loads((ROOT / "schemas/ObsidianExportRequest.schema.json").read_text())
    Draft202012Validator(schema).validate(request.__dict__)
