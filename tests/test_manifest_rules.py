"""Manifest rules: SemVer version (4.4); capability aliases and deprecation (5.5, 5.6)."""

import pytest

from theforge.contracts import ContractError, ForgeManifest, from_dict
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


# --- Capability aliases and deprecation (reqs 5.5, 5.6) -------------------------------------

_CAP = {
    "id": "demo.echo", "actions": ["echo"], "default_action": "echo",
    "state": "supported", "operation_class": "read_only",
}


def _cap(cap_id: str, **extra: object) -> dict[str, object]:
    return {**_CAP, "id": cap_id, **extra}


def _manifest(*caps: dict[str, object]) -> ForgeManifest:
    return from_dict(ForgeManifest, {
        "id": "demo-forge", "version": "1.0.0", "protocols": ["forge/v1"],
        "ops": ["describe", "health", "execute"], "capabilities": list(caps)})


def test_cycle1_capability_without_new_fields_gets_defaults() -> None:
    capability = _manifest(_cap("demo.echo")).capabilities[0]
    assert capability.aliases == []
    assert capability.deprecated is False
    assert capability.replaced_by is None


def test_capability_parses_aliases_and_deprecation() -> None:
    capability = _manifest(_cap("demo.echo", aliases=["demo.say", "demo.repeat"],
                                deprecated=True, replaced_by="demo.shout")).capabilities[0]
    assert capability.aliases == ["demo.say", "demo.repeat"]
    assert capability.deprecated is True
    assert capability.replaced_by == "demo.shout"


def test_replaced_by_may_point_to_capability_of_another_provider() -> None:
    manifest = _manifest(_cap("demo.echo", deprecated=True, replaced_by="other.echo"))
    assert manifest.capabilities[0].replaced_by == "other.echo"


@pytest.mark.parametrize(
    ("caps", "message"),
    [
        ((_cap("demo.echo", aliases=["demo.say", "demo.say"]),), "duplicate capability aliases"),
        ((_cap("demo.echo", aliases=["demo.say"]), _cap("demo.ping", aliases=["demo.say"])),
         "duplicate capability aliases"),
        ((_cap("demo.echo", aliases=["demo.echo"]),), "alias equal to capability id"),
        ((_cap("demo.echo", aliases=["demo.ping"]), _cap("demo.ping")),
         "alias equal to capability id"),
        ((_cap("demo.echo", replaced_by="demo.echo"),), "replaced_by equal to its own id"),
    ],
    ids=["dup-alias-same-cap", "dup-alias-across-caps", "alias-equals-own-id",
         "alias-equals-other-id", "replaced-by-self"],
)
def test_alias_and_replacement_collisions_invalidate_manifest(
    caps: tuple[dict[str, object], ...], message: str
) -> None:
    with pytest.raises(ContractError, match=message):
        _manifest(*caps)


def test_wrong_types_for_new_fields_are_contract_errors() -> None:
    for extra in ({"aliases": "demo.say"}, {"aliases": [1]}, {"deprecated": "yes"},
                  {"replaced_by": 3}):
        with pytest.raises(ContractError):
            _manifest(_cap("demo.echo", **extra))


def test_resolve_prefers_canonical_id_then_alias() -> None:
    manifest = _manifest(_cap("demo.echo", aliases=["demo.say"]), _cap("demo.ping"))
    canonical = manifest.resolve("demo.echo")
    assert canonical is not None
    assert (canonical[0].id, canonical[1]) == ("demo.echo", False)
    via_alias = manifest.resolve("demo.say")
    assert via_alias is not None
    assert (via_alias[0].id, via_alias[1]) == ("demo.echo", True)
    assert manifest.resolve("demo.unknown") is None


def test_resolve_on_cycle1_manifest_matches_capability_lookup() -> None:
    manifest = _manifest(_cap("demo.echo"))
    resolved = manifest.resolve("demo.echo")
    assert resolved is not None and resolved[0] is manifest.capability("demo.echo")
    assert resolved[1] is False
