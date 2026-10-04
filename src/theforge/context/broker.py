"""Context Broker: provider-specific ContextPack by reference + hash, within budget."""

from collections.abc import Mapping
from pathlib import PurePosixPath
from types import MappingProxyType
from typing import Final

from theforge.context.scan import WorkspaceScan
from theforge.contracts import ContextFile, ContextPack, ExcludedFile, TaskSpec
from theforge.contracts.canonical import sha256_hex, utc_now
from theforge.meta import PRODUCER
from theforge.profiles import PROFILES
from theforge.security.paths import resolve_inside

# Derived from the profiles table (compat name used by callers and tests).
BUDGETS: Final[Mapping[str, int]] = MappingProxyType(
    {name: profile.budget_bytes for name, profile in PROFILES.items()}
)


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
        resolved = resolve_inside(scan.root, path)
        if resolved is None:
            excluded.append(ExcludedFile(path=rel, reason="outside_root"))
            continue
        remaining = budget - used
        try:
            if path.stat().st_size > remaining:
                excluded.append(ExcludedFile(path=rel, reason="budget"))
                truncated = True
                continue
            with resolved.open("rb") as fh:
                data = fh.read(remaining + 1)
        except OSError:
            excluded.append(ExcludedFile(path=rel, reason="unreadable"))
            continue
        if len(data) > remaining:
            excluded.append(ExcludedFile(path=rel, reason="budget"))
            truncated = True
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
