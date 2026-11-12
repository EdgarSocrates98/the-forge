"""Controlled Phase 2 cross-Forge Obsidian E2E.

This runner deliberately uses local fixture adapters and a temporary vault. It
is not a cloud homologation claim. Run it from the FORJAS checkout:

    python the-forge/scripts/phase2_federated_obsidian_e2e.py \
      --repos-root E:/projetos/FORJAS

The result is JSON on stdout and no repository or real vault is modified.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


def _add_repo_paths(repos_root: Path) -> None:
    neutral_obsidian = repos_root / "product-forge" / "forge-obsidian" / "src"
    if neutral_obsidian.is_dir():
        sys.path.insert(0, str(neutral_obsidian))
    for repo in (
        "product-forge",
        "spark-forge-aws",
        "spark-forge-azure",
        "api-forge",
        "platform-forge",
        "code-atlas-forge",
        "forge-lens",
        "forge-agent-bridge",
    ):
        root = repos_root / repo
        path = root / "src" if (root / "src").is_dir() else root
        if path.is_dir():
            sys.path.insert(0, str(path))


def _with_link(note: dict[str, Any], target: str) -> dict[str, Any]:
    content = str(note["content"]).rstrip() + f"\n\nSee [[{target}]].\n"
    return {
        **note,
        "content": content,
        "content_hash": hashlib.sha256(content.encode("utf-8")).hexdigest(),
    }


def run(repos_root: Path) -> dict[str, Any]:
    _add_repo_paths(repos_root)
    from apiforge.context.obsidian import build_obsidian_contract_review
    from code_atlas.context.obsidian import project_obsidian_relations  # type: ignore[import-not-found]
    from forge_agent_bridge.context import (  # type: ignore[import-not-found]
        ContextStore,
        KnowledgeContextPack,
        ProductAgentSessionContext,
    )
    from forge_lens.adapters.obsidian import trace_from_obsidian_receipt  # type: ignore[import-not-found]
    from forge_obsidian import (  # type: ignore[import-not-found]
        ObsidianVaultError,
        export_vault_document,
        import_vault_document,
        parse_markdown_document,
        plan_vault_sync,
    )
    from platformforge.context.obsidian import build_obsidian_operations_review
    from sparkforge_aws.context.obsidian import build_obsidian_diagnostic
    from sparkforge_azure.context.obsidian import build_obsidian_diagnostic as build_azure_note

    with tempfile.TemporaryDirectory(prefix="forge-phase2-e2e-") as temp:
        vault = Path(temp) / "authorized-vault"
        vault.mkdir()
        workspace = "ws-phase2-fixture"
        vault_id = "vault-phase2-fixture"

        notes = [
            build_obsidian_diagnostic(
                title="Spark skew fixture",
                summary="Fixture evidence for a Spark diagnostic.",
                workspace=workspace,
                vault_id=vault_id,
                findings=[{"severity": "warning", "message": "skew observed"}],
                evidence=[{"source": "fixture", "id": "aws-evidence-1"}],
                note_path="aws/spark-diagnostic.md",
            ),
            build_azure_note(
                title="Azure permission fixture",
                summary="Fixture evidence for a permission investigation.",
                workspace=workspace,
                vault_id=vault_id,
                permissions=[{"principal": "fixture", "result": "denied"}],
                freshness="fresh",
                note_path="azure/permission-investigation.md",
            ),
            build_obsidian_contract_review(
                title="API contract fixture",
                summary="Fixture breaking-change review.",
                workspace=workspace,
                vault_id=vault_id,
                endpoints=[{"method": "GET", "path": "/v1/orders"}],
                breaking_changes=[{"kind": "response", "severity": "high"}],
                note_path="api/contract-review.md",
            ),
            build_obsidian_operations_review(
                title="Platform incident fixture",
                summary="Fixture Kubernetes finding and proposed runbook.",
                workspace=workspace,
                vault_id=vault_id,
                incident={"cluster": "fixture", "state": "investigating"},
                runbooks=[{"state": "draft", "title": "Pod recovery"}],
                note_path="platform/incident-review.md",
            ),
        ]
        notes[0] = _with_link(notes[0], "api/contract-review")
        notes[2] = _with_link(notes[2], "platform/incident-review")
        note_validator = Draft202012Validator(
            json.loads(
                (repos_root / "the-forge" / "schemas" / "ObsidianNoteRef.schema.json").read_text(
                    encoding="utf-8"
                )
            )
        )
        for note in notes:
            public_note = {key: value for key, value in note.items() if key != "content"}
            errors = sorted(
                note_validator.iter_errors(public_note),
                key=lambda error: list(error.path),
            )
            assert not errors, "; ".join(error.message for error in errors)
        for note in notes:
            (vault / str(note["path"])).parent.mkdir(parents=True, exist_ok=True)

        receipts = [
            export_vault_document(
                vault,
                str(note["path"]),
                str(note["content"]),
                classification=str(note.get("classification") or "internal"),
                source=str(note["source"]),
            )
            for note in notes
        ]
        imported = [import_vault_document(vault, str(note["path"])) for note in notes]
        assert all(
            item["content"] == note["content"] for item, note in zip(imported, notes, strict=True)
        )
        assert all(item["content_hash"] for item in imported)

        parsed = parse_markdown_document(imported[0]["content"])
        note_ref = {
            "schema": "theforge/ObsidianNoteRef/v1",
            "version": "v1",
            "workspace": workspace,
            "vault_id": vault_id,
            "path": imported[0]["path"],
            "source": imported[0]["provenance"]["adapter"],
            "classification": "internal",
            "content_hash": imported[0]["content_hash"],
            "wikilinks": parsed["wikilinks"],
            "relative_links": parsed["relative_links"],
            "attachments": parsed["attachments"],
        }
        atlas = project_obsidian_relations(note_ref)
        assert atlas["body_included"] is False
        assert atlas["relations"]

        lens = trace_from_obsidian_receipt(receipts[0], project_id="phase2-fixture")
        assert lens.provenance.value == "imported"
        assert "content" not in lens.spans[0].attributes

        source_id = f"obsidian:{vault_id}:{imported[0]['path']}"
        bridge_state = Path(temp) / "bridge-state"
        bridge_state.mkdir()
        bridge = ContextStore(path=bridge_state)
        bridge.bind(
            "session-phase2",
            ProductAgentSessionContext(
                identity="fixture-agent",
                workspace_id=workspace,
                allowed_knowledge_sources=[source_id],
            ),
        )
        pack = KnowledgeContextPack(
            pack_id="phase2-pack",
            workspace_id=workspace,
            principal="fixture-agent",
            source_versions={source_id: imported[0]["content_hash"]},
            selected_items=["obsidian-note-1"],
            items=[
                {
                    "item_id": "obsidian-note-1",
                    "source_id": source_id,
                    "document_id": imported[0]["path"],
                    "workspace_id": workspace,
                    "version": imported[0]["content_hash"],
                }
            ],
        )
        assert bridge.authorize_knowledge_pack("session-phase2", pack).pack_id == "phase2-pack"

        conflict_path = "conflicts/manual.md"
        (vault / "conflicts").mkdir()
        export_vault_document(vault, conflict_path, "# Baseline\n")
        conflict_plan = plan_vault_sync(vault, conflict_path, "# Candidate\n")
        (vault / conflict_path).write_text("# Manual edit\n", encoding="utf-8")
        conflict_detected = False
        try:
            export_vault_document(
                vault,
                conflict_path,
                "# Candidate\n",
                baseline_hash=conflict_plan["previous_hash"],
            )
        except ObsidianVaultError as exc:
            conflict_detected = exc.code == "OBSIDIAN-CONFLICT"
        assert conflict_detected

        return {
            "schema": "theforge/Phase2FederatedObsidianE2E/v1",
            "fixture_only": True,
            "notes_exported": len(receipts),
            "notes_roundtripped": len(imported),
            "note_contracts_validated": len(notes),
            "atlas_relations": len(atlas["relations"]),
            "lens_spans": len(lens.spans),
            "bridge_authorized": True,
            "manual_conflict_detected": conflict_detected,
            "cloud_access": False,
            "body_persisted_in_federation_outputs": False,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repos-root", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.repos_root.resolve()), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
