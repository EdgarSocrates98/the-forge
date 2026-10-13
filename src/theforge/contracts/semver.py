"""SemVer 2.0.0 parsing for provider versions (``ForgeManifest.version``).

Pure and total: :func:`parse_semver` never raises and returns ``None`` for anything that is
not exactly a SemVer 2.0.0 string (no leading ``v``, no leading zeros in numeric
identifiers, ASCII only). Version comparison is deliberately absent: specialist version
windows are the adapters' responsibility, not the core's.
"""

import re
from dataclasses import dataclass

_NUM = r"(?:0|[1-9][0-9]*)"
_PRE_ID = r"(?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*)"
_BUILD_ID = r"[0-9A-Za-z-]+"
_SEMVER = re.compile(
    rf"(?P<major>{_NUM})\.(?P<minor>{_NUM})\.(?P<patch>{_NUM})"
    rf"(?:-(?P<pre>{_PRE_ID}(?:\.{_PRE_ID})*))?"
    rf"(?:\+(?P<build>{_BUILD_ID}(?:\.{_BUILD_ID})*))?",
    re.ASCII,
)


@dataclass(frozen=True, kw_only=True)
class SemVer:
    major: int
    minor: int
    patch: int
    prerelease: tuple[str, ...] = ()
    build: tuple[str, ...] = ()


def parse_semver(text: object) -> SemVer | None:
    """Parse a SemVer 2.0.0 string; ``None`` means malformed. Never raises."""
    if type(text) is not str:
        return None
    match = _SEMVER.fullmatch(text)
    if match is None:
        return None
    pre, build = match.group("pre"), match.group("build")
    try:
        return SemVer(
            major=int(match.group("major")),
            minor=int(match.group("minor")),
            patch=int(match.group("patch")),
            prerelease=tuple(pre.split(".")) if pre else (),
            build=tuple(build.split(".")) if build else (),
        )
    except ValueError:  # integer beyond the interpreter's str-digit limit
        return None
