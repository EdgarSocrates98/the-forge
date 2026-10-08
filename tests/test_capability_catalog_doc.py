"""The capability catalog in ``docs/capabilities.md`` matches what the adapters expose
(real-provider-integration 9.2; requirements 5.1, 5.3, 5.7).

Both adapters run in replay (``--replay tests/fixtures/native/<forge>/default describe``) as
subprocesses of the current interpreter, where they are installed editable. The two catalog
tables of the document (exposed capabilities and native surface not exposed) are parsed and
compared both ways with the describe: a capability or action exposed but not catalogued fails,
and so does a catalogued one that is not exposed. Every "not exposed" limitation of the
describe must be catalogued with the same reason, verbatim.
"""

import json
import re
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from theforge.contracts import PROTOCOL_V1
from theforge.contracts.taxonomy import (
    ACTION,
    GENERIC_SEGMENTS,
    MAX_ID_LEN,
    MAX_SEGMENT_LEN,
    MAX_SEGMENTS,
    MIN_SEGMENTS,
    RESERVED_NAMESPACES,
)

REPO = Path(__file__).parents[1]
DOC = REPO / "docs" / "capabilities.md"
ADR = REPO / "docs" / "adr" / "0017-capability-taxonomy.md"
NATIVE = REPO / "tests" / "fixtures" / "native"
ADAPTERS = {
    "spark-forge-aws": "sparkforge_aws",
    "api-forge": "apiforge",
    "forge-doctor-data": "doctordata",
    "forge-doctor-api": "doctorapi",
}

EXPOSED_HEADER = "| Provider | Capability | Ações | Origem nativa |"
EXCLUDED_HEADER = "| Provider | Capability | Ação | Origem nativa | Motivo |"
NONE = "—"
TICKED = re.compile(r"`([^`]+)`")

# Limitation shapes of the adapters' describe (every one names what is not exposed).
ACTION_LIMITATION = re.compile(r"^action '([^']+)' of '([^']+)' not exposed \(([^)]+)\): (.+)$")
CAPABILITY_LIMITATION = re.compile(r"^capability '([^']+)'(?: \([^)]*\))? not exposed: (.+)$")
GROUP_LIMITATION = re.compile(r"^not exposed: ([^:]+): (.+)$")


@dataclass(frozen=True)
class Exclusion:
    provider: str
    capability: str | None
    action: str | None
    origin: frozenset[str]  # native tools of a group; empty for capability/action rows
    reason: str


# --- describe in replay ---------------------------------------------------------------------


def _describe(provider: str) -> dict[str, Any]:
    forge = ADAPTERS[provider]
    request = json.dumps(
        {
            "protocol": PROTOCOL_V1,
            "kind": "Request",
            "op": "describe",
            "request_id": "req-catalog",
            "payload": {},
        }
    ).encode()
    argv = [
        sys.executable,
        "-m",
        f"theforge_{forge}",
        "--replay",
        str(NATIVE / forge / "default"),
        "describe",
    ]
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as cwd:  # never the repo
        out = subprocess.run(argv, input=request, capture_output=True, timeout=120, cwd=cwd)
    assert out.returncode == 0, out.stderr
    response = json.loads(out.stdout)
    assert response["status"] == "ok", response
    payload: dict[str, Any] = response["payload"]
    assert payload["id"] == provider
    return payload


@pytest.fixture(scope="module")
def manifests() -> dict[str, dict[str, Any]]:
    return {provider: _describe(provider) for provider in ADAPTERS}


def exposed_of(manifests: dict[str, dict[str, Any]]) -> dict[tuple[str, str], tuple[str, ...]]:
    return {
        (provider, cap["id"]): tuple(cap["actions"])
        for provider, payload in manifests.items()
        for cap in payload["capabilities"]
    }


def exclusions_of(manifests: dict[str, dict[str, Any]]) -> set[Exclusion]:
    found: set[Exclusion] = set()
    for provider, payload in manifests.items():
        for text in payload["limitations"]:
            if m := ACTION_LIMITATION.match(text):
                action, cap, _tool, reason = m.groups()
                found.add(Exclusion(provider, cap, action, frozenset(), reason))
            elif m := CAPABILITY_LIMITATION.match(text):
                found.add(Exclusion(provider, m[1], None, frozenset(), m[2]))
            elif m := GROUP_LIMITATION.match(text):
                tools = frozenset(t.strip() for t in m[1].split(","))
                found.add(Exclusion(provider, None, None, tools, m[2]))
            else:
                assert "not exposed" not in text, f"unparsed limitation: {text!r}"
    return found


# --- catalog tables of docs/capabilities.md -------------------------------------------------


def _table(text: str, header: str) -> Iterator[list[str]]:
    lines = text.splitlines()
    assert lines.count(header) == 1, f"table header not found exactly once: {header}"
    start = lines.index(header) + 2  # skip the separator row
    for line in lines[start:]:
        if not line.startswith("|"):
            break
        yield [cell.strip() for cell in line.strip().strip("|").split("|")]


def _one(cell: str) -> str | None:
    if cell == NONE:
        return None
    ticked = TICKED.findall(cell)
    assert len(ticked) == 1, f"expected one `value` or {NONE}: {cell!r}"
    return ticked[0]


