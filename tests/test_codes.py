"""Guard: every FORGE-* error code lives in theforge.contracts.codes (req 2.6)."""

import ast
from pathlib import Path

import theforge
from theforge.contracts.codes import Codes

SRC = Path(theforge.__file__).resolve().parent
CODES_FILE = SRC / "contracts" / "codes.py"


def _forge_literals(path: Path) -> list[tuple[int, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return [
        (node.lineno, node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and "FORGE-" in node.value
    ]


def test_no_forge_literal_outside_codes_module() -> None:
    offenders = [
        f"{path.relative_to(SRC)}:{lineno}: {value!r}"
        for path in sorted(SRC.rglob("*.py"))
        if path.resolve() != CODES_FILE
        for lineno, value in _forge_literals(path)
    ]
    assert offenders == []


def test_codes_are_unique_and_prefixed() -> None:
    values = {name: value for name, value in vars(Codes).items() if name.isupper()}
    assert values, "Codes declares no constants"
    assert all(isinstance(v, str) and v.startswith("FORGE-") for v in values.values())
    assert len(set(values.values())) == len(values)


def test_existing_code_values_are_preserved() -> None:
    assert Codes.PROTO_NOT_JSON == "FORGE-PROTO-NOT-JSON"
    assert Codes.PROTO_SCHEMA == "FORGE-PROTO-SCHEMA"
    assert Codes.PROTO_MISMATCH == "FORGE-PROTO-MISMATCH"
    assert Codes.PROTO_VERSION == "FORGE-PROTO-VERSION"
    assert Codes.PROTO_SPAWN == "FORGE-PROTO-SPAWN"
    assert Codes.PROTO_TIMEOUT == "FORGE-PROTO-TIMEOUT"
    assert Codes.PROTO_OVERSIZE == "FORGE-PROTO-OVERSIZE"
    assert Codes.PROTO_EXIT == "FORGE-PROTO-EXIT"
    assert Codes.PROTO_PRODUCER == "FORGE-PROTO-PRODUCER"
    assert Codes.PROVIDER_BLOCKED == "FORGE-PROVIDER-BLOCKED"
    assert Codes.PROVIDER_UNTRUSTED == "FORGE-PROVIDER-UNTRUSTED"
    assert Codes.PROVIDER_NOT_READY == "FORGE-PROVIDER-NOT-READY"
    assert Codes.HEALTH_FAILED == "FORGE-HEALTH-FAILED"
    assert Codes.HEALTH_UNAVAILABLE == "FORGE-HEALTH-UNAVAILABLE"
    assert Codes.USAGE == "FORGE-USAGE"
    assert Codes.INTERNAL == "FORGE-INTERNAL"


def test_errors_module_reexports_codes() -> None:
    from theforge import errors

    assert errors.Codes is Codes


def test_context_request_codes_declared() -> None:
    assert Codes.CONTEXT_REQUEST_UNSUPPORTED == "FORGE-CONTEXT-REQUEST-UNSUPPORTED"
    assert Codes.CONTEXT_REQUEST_LIMIT == "FORGE-CONTEXT-REQUEST-LIMIT"
    assert Codes.CONTEXT_REQUEST_INVALID == "FORGE-CONTEXT-REQUEST-INVALID"
