"""Contract and security gates for Knowledge Interoperability v1."""

from dataclasses import asdict

import pytest

from theforge.contracts import (
    ContractError,
    KnowledgeContextPack,
    KnowledgeDocument,
    KnowledgeRelation,
    KnowledgeSource,
    from_dict,
    knowledge_canonical_json,
)


def test_source_rejects_embedded_secret() -> None:
    with pytest.raises(ContractError, match="reference a secret"):
        KnowledgeSource(
            source_id="src-1",
            source_type="markdown",
            locator="file:///tmp/notes.md",
            workspace_id="ws-1",
            auth_ref="token=do-not-store",
        )


def test_document_roundtrip_is_deterministic() -> None:
    document = KnowledgeDocument(
        document_id="doc-1",
        source_id="src-1",
        workspace_id="ws-1",
        title="Runbook",
        content_type="text/markdown",
        original_artifact_ref="artifact://original/doc-1",
        normalized_artifact_ref="artifact://normalized/doc-1",
        content_hash="sha256:abc",
        version="1",
        classification="internal",
        trust_state="observed",
        created_at="2026-11-07T00:00:00Z",
        updated_at="2026-11-07T00:00:00Z",
    )
    restored = from_dict(KnowledgeDocument, asdict(document), strict=True)
    assert restored == document
    assert knowledge_canonical_json(document) == knowledge_canonical_json(restored)


def test_context_pack_rejects_unauthorized_items() -> None:
    pack = KnowledgeContextPack(
        pack_id="pack-1",
        query="how do I deploy?",
        workspace_id="ws-1",
        principal="agent-1",
        selected_items=["doc-allowed", "doc-secret"],
    )
    with pytest.raises(ContractError, match="unauthorized"):
        pack.ensure_authorized({"doc-allowed"})


def test_over_budget_pack_requires_explicit_truncation() -> None:
    with pytest.raises(ContractError, match="truncations"):
        KnowledgeContextPack(
            pack_id="pack-1",
            query="q",
            workspace_id="ws-1",
            principal="agent-1",
            estimated_tokens=101,
            budget_tokens=100,
        )


def test_relation_requires_declared_semantics() -> None:
    with pytest.raises(ContractError, match="semantics is required"):
        KnowledgeRelation(
            relation_id="rel-1",
            relation_type="related_to",
            source_id="src-1",
            from_ref="doc-1",
            to_ref="doc-2",
            semantics="",
        )
