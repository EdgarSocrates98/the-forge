"""Manifest rules: SemVer 2.0.0 provider version (req 4.4)."""

import pytest

from theforge.contracts.codes import Codes
from theforge.contracts.semver import SemVer, parse_semver


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("0.1.0", SemVer(major=0, minor=1, patch=0)),
        ("1.2.3", SemVer(major=1, minor=2, patch=3)),
        (
            "1.2.3-rc.1+build.5",
            SemVer(major=1, minor=2, patch=3, prerelease=("rc", "1"), build=("build", "5")),
        ),
        ("1.0.0-alpha", SemVer(major=1, minor=0, patch=0, prerelease=("alpha",))),
        (
            "1.0.0-0.3.7",
            SemVer(major=1, minor=0, patch=0, prerelease=("0", "3", "7")),
        ),
        (
            "1.0.0-x-y-z.--",
            SemVer(major=1, minor=0, patch=0, prerelease=("x-y-z", "--")),
        ),
        ("1.0.0-0a", SemVer(major=1, minor=0, patch=0, prerelease=("0a",))),
        ("1.0.0+001", SemVer(major=1, minor=0, patch=0, build=("001",))),
        (
            "1.0.0+20130313144700.sha-5114f85",
            SemVer(major=1, minor=0, patch=0, build=("20130313144700", "sha-5114f85")),
        ),
        ("10.20.30", SemVer(major=10, minor=20, patch=30)),
        (
            "99999999999999999999.0.0",
            SemVer(major=99999999999999999999, minor=0, patch=0),
        ),
    ],
)
def test_parse_semver_accepts_valid_versions(text: str, expected: SemVer) -> None:
    assert parse_semver(text) == expected


@pytest.mark.parametrize(
    "value",
    [
        "1.0",
        "1",
        "",
        "v1.2.3",
        "V1.2.3",
        "01.2.3",
        "1.02.3",
        "1.2.03",
        "1.2.3-01",  # numeric pre-release identifier with leading zero
        "1.2.3-",
        "1.2.3+",
        "1.2.3-rc..1",
        "1.2.3+build..5",
        "1.2.3-rc_1",
        "1.2.3.4",
        " 1.2.3",
        "1.2.3 ",
        "1.2.3\n",
        "-1.2.3",
        "1.2.3-ré",
        "١.2.3",  # ARABIC-INDIC DIGIT ONE: non-ASCII digit
        "1.２.3",  # FULLWIDTH DIGIT TWO
        "1.2.3+٣",
        "1" * 5000 + ".0.0",  # beyond int str-digit limit: malformed, never raises
        None,
        123,
        1.2,
        b"1.2.3",
        ["1", "2", "3"],
        {"version": "1.2.3"},
    ],
)
def test_parse_semver_rejects_malformed_without_raising(value: object) -> None:
    assert parse_semver(value) is None


def test_semver_is_frozen() -> None:
    version = SemVer(major=1, minor=2, patch=3)
    with pytest.raises(AttributeError):
        version.major = 2  # type: ignore[misc]


def test_manifest_rule_codes_are_registered() -> None:
    assert Codes.MANIFEST_VERSION == "FORGE-MANIFEST-VERSION"
    assert Codes.MANIFEST_TAXONOMY == "FORGE-MANIFEST-TAXONOMY"
