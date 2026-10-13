"""Local, observable identity of a provider: resolved executable plus argv file stats.

Limitation (ADR 0013): code imported by modules (``-m pkg``) is not covered; the pre-execute
revalidation compensates for the selected provider.
"""

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from theforge.contracts.canonical import sha256_of
from theforge.registry.config import ProviderEntry


@dataclass(frozen=True, kw_only=True)
class ProviderFingerprint:
    executable: str
    file_stats: list[tuple[str, int, int]]
    digest: str


def _stat(arg: str) -> tuple[str, int, int] | None:
    try:
        if not Path(arg).is_file():
            return None
        st = os.stat(arg)
    except (OSError, ValueError):
        return None
    return (arg, st.st_size, st.st_mtime_ns)


def fingerprint(entry: ProviderEntry) -> ProviderFingerprint:
    executable = shutil.which(entry.argv[0]) or entry.argv[0]
    stats = [s for s in (_stat(a) for a in [executable, *entry.argv[1:]]) if s is not None]
    digest = sha256_of({"executable": executable, "file_stats": [list(s) for s in stats]})
    return ProviderFingerprint(executable=executable, file_stats=stats, digest=digest)