def parse_exposed(text: str) -> dict[tuple[str, str], tuple[str, ...]]:
    table: dict[tuple[str, str], tuple[str, ...]] = {}
    for provider, cap, actions, origin in _table(text, EXPOSED_HEADER):
        key = (_one(provider) or "", _one(cap) or "")
        assert key not in table, f"capability catalogued twice: {key}"
        assert TICKED.findall(origin), f"no native origin for {key}"
        table[key] = tuple(TICKED.findall(actions))
    return table


def parse_excluded(text: str) -> set[Exclusion]:
    rows: set[Exclusion] = set()
    for provider, cap, action, origin, reason in _table(text, EXCLUDED_HEADER):
        assert TICKED.findall(origin), f"no native origin in exclusion row {cap}/{action}"
        quoted = TICKED.findall(reason)
        assert len(quoted) == 1, f"reason must be one `quoted` text: {reason!r}"
        tools = frozenset() if cap != NONE else frozenset(TICKED.findall(origin))
        rows.add(Exclusion(_one(provider) or "", _one(cap), _one(action), tools, quoted[0]))
    return rows


def catalog_drift(
    catalogued: dict[tuple[str, str], tuple[str, ...]],
    exposed: dict[tuple[str, str], tuple[str, ...]],
) -> list[str]:
    """Differences between the catalogued and the exposed capabilities (empty = in sync)."""
    problems = [
        f"{p}/{c} is exposed but not in docs/capabilities.md"
        for p, c in sorted(exposed.keys() - catalogued.keys())
    ]
    problems += [
        f"{p}/{c} is catalogued but not exposed"
        for p, c in sorted(catalogued.keys() - exposed.keys())
    ]
    problems += [
        f"{p}/{c}: catalogued actions {list(catalogued[p, c])} != exposed {list(exposed[p, c])}"
        for p, c in sorted(catalogued.keys() & exposed.keys())
        if catalogued[p, c] != exposed[p, c]
    ]
    return problems


@pytest.fixture(scope="module")
def doc() -> str:
    return DOC.read_text(encoding="utf-8")


# --- the catalog matches the describe -------------------------------------------------------


def test_every_exposed_capability_is_catalogued_with_its_actions(
    doc: str, manifests: dict[str, dict[str, Any]]
) -> None:
    exposed = exposed_of(manifests)
    assert len(exposed) == 21  # 15 Spark Forge AWS + 2 API Forge + 4 Doctors
    assert catalog_drift(parse_exposed(doc), exposed) == []


def test_every_exclusion_is_catalogued_with_the_describe_reason(
    doc: str, manifests: dict[str, dict[str, Any]]
) -> None:
    from_describe = exclusions_of(manifests)
    catalogued = parse_excluded(doc)
    assert from_describe - catalogued == set(), "not exposed in describe, missing in the doc"
    assert catalogued - from_describe == set(), "catalogued exclusion absent from describe"
    assert sum(1 for e in from_describe if e.provider == "api-forge") == 19


def test_an_uncatalogued_capability_is_detected(
    doc: str, manifests: dict[str, dict[str, Any]]
) -> None:
    exposed = exposed_of(manifests)
    catalogued = parse_exposed(doc)
    missing = dict(catalogued)
    del missing["spark-forge-aws", "pyspark.static-analysis"]
    assert catalog_drift(missing, exposed) == [
        "spark-forge-aws/pyspark.static-analysis is exposed but not in docs/capabilities.md"
    ]

    extra = dict(exposed)
    extra["api-forge", "api.provenance"] = ("provenance",)
    assert catalog_drift(catalogued, extra) == [
        "api-forge/api.provenance is exposed but not in docs/capabilities.md"
    ]


def test_a_catalogued_capability_not_exposed_or_with_other_actions_is_detected(
    doc: str, manifests: dict[str, dict[str, Any]]
) -> None:
    exposed = exposed_of(manifests)
    catalogued = dict(parse_exposed(doc))
    catalogued["spark-forge-aws", "migration.assessment"] = ("migration-assess",)
    catalogued["api-forge", "api.analyze"] = ("analyze", "diff")
    assert catalog_drift(catalogued, exposed) == [
        "spark-forge-aws/migration.assessment is catalogued but not exposed",
        "api-forge/api.analyze: catalogued actions ['analyze', 'diff'] != exposed ['analyze']",
    ]


# --- the documented rules match the mechanical rules ----------------------------------------


def test_mechanical_rules_table_matches_the_code(doc: str) -> None:
    rules = "\n".join("|".join(row) for row in _table(doc, "| Regra | Valor |"))
    for word in sorted(GENERIC_SEGMENTS | RESERVED_NAMESPACES):
        assert f"`{word}`" in rules, word
    assert f"`^{ACTION.pattern}$`" in rules
    for number in (MIN_SEGMENTS, MAX_SEGMENTS, MAX_SEGMENT_LEN, MAX_ID_LEN):
        assert str(number) in rules


def test_doc_covers_the_rules_and_links_the_adr(doc: str) -> None:
    for section in (
        "Namespace",
        "Subject",
        "Granularidade",
        "Ações",
        "Sobreposição",
        "Versionamento",
        "Depreciação",
        "Aliases",
    ):
        assert re.search(rf"^## {section}\b", doc, re.MULTILINE), section
    assert "adr/0017-capability-taxonomy.md" in doc
    assert ADR.is_file()
    assert "FORGE-MANIFEST-TAXONOMY" in ADR.read_text(encoding="utf-8")
