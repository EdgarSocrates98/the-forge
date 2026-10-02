"""Context Broker: provider-specific ContextPack by reference + hash, within budget."""

from pathlib import PurePosixPath

from theforge.context.scan import WorkspaceScan
from theforge.contracts import ContextFile, ContextPack, ExcludedFile, TaskSpec
from theforge.contracts.canonical import sha256_hex, utc_now
from theforge.meta import PRODUCER

BUDGETS: dict[str, int] = {"economy": 64 * 1024, "balanced": 256 * 1024, "max": 1024 * 1024}


def build_context_pack(
    task: TaskSpec, provider_id: str, globs: list[str], scan: WorkspaceScan
) -> ContextPack:
    budget = BUDGETS[task.budget_profile]
    ranked: list[tuple[int, str, list[str]]] = []
    for rel in scan.files:
        hits = [g for g in globs if PurePosixPath(rel).match(g)]
        if hits:
            ranked.append((-len(hits), rel, hits))
    ranked.sort()
    files: list[ContextFile] = []
    excluded = list(scan.excluded)
    used = 0
    truncated = False
    for _, rel, hits in ranked:
        path = scan.root / rel
        try:
            size = path.stat().st_size
            if used + size > budget:
                excluded.append(ExcludedFile(path=rel, reason="budget"))
                truncated = True
                continue
            data = path.read_bytes()
        except OSError:
            excluded.append(ExcludedFile(path=rel, reason="unreadable"))
            continue
        files.append(ContextFile(path=rel, sha256=sha256_hex(data), bytes=len(data),
                                 reason=f"glob:{','.join(hits)}"))
        used += len(data)
    return ContextPack(
        producer=PRODUCER, created_at=utc_now(),
        status="truncated" if truncated else "complete", task_id=task.id,
        provider_id=provider_id, root=str(scan.root), files=files, excluded=excluded,
        budget_bytes=budget, used_bytes=used, truncated=truncated,
    )
