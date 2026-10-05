"""Manifest rules: SemVer version (4.4); aliases and deprecation (5.5, 5.6); taxonomy (5.1, 5.2)."""

import json
import subprocess
from pathlib import Path

import pytest

from helpers import PROVIDERS, bad_argv
from theforge.contracts import ContractError, ForgeManifest, Violation, from_dict
from theforge.contracts.codes import Codes
from theforge.contracts.semver import SemVer, parse_semver
from theforge.contracts.taxonomy import GENERIC_SEGMENTS, RESERVED_NAMESPACES, validate_taxonomy
from theforge.providers.echo.provider import MANIFEST as ECHO_MANIFEST


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


# --- Capability taxonomy: mechanical rules (reqs 5.1, 5.2) ----------------------------------


def _taxonomy(*caps: dict[str, object]) -> tuple[Violation, ...]:
    return validate_taxonomy(_manifest(*caps))


def _fields(violations: tuple[Violation, ...]) -> list[str | None]:
    return [v.field for v in violations]


@pytest.mark.parametrize(
    "cap_id",
    ["demo.echo", "demo.echo.fast", f"{'a' * 32}.b", f"ab.{'b' * 30}.{'c' * 30}",
     f"{'a' * 31}.{'b' * 32}", "spark.performance", "api.contract", "my-ns.sub-ject"],
    ids=["two-segments", "three-segments", "segment-at-32", "id-at-64-three-segments",
         "id-at-64-two-segments", "spark-fixture", "api-fixture", "hyphenated"],
)
def test_taxonomy_accepts_valid_capability_ids(cap_id: str) -> None:
    assert len(cap_id) <= 64
    assert _taxonomy(_cap(cap_id)) == ()


@pytest.mark.parametrize(
    ("cap_id", "fragment"),
    [
        ("a.b.c.d", "segments"),
        (f"{'a' * 33}.b", "segment"),
        (f"a.{'b' * 33}", "segment"),
        (f"{'a' * 32}.{'b' * 32}.c", "64"),
        ("forge.echo", "reserved"),
        ("theforge.echo", "reserved"),
        ("demo.misc", "generic"),
        ("utils.echo", "generic"),
        ("demo.echo.default", "generic"),
    ],
    ids=["four-segments", "namespace-too-long", "subject-too-long", "id-too-long",
         "reserved-forge", "reserved-theforge", "generic-subject", "generic-namespace",
         "generic-qualifier"],
)
def test_taxonomy_rejects_invalid_capability_ids(cap_id: str, fragment: str) -> None:
    violations = _taxonomy(_cap(cap_id))
    assert violations, cap_id
    assert all(v.code == Codes.MANIFEST_TAXONOMY for v in violations)
    assert set(_fields(violations)) == {"capabilities[0].id"}
    assert fragment in violations[0].detail
    assert repr(cap_id) in violations[0].detail


@pytest.mark.parametrize("segment", sorted(GENERIC_SEGMENTS))
def test_every_generic_segment_is_rejected_in_any_position(segment: str) -> None:
    for cap_id in (f"{segment}.echo", f"demo.{segment}", f"demo.echo.{segment}"):
        assert _fields(_taxonomy(_cap(cap_id))) == ["capabilities[0].id"], cap_id


def test_generic_and_reserved_sets_match_the_design_table() -> None:
    assert frozenset({"forge", "theforge"}) == RESERVED_NAMESPACES
    assert frozenset({
        "all", "any", "misc", "general", "generic", "default", "other", "stuff",
        "tool", "tools", "util", "utils"}) == GENERIC_SEGMENTS


def test_reserved_word_outside_namespace_and_generic_substrings_are_allowed() -> None:
    # Reserved names bind only the namespace; generic words match whole segments only.
    assert _taxonomy(_cap("demo.forge"), _cap("tooling.utility.defaults")) == ()


@pytest.mark.parametrize(
    "action", ["echo", "a", "dry-run", "v2", "a" + "b" * 31],
    ids=["word", "single-char", "hyphen", "digit", "at-32"],
)
def test_taxonomy_accepts_valid_actions(action: str) -> None:
    assert _taxonomy(_cap("demo.echo", actions=[action], default_action=action)) == ()


@pytest.mark.parametrize(
    "action", ["Echo", "2run", "-run", "dry_run", "run now", "a" + "b" * 32, "", "açao"],
    ids=["uppercase", "leading-digit", "leading-hyphen", "underscore", "space", "at-33",
         "empty", "non-ascii"],
)
def test_taxonomy_rejects_invalid_actions(action: str) -> None:
    violations = _taxonomy(_cap("demo.echo", actions=["echo", action], default_action="echo"))
    assert [(v.code, v.field) for v in violations] == [
        (Codes.MANIFEST_TAXONOMY, "capabilities[0].actions[1]")]
    assert "demo.echo" in violations[0].detail and repr(action) in violations[0].detail


@pytest.mark.parametrize(
    "alias", ["demo.say", "demo.say.loud", "other-ns.echo"],
    ids=["two-segments", "three-segments", "other-namespace"],
)
def test_taxonomy_accepts_valid_aliases(alias: str) -> None:
    assert _taxonomy(_cap("demo.echo", aliases=[alias])) == ()


