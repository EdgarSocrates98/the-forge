"""Protocol version negotiation: highest common major wins."""

import re

SUPPORTED_PROTOCOLS: tuple[str, ...] = ("forge/v1",)
_PROTOCOL = re.compile(r"^forge/v(\d+)$")


def major(protocol: str) -> int | None:
    match = _PROTOCOL.match(protocol)
    return int(match.group(1)) if match else None


def choose_protocol(
    offered: list[str], supported: tuple[str, ...] = SUPPORTED_PROTOCOLS
) -> str | None:
    ours = {m: p for p in supported if (m := major(p)) is not None}
    theirs = {m for p in offered if (m := major(p)) is not None}
    common = sorted(theirs & ours.keys())
    return ours[common[-1]] if common else None
