"""Protocol version negotiation: highest common major wins.

Offered lists come from untrusted providers: malformed entries (wrong case,
whitespace, leading zeros, non-ASCII digits, non-strings) are ignored, duplicates
collapse and the result does not depend on order. No common major -> ``None``.
"""

import re
from collections.abc import Iterable

SUPPORTED_PROTOCOLS: tuple[str, ...] = ("forge/v1",)
_PROTOCOL = re.compile(r"forge/v([1-9][0-9]{0,2})", re.ASCII)


def major(protocol: str) -> int | None:
    if not isinstance(protocol, str):
        return None
    match = _PROTOCOL.fullmatch(protocol)
    return int(match.group(1)) if match else None


def _majors(protocols: Iterable[object]) -> dict[int, str]:
    found: dict[int, str] = {}
    for p in protocols:
        if isinstance(p, str) and (m := major(p)) is not None:
            found.setdefault(m, p)
    return found


def choose_protocol(
    offered: list[str], supported: tuple[str, ...] = SUPPORTED_PROTOCOLS
) -> str | None:
    if not isinstance(offered, (list, tuple)):
        return None
    ours = _majors(supported)
    common = _majors(offered).keys() & ours.keys()
    return ours[max(common)] if common else None