@pytest.mark.parametrize(
    "alias",
    ["Demo.Say", "say", "demo..say", "demo.say.x.y", f"{'a' * 33}.say",
     f"{'a' * 32}.{'b' * 32}.c", "forge.say", "demo.tools", "demo_say.x"],
    ids=["uppercase", "single-segment", "empty-segment", "four-segments", "segment-too-long",
         "id-too-long", "reserved", "generic", "underscore"],
)
def test_taxonomy_rejects_invalid_aliases(alias: str) -> None:
    violations = _taxonomy(_cap("demo.echo", aliases=["demo.ok", alias]))
    assert violations
    assert {(v.code, v.field) for v in violations} == {
        (Codes.MANIFEST_TAXONOMY, "capabilities[0].aliases[1]")}
    assert repr(alias) in violations[0].detail and "demo.echo" in violations[0].detail


@pytest.mark.parametrize(
    "target", ["demo.shout", "other.echo.v2", "forge.echo", "demo.misc"],
    ids=["same-provider", "other-provider", "reserved-is-format-only", "generic-is-format-only"],
)
def test_taxonomy_accepts_replaced_by_in_id_format(target: str) -> None:
    assert _taxonomy(_cap("demo.echo", deprecated=True, replaced_by=target)) == ()


@pytest.mark.parametrize(
    "target", ["shout", "Demo.Shout", "demo.shout.x.y", f"{'a' * 33}.b",
               f"{'a' * 32}.{'b' * 32}.c", "", "demo shout"],
    ids=["single-segment", "uppercase", "four-segments", "segment-too-long", "id-too-long",
         "empty", "space"],
)
def test_taxonomy_rejects_replaced_by_off_id_format(target: str) -> None:
    violations = _taxonomy(_cap("demo.echo", deprecated=True, replaced_by=target))
    assert violations
    assert {(v.code, v.field) for v in violations} == {
        (Codes.MANIFEST_TAXONOMY, "capabilities[0].replaced_by")}
    assert repr(target) in violations[0].detail and "demo.echo" in violations[0].detail


def test_taxonomy_violation_order_is_deterministic() -> None:
    caps = (
        _cap("demo.ok"),
        _cap("demo.misc", actions=["Bad", "ok", "_x"], default_action="ok",
             aliases=["fine.alias", "forge.alias"], replaced_by="nope"),
        _cap("acme.utils.x.y", aliases=["Bad"]),
    )
    violations = _taxonomy(*caps)
    assert _fields(violations) == [
        "capabilities[1].id",
        "capabilities[1].aliases[1]",
        "capabilities[1].actions[0]",
        "capabilities[1].actions[2]",
        "capabilities[1].replaced_by",
        "capabilities[2].id",  # four segments
        "capabilities[2].id",  # generic segment
        "capabilities[2].aliases[0]",
    ]
    assert "segments" in violations[5].detail and "generic" in violations[6].detail
    assert violations == _taxonomy(*caps)
    assert all(v.code == Codes.MANIFEST_TAXONOMY for v in violations)


def test_taxonomy_reports_id_that_bypassed_construction_without_raising() -> None:
    manifest = _manifest(_cap("demo.echo"))
    object.__setattr__(manifest.capabilities[0], "id", "Bad Id")
    assert _fields(validate_taxonomy(manifest)) == ["capabilities[0].id"]


def test_manifest_without_capabilities_has_no_taxonomy_violations() -> None:
    assert validate_taxonomy(_manifest()) == ()


# --- Every provider shipped in the repository stays on-taxonomy (5.2) ------------------------


def _bad_forge_manifest(mode: str) -> ForgeManifest:
    proc = subprocess.run(
        [*bad_argv(mode, "bad-forge"), "describe"],
        input=json.dumps({"protocol": "forge/v1", "request_id": "r1", "op": "describe"}),
        capture_output=True, text=True, timeout=30, check=True)
    return from_dict(ForgeManifest, json.loads(proc.stdout)["payload"])


def test_echo_forge_capabilities_are_on_taxonomy() -> None:
    assert "demo.echo" in {c.id for c in ECHO_MANIFEST.capabilities}
    assert validate_taxonomy(ECHO_MANIFEST) == ()


def test_repository_ships_fixture_provider_manifests() -> None:
    assert len(sorted(PROVIDERS.glob("*.json"))) >= 2


@pytest.mark.parametrize("path", sorted(PROVIDERS.glob("*.json")), ids=lambda p: p.name)
def test_fixture_provider_capabilities_are_on_taxonomy(path: Path) -> None:
    manifest = from_dict(ForgeManifest, json.loads(path.read_text(encoding="utf-8")))
    assert manifest.capabilities
    assert validate_taxonomy(manifest) == ()


@pytest.mark.parametrize(
    "mode", ["ok", "describe-catch-all-glob", "describe-only-catch-all-glob",
             "describe-too-many-capabilities", "capability-spam"])
def test_bad_forge_default_capabilities_are_on_taxonomy(mode: str) -> None:
    manifest = _bad_forge_manifest(mode)
    assert manifest.capabilities
    assert validate_taxonomy(manifest) == ()


def test_taxonomy_rejects_trailing_newline_that_survives_construction() -> None:
    violations = _taxonomy(_cap("demo.echo\n", aliases=["demo.alias\n"]))
    assert _fields(violations) == ["capabilities[0].id", "capabilities[0].aliases[0]"]
