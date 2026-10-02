# The Forge Ciclo 1 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Construir o core local do The Forge: Forge Protocol v1 (exec-protocol subprocess+JSON), contratos v1, registry com trust, routing determinístico explicável, Context Broker, run store com receipts, doctor e CLI `theforge`/`forge`, provado com `echo-forge` e providers de fixture.

**Architecture:** Pacote Python stdlib-only em `src/theforge/`. Módulos com uma responsabilidade cada, conversando só via dataclasses de `theforge.contracts`. Providers são processos externos chamados por `SubprocessTransport` (`<argv> <op>`, JSON em stdin/stdout). Spec: `docs/superpowers/specs/2026-10-02-the-forge-protocol-core-design.md`.

**Tech Stack:** Python ≥3.11 (stdlib: argparse, dataclasses, tomllib, subprocess, hashlib). Dev: pytest, hypothesis, jsonschema, ruff, mypy. Build: hatchling.

---

## Convenções

- Shell: Git Bash. Interpretador do venv: `PY=.venv/Scripts/python` (Windows) ou `PY=.venv/bin/python` (POSIX). Todos os comandos abaixo usam `$PY`.
- Todos os testes rodam offline (fixture autouse bloqueia sockets). Testes `slow` só no Task 20.
- Commits pequenos, mensagens convencionais, sem push. Trailer obrigatório em todo commit:
  `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>`
- Arquivos de teste ficam planos em `tests/` (nomes únicos, sem `__init__.py`); helpers compartilhados em `tests/helpers.py`.

## Esclarecimentos do spec (decididos aqui)

1. `ExecutionReceipt` usa o campo `status` (valores de Outcome) no lugar de `outcome` — cabeçalho comum uniforme.
2. `Finding` = `{id, title, severity: info|low|medium|high|critical, evidence_ids[]}`.
3. Health dos providers retorna `HealthOutcome{status: ok|degraded|unavailable|error, error}`; `degraded` conta como saudável.
4. Cache de registry guarda só registros `ready`; os demais são re-descritos a cada uso.
5. Hash de receipt = sha256 do JSON canônico **já redigido** (o que está em disco é verificável).
6. `theforge doctor` e `providers health` saem com exit 1 quando algo está `fail`/indisponível.

## Estrutura de arquivos

```text
pyproject.toml  README.md  CLAUDE.md  .gitignore
schemas/<Contract>.schema.json            # gerados, paridade testada
src/theforge/
  __init__.py  __main__.py  meta.py  errors.py  state.py
  contracts/  __init__.py base.py canonical.py types.py manifest.py task.py
              routing.py context.py result.py receipt.py envelope.py schema.py
  security/   __init__.py redact.py env.py paths.py
  protocol/   __init__.py negotiate.py transport.py
  providers/  __init__.py  echo/__init__.py echo/provider.py echo/__main__.py
  registry/   __init__.py config.py registry.py health.py
  context/    __init__.py scan.py broker.py
  routing/    __init__.py signals.py router.py
  runs/       __init__.py store.py
  forger/     __init__.py orchestrator.py
  environment/__init__.py doctor.py
  cli/        __init__.py main.py commands.py render.py
tests/
  conftest.py helpers.py test_*.py
  fixtures/providers/fixture_forge.py fixture-spark.json fixture-api.json bad_forge.py
  golden/explain_case_b.txt
docs/ architecture.md protocol.md provider-authoring.md security.md cli.md adr/0001..0008
```

---

### Task 1: Scaffold do projeto

**Files:**
- Modify: `.gitignore`
- Create: `pyproject.toml`, `README.md`, `src/theforge/__init__.py`, `tests/conftest.py`, `tests/test_smoke.py`

- [ ] **Step 1: Substituir `.gitignore`**

```gitignore
prompt_evo*.md
.venv/
__pycache__/
*.py[cod]
*.egg-info/
dist/
build/
.pytest_cache/
.mypy_cache/
.ruff_cache/
.hypothesis/
.forge/
```

- [ ] **Step 2: Criar `pyproject.toml`**

```toml
[build-system]
requires = ["hatchling>=1.25"]
build-backend = "hatchling.build"

[project]
name = "theforge"
version = "0.1.0"
description = "Local-first control plane that discovers, routes and governs specialist Forges."
readme = "README.md"
requires-python = ">=3.11"
license = { text = "MIT" }
dependencies = []

[project.optional-dependencies]
dev = ["pytest>=8.0", "hypothesis>=6.100", "jsonschema>=4.21", "ruff>=0.6", "mypy>=1.10"]

[project.scripts]
theforge = "theforge.cli.main:main"
forge = "theforge.cli.main:main"

[tool.hatch.build.targets.wheel]
packages = ["src/theforge"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-q -m 'not slow'"
markers = ["slow: builds packages or needs network (fresh install gate)"]

[tool.ruff]
line-length = 100
target-version = "py311"
src = ["src", "tests"]

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP", "SIM"]

[tool.mypy]
python_version = "3.11"
strict = true
mypy_path = "src"
files = ["src"]
```

- [ ] **Step 3: Criar `README.md` mínimo (substituído no Task 19)**

```markdown
# The Forge

Local-first control plane for specialist Forges. See `docs/`.
```

- [ ] **Step 4: Criar `src/theforge/__init__.py`**

```python
"""The Forge: local-first control plane for specialist Forges."""

__version__ = "0.1.0"
```

- [ ] **Step 5: Criar `tests/conftest.py`**

```python
import socket
from typing import Any

import pytest


@pytest.fixture(autouse=True)
def _offline(monkeypatch: pytest.MonkeyPatch) -> None:
    def guard(*args: Any, **kwargs: Any) -> None:
        raise OSError("network access disabled in tests")

    monkeypatch.setattr(socket.socket, "connect", guard)
    monkeypatch.setattr(socket.socket, "connect_ex", guard)


@pytest.fixture(autouse=True)
def _isolated_user_config(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("THEFORGE_CONFIG_DIR", str(tmp_path_factory.mktemp("user-config")))
```

- [ ] **Step 6: Criar `tests/test_smoke.py`**

```python
import socket

import pytest

import theforge


def test_version() -> None:
    assert theforge.__version__ == "0.1.0"


def test_network_is_blocked() -> None:
    with pytest.raises(OSError, match="network access disabled"):
        socket.create_connection(("127.0.0.1", 9), timeout=1)
```

- [ ] **Step 7: Criar venv e instalar**

Run (Windows): `py -V:Astral/CPython3.11.15 -m venv .venv` (POSIX: `python3.11 -m venv .venv`)
Run: `$PY -m pip install -e ".[dev]"`
Expected: `Successfully installed ... theforge-0.1.0`

- [ ] **Step 8: Rodar testes**

Run: `$PY -m pytest`
Expected: `2 passed`

- [ ] **Step 9: Commit**

```bash
git add .gitignore pyproject.toml README.md src tests
git commit -m "chore: scaffold theforge package with offline test harness"
```

---

### Task 2: JSON canônico e hashing

**Files:**
- Create: `src/theforge/contracts/__init__.py` (vazio por enquanto), `src/theforge/contracts/canonical.py`
- Test: `tests/test_canonical.py`

- [ ] **Step 1: Teste falhando** — `tests/test_canonical.py`

```python
import json

from hypothesis import given
from hypothesis import strategies as st

from theforge.contracts.canonical import canonical_json, sha256_hex, sha256_of, utc_now

JSON_VALUES = st.recursive(
    st.none() | st.booleans() | st.integers() | st.text(),
    lambda inner: st.lists(inner) | st.dictionaries(st.text(), inner),
    max_leaves=20,
)


def test_key_order_does_not_change_hash() -> None:
    assert sha256_of({"b": 1, "a": 2}) == sha256_of({"a": 2, "b": 1})


def test_compact_separators() -> None:
    assert canonical_json({"a": [1, 2]}) == '{"a":[1,2]}'


def test_unicode_is_kept() -> None:
    assert canonical_json({"k": "ação"}) == '{"k":"ação"}'


def test_sha256_hex() -> None:
    assert sha256_hex(b"") == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


@given(JSON_VALUES)
def test_canonical_roundtrip_is_stable(value: object) -> None:
    once = canonical_json(value)
    assert canonical_json(json.loads(once)) == once


def test_utc_now_format() -> None:
    stamp = utc_now()
    assert stamp.endswith("Z") and "T" in stamp
```

- [ ] **Step 2: Ver falhar**

Run: `$PY -m pytest tests/test_canonical.py`
Expected: FAIL `ModuleNotFoundError: No module named 'theforge.contracts'`

- [ ] **Step 3: Implementar**

`src/theforge/contracts/__init__.py`:

```python
"""Versioned Forge contracts (v1)."""
```

`src/theforge/contracts/canonical.py`:

```python
"""Canonical JSON and hashing shared by every persisted contract."""

import hashlib
import json
from datetime import UTC, datetime
from typing import Any


def canonical_json(obj: Any) -> str:
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_of(obj: Any) -> str:
    return sha256_hex(canonical_json(obj).encode("utf-8"))


def utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
```

- [ ] **Step 4: Ver passar**

Run: `$PY -m pytest tests/test_canonical.py`
Expected: `6 passed`

- [ ] **Step 5: Commit**

```bash
git add src/theforge/contracts tests/test_canonical.py
git commit -m "feat(contracts): add canonical JSON and sha256 helpers"
```

---

### Task 3: Conversão genérica dict ⇄ dataclass

**Files:**
- Create: `src/theforge/contracts/base.py`
- Test: `tests/test_contracts_base.py`

- [ ] **Step 1: Teste falhando** — `tests/test_contracts_base.py`

```python
from dataclasses import dataclass, field
from typing import Any, Literal

import pytest

from theforge.contracts.base import ContractError, from_dict, to_dict


@dataclass(frozen=True, kw_only=True)
class Inner:
    name: str
    size: int = 0


@dataclass(frozen=True, kw_only=True)
class Outer:
    kind: Literal["a", "b"]
    inner: Inner
    items: list[Inner] = field(default_factory=list)
    note: str | None = None
    ratio: float = 1.0
    flag: bool = False
    extra: dict[str, Any] = field(default_factory=dict)


def test_roundtrip() -> None:
    obj = Outer(
        kind="a", inner=Inner(name="x", size=2), items=[Inner(name="y")],
        note="n", ratio=0.5, flag=True, extra={"k": [1]},
    )
    assert from_dict(Outer, to_dict(obj)) == obj


def test_missing_required_field_reports_path() -> None:
    with pytest.raises(ContractError, match=r"\$\.inner: required field missing"):
        from_dict(Outer, {"kind": "a"})


def test_literal_rejects_unknown_value() -> None:
    with pytest.raises(ContractError, match="expected one of"):
        from_dict(Outer, {"kind": "z", "inner": {"name": "x"}})


def test_bool_is_not_an_integer() -> None:
    with pytest.raises(ContractError, match=r"\$\.inner\.size: expected integer"):
        from_dict(Outer, {"kind": "a", "inner": {"name": "x", "size": True}})


def test_int_is_accepted_as_float() -> None:
    assert from_dict(Outer, {"kind": "a", "inner": {"name": "x"}, "ratio": 2}).ratio == 2.0


def test_optional_accepts_null() -> None:
    assert from_dict(Outer, {"kind": "a", "inner": {"name": "x"}, "note": None}).note is None


def test_unknown_fields_are_ignored() -> None:
    assert from_dict(Inner, {"name": "x", "future_field": 1}) == Inner(name="x")


def test_list_item_path_in_error() -> None:
    data = {"kind": "a", "inner": {"name": "x"}, "items": [{"name": "ok"}, {"name": 3}]}
    with pytest.raises(ContractError, match=r"\$\.items\[1\]\.name"):
        from_dict(Outer, data)


def test_non_object_rejected() -> None:
    with pytest.raises(ContractError, match="expected object"):
        from_dict(Inner, [1])


def test_to_dict_rejects_non_dataclass() -> None:
    with pytest.raises(TypeError):
        to_dict({"a": 1})
```

- [ ] **Step 2: Ver falhar**

Run: `$PY -m pytest tests/test_contracts_base.py`
Expected: FAIL `ModuleNotFoundError: No module named 'theforge.contracts.base'`

- [ ] **Step 3: Implementar** — `src/theforge/contracts/base.py`

```python
"""Generic dict <-> dataclass conversion with strict validation.

Unknown fields are ignored (forward compatibility inside a major version);
missing required fields, wrong types and unknown Literal values are errors.
"""

import types
from dataclasses import MISSING, asdict, fields, is_dataclass
from typing import Any, Literal, TypeVar, Union, cast, get_args, get_origin, get_type_hints

T = TypeVar("T")


class ContractError(ValueError):
    """Raised when data does not satisfy a contract."""


def to_dict(obj: Any) -> dict[str, Any]:
    if not is_dataclass(obj) or isinstance(obj, type):
        raise TypeError(f"expected dataclass instance, got {type(obj).__name__}")
    return asdict(obj)


def from_dict(cls: type[T], data: Any, path: str = "$") -> T:
    if not isinstance(data, dict):
        raise ContractError(f"{path}: expected object, got {type(data).__name__}")
    hints = get_type_hints(cls)
    kwargs: dict[str, Any] = {}
    for f in fields(cast(Any, cls)):
        if f.name in data:
            kwargs[f.name] = _coerce(hints[f.name], data[f.name], f"{path}.{f.name}")
        elif f.default is MISSING and f.default_factory is MISSING:
            raise ContractError(f"{path}.{f.name}: required field missing")
    factory: Any = cls
    try:
        return cast(T, factory(**kwargs))
    except ContractError as exc:
        raise ContractError(f"{path}: {exc}") from exc


def _coerce(tp: Any, value: Any, path: str) -> Any:
    if tp is Any:
        return value
    origin = get_origin(tp)
    args = get_args(tp)
    if origin in (Union, types.UnionType):
        if value is None and type(None) in args:
            return None
        errors: list[str] = []
        for member in args:
            if member is type(None):
                continue
            try:
                return _coerce(member, value, path)
            except ContractError as exc:
                errors.append(str(exc))
        raise ContractError(f"{path}: no union member matched ({'; '.join(errors)})")
    if origin is Literal:
        if value not in args:
            raise ContractError(f"{path}: expected one of {list(args)}, got {value!r}")
        return value
    if origin is list:
        if not isinstance(value, list):
            raise ContractError(f"{path}: expected array, got {type(value).__name__}")
        return [_coerce(args[0], item, f"{path}[{i}]") for i, item in enumerate(value)]
    if origin is dict:
        if not isinstance(value, dict):
            raise ContractError(f"{path}: expected object, got {type(value).__name__}")
        return {str(k): _coerce(args[1], v, f"{path}.{k}") for k, v in value.items()}
    if isinstance(tp, type) and is_dataclass(tp):
        return from_dict(tp, value, path)
    return _coerce_scalar(tp, value, path)


def _coerce_scalar(tp: Any, value: Any, path: str) -> Any:
    if tp is bool:
        if not isinstance(value, bool):
            raise ContractError(f"{path}: expected boolean, got {type(value).__name__}")
        return value
    if tp is int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ContractError(f"{path}: expected integer, got {type(value).__name__}")
        return value
    if tp is float:
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise ContractError(f"{path}: expected number, got {type(value).__name__}")
        return float(value)
    if tp is str:
        if not isinstance(value, str):
            raise ContractError(f"{path}: expected string, got {type(value).__name__}")
        return value
    raise ContractError(f"{path}: unsupported annotation {tp!r}")
```

- [ ] **Step 4: Ver passar**

Run: `$PY -m pytest tests/test_contracts_base.py`
Expected: `10 passed`

- [ ] **Step 5: Commit**

```bash
git add src/theforge/contracts/base.py tests/test_contracts_base.py
git commit -m "feat(contracts): add strict generic dict-dataclass conversion"
```

---
### Task 4: Modelos de contrato v1

**Files:**
- Create: `src/theforge/contracts/types.py`, `manifest.py`, `task.py`, `routing.py`, `context.py`, `result.py`, `receipt.py`, `envelope.py`, `src/theforge/meta.py`, `src/theforge/errors.py`
- Modify: `src/theforge/contracts/__init__.py`
- Test: `tests/test_contracts_models.py`

- [ ] **Step 1: Teste falhando** — `tests/test_contracts_models.py`

```python
import pytest

from theforge.contracts import (
    Confidence,
    ContractError,
    ExecutionResult,
    ForgeManifest,
    Producer,
    Response,
    RoutingDecision,
    from_dict,
)

P = {"id": "p", "version": "1"}
CAP = {
    "id": "demo.echo", "actions": ["echo"], "default_action": "echo",
    "state": "supported", "operation_class": "read_only",
}


def manifest_dict(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "id": "demo-forge", "version": "1.0.0", "protocols": ["forge/v1"],
        "ops": ["describe", "health", "execute"], "capabilities": [dict(CAP)],
    }
    data.update(overrides)
    return data


def test_manifest_parses_with_defaults() -> None:
    m = from_dict(ForgeManifest, manifest_dict())
    assert m.schema == "theforge/ForgeManifest/v1"
    assert m.capability("demo.echo") is not None
    assert m.capability("nope") is None
    assert m.capabilities[0].signals.keywords == []


@pytest.mark.parametrize("cap_id", ["Demo.echo", "demo", "demo..echo", "demo.Echo", "1demo.x"])
def test_invalid_capability_ids(cap_id: str) -> None:
    caps = [{**CAP, "id": cap_id}]
    with pytest.raises(ContractError, match="invalid capability id"):
        from_dict(ForgeManifest, manifest_dict(capabilities=caps))


def test_default_action_must_be_offered() -> None:
    with pytest.raises(ContractError, match="default_action"):
        from_dict(ForgeManifest, manifest_dict(capabilities=[{**CAP, "default_action": "x"}]))


def test_manifest_requires_describe_and_health() -> None:
    with pytest.raises(ContractError, match="missing required ops"):
        from_dict(ForgeManifest, manifest_dict(ops=["execute"]))


def test_duplicate_capability_ids_rejected() -> None:
    with pytest.raises(ContractError, match="duplicate capability ids"):
        from_dict(ForgeManifest, manifest_dict(capabilities=[dict(CAP), dict(CAP)]))


def test_manifest_rejects_foreign_schema() -> None:
    with pytest.raises(ContractError, match="unsupported manifest schema"):
        from_dict(ForgeManifest, manifest_dict(schema="other/v1"))


def test_invalid_provider_id() -> None:
    with pytest.raises(ContractError, match="invalid provider id"):
        from_dict(ForgeManifest, manifest_dict(id="Demo Forge"))


def test_response_refused_requires_error() -> None:
    with pytest.raises(ContractError, match="error is required"):
        from_dict(Response, {"request_id": "r", "producer": P, "status": "refused"})


def test_response_ok_minimal() -> None:
    r = from_dict(Response, {"request_id": "r", "producer": P, "status": "ok"})
    assert r.payload == {} and r.protocol == "forge/v1" and r.kind == "Response"


def test_routed_decision_requires_selection() -> None:
    with pytest.raises(ContractError, match="requires a selection"):
        RoutingDecision(
            producer=Producer(id="p", version="1"), created_at="t", status="routed",
            task_id="t", reason="r", confidence=Confidence(level="high"),
        )


def test_execution_result_metrics_default_unknown() -> None:
    r = from_dict(ExecutionResult, {"producer": P, "created_at": "t", "status": "ok"})
    assert r.metrics.tokens.kind == "unknown" and r.metrics.tokens.value is None


def test_metric_int_coerced_to_float() -> None:
    data = {
        "producer": P, "created_at": "t", "status": "ok",
        "metrics": {"duration_ms": {"value": 12, "kind": "measured"}},
    }
    assert from_dict(ExecutionResult, data).metrics.duration_ms.value == 12.0


def test_evidence_epistemic_is_validated() -> None:
    evidence = {"id": "e", "epistemic": "certain", "subject": "s", "claim": "c", "producer": P}
    data = {"producer": P, "created_at": "t", "status": "ok", "evidence": [evidence]}
    with pytest.raises(ContractError, match="expected one of"):
        from_dict(ExecutionResult, data)
```

- [ ] **Step 2: Ver falhar**

Run: `$PY -m pytest tests/test_contracts_models.py`
Expected: FAIL `ImportError: cannot import name 'Confidence'`

- [ ] **Step 3: `src/theforge/contracts/types.py`**

```python
"""Shared literal types and small value objects for all contracts."""

from dataclasses import dataclass
from typing import Literal

TrustLevel = Literal["builtin", "trusted", "local", "unverified", "blocked"]
CapabilityState = Literal["supported", "heuristic", "unresolved", "unsupported"]
OperationClass = Literal[
    "read_only", "local_mutation", "external_read", "external_mutation", "destructive"
]
BudgetProfile = Literal["economy", "balanced", "max"]
Epistemic = Literal["confirmed", "observed", "inferred", "proposed", "unresolved"]
MetricKind = Literal["measured", "estimated", "unknown"]
ResponseStatus = Literal["ok", "partial", "refused", "error"]
Outcome = Literal["ok", "partial", "refused", "provider_failure", "ambiguous", "no_route"]
Severity = Literal["info", "low", "medium", "high", "critical"]
HealthStatus = Literal["ok", "degraded", "unavailable"]

TRUST_RANK: dict[str, int] = {
    "builtin": 0, "trusted": 1, "local": 2, "unverified": 3, "blocked": 4,
}


@dataclass(frozen=True, kw_only=True)
class Producer:
    id: str
    version: str


@dataclass(frozen=True, kw_only=True)
class ErrorInfo:
    code: str
    detail: str
    field: str | None = None
    unlock: str | None = None
```

- [ ] **Step 4: `src/theforge/contracts/manifest.py`**

```python
"""ForgeManifest: what a provider declares about itself via `describe`."""

import re
from dataclasses import dataclass, field

from theforge.contracts.base import ContractError
from theforge.contracts.types import CapabilityState, OperationClass

MANIFEST_SCHEMA = "theforge/ForgeManifest/v1"
CAPABILITY_ID = re.compile(r"^[a-z][a-z0-9-]*(\.[a-z][a-z0-9-]*)+$")
PROVIDER_ID = re.compile(r"^[a-z][a-z0-9-]*$")
REQUIRED_OPS = ("describe", "health")


@dataclass(frozen=True, kw_only=True)
class Signals:
    keywords: list[str] = field(default_factory=list)
    file_globs: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)


@dataclass(frozen=True, kw_only=True)
class Capability:
    id: str = field(metadata={"pattern": CAPABILITY_ID.pattern})
    actions: list[str]
    default_action: str
    state: CapabilityState
    operation_class: OperationClass
    description: str = ""
    signals: Signals = field(default_factory=Signals)

    def __post_init__(self) -> None:
        if not CAPABILITY_ID.match(self.id):
            raise ContractError(f"invalid capability id {self.id!r}")
        if not self.actions:
            raise ContractError(f"capability {self.id}: actions must not be empty")
        if self.default_action not in self.actions:
            raise ContractError(
                f"capability {self.id}: default_action {self.default_action!r} not in actions"
            )


@dataclass(frozen=True, kw_only=True)
class ExecutionInfo:
    local: bool = True
    offline: bool = True
    requires_network: bool = False


@dataclass(frozen=True, kw_only=True)
class ForgeManifest:
    schema: str = MANIFEST_SCHEMA
    id: str = field(metadata={"pattern": PROVIDER_ID.pattern})
    version: str
    protocols: list[str]
    ops: list[str]
    domains: list[str] = field(default_factory=list)
    capabilities: list[Capability] = field(default_factory=list)
    execution: ExecutionInfo = field(default_factory=ExecutionInfo)
    limitations: list[str] = field(default_factory=list)
    unknowns: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.schema != MANIFEST_SCHEMA:
            raise ContractError(f"unsupported manifest schema {self.schema!r}")
        if not PROVIDER_ID.match(self.id):
            raise ContractError(f"invalid provider id {self.id!r}")
        missing = [op for op in REQUIRED_OPS if op not in self.ops]
        if missing:
            raise ContractError(f"manifest {self.id}: missing required ops {missing}")
        if not self.protocols:
            raise ContractError(f"manifest {self.id}: protocols must not be empty")
        ids = [c.id for c in self.capabilities]
        dups = sorted({i for i in ids if ids.count(i) > 1})
        if dups:
            raise ContractError(f"manifest {self.id}: duplicate capability ids {dups}")

    def capability(self, capability_id: str) -> Capability | None:
        return next((c for c in self.capabilities if c.id == capability_id), None)
```

- [ ] **Step 5: `src/theforge/contracts/task.py`**

```python
"""TaskSpec: the normalized request The Forger works on."""

from dataclasses import dataclass, field
from typing import Any, Literal

from theforge.contracts.base import ContractError
from theforge.contracts.types import BudgetProfile, Producer

TASK_SCHEMA = "theforge/TaskSpec/v1"


@dataclass(frozen=True, kw_only=True)
class TaskSpec:
    schema: str = TASK_SCHEMA
    producer: Producer
    created_at: str
    status: Literal["created"] = "created"
    id: str
    intent: str
    workspace_root: str
    targets: list[str] = field(default_factory=lambda: ["."])
    budget_profile: BudgetProfile = "balanced"
    requested_capability: str | None = None
    requested_action: str | None = None
    constraints: dict[str, Any] = field(default_factory=dict)
    limitations: list[str] = field(default_factory=list)
    unknowns: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.intent.strip():
            raise ContractError("task intent must not be empty")
```

- [ ] **Step 6: `src/theforge/contracts/routing.py`**

```python
"""RoutingDecision: auditable record of why a provider was (not) selected."""

from dataclasses import dataclass, field
from typing import Literal

from theforge.contracts.base import ContractError
from theforge.contracts.types import Producer

ROUTING_SCHEMA = "theforge/RoutingDecision/v1"


@dataclass(frozen=True, kw_only=True)
class MatchedSignals:
    dependencies: list[str] = field(default_factory=list)
    file_globs: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)


@dataclass(frozen=True, kw_only=True)
class Candidate:
    provider: str
    capability: str
    matched: MatchedSignals = field(default_factory=MatchedSignals)
    rank_key: list[int] = field(default_factory=list)


@dataclass(frozen=True, kw_only=True)
class Selection:
    provider: str
    capability: str
    action: str
    role: Literal["primary", "specialist"] = "primary"


@dataclass(frozen=True, kw_only=True)
class Confidence:
    level: Literal["high", "low"]
    measured_signals: list[str] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=list)


@dataclass(frozen=True, kw_only=True)
class RoutingDecision:
    schema: str = ROUTING_SCHEMA
    producer: Producer
    created_at: str
    status: Literal["routed", "ambiguous", "no_route"]
    task_id: str
    candidates: list[Candidate] = field(default_factory=list)
    selected: list[Selection] = field(default_factory=list)
    pattern: Literal["route"] = "route"
    reason: str
    confidence: Confidence
    fallbacks_used: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    unknowns: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.status == "routed" and not self.selected:
            raise ContractError("routed decision requires a selection")
```

- [ ] **Step 7: `src/theforge/contracts/context.py`**

```python
"""ContextPack: references + hashes of the files a provider may read."""

from dataclasses import dataclass, field
from typing import Literal

from theforge.contracts.types import Producer

CONTEXT_SCHEMA = "theforge/ContextPack/v1"


@dataclass(frozen=True, kw_only=True)
class ContextFile:
    path: str
    sha256: str
    bytes: int
    reason: str = ""


@dataclass(frozen=True, kw_only=True)
class ExcludedFile:
    path: str
    reason: str


@dataclass(frozen=True, kw_only=True)
class ContextPack:
    schema: str = CONTEXT_SCHEMA
    producer: Producer
    created_at: str
    status: Literal["complete", "truncated"]
    task_id: str
    provider_id: str
    root: str
    files: list[ContextFile] = field(default_factory=list)
    excluded: list[ExcludedFile] = field(default_factory=list)
    budget_bytes: int
    used_bytes: int = 0
    truncated: bool = False
    limitations: list[str] = field(default_factory=list)
    unknowns: list[str] = field(default_factory=list)
```

- [ ] **Step 8: `src/theforge/contracts/result.py`**

```python
"""ExecutionResult, Finding and Evidence returned by providers."""

from dataclasses import dataclass, field
from typing import Literal

from theforge.contracts.types import Epistemic, MetricKind, Producer, Severity

RESULT_SCHEMA = "theforge/ExecutionResult/v1"


@dataclass(frozen=True, kw_only=True)
class Location:
    path: str
    line: int | None = None


@dataclass(frozen=True, kw_only=True)
class Evidence:
    id: str
    epistemic: Epistemic
    subject: str
    claim: str
    producer: Producer
    location: Location | None = None
    hash: str | None = None
    limitations: list[str] = field(default_factory=list)


@dataclass(frozen=True, kw_only=True)
class Finding:
    id: str
    title: str
    severity: Severity = "info"
    evidence_ids: list[str] = field(default_factory=list)


@dataclass(frozen=True, kw_only=True)
class Artifact:
    path: str
    sha256: str


@dataclass(frozen=True, kw_only=True)
class Metric:
    value: float | None = None
    kind: MetricKind = "unknown"


@dataclass(frozen=True, kw_only=True)
class Metrics:
    duration_ms: Metric = field(default_factory=Metric)
    context_bytes: Metric = field(default_factory=Metric)
    tokens: Metric = field(default_factory=Metric)


@dataclass(frozen=True, kw_only=True)
class ExecutionResult:
    schema: str = RESULT_SCHEMA
    producer: Producer
    created_at: str
    status: Literal["ok", "partial"]
    findings: list[Finding] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)
    artifacts: list[Artifact] = field(default_factory=list)
    metrics: Metrics = field(default_factory=Metrics)
    limitations: list[str] = field(default_factory=list)
    unknowns: list[str] = field(default_factory=list)
```

- [ ] **Step 9: `src/theforge/contracts/receipt.py`**

```python
"""ExecutionReceipt: hashes tying a run's inputs, provider and result together."""

from dataclasses import dataclass, field

from theforge.contracts.types import ErrorInfo, Outcome, Producer, TrustLevel

RECEIPT_SCHEMA = "theforge/ExecutionReceipt/v1"


@dataclass(frozen=True, kw_only=True)
class ReceiptInputs:
    task_sha256: str
    routing_sha256: str | None = None
    context_sha256: str | None = None


@dataclass(frozen=True, kw_only=True)
class ReceiptProvider:
    id: str
    version: str
    trust: TrustLevel
    manifest_sha256: str | None = None


@dataclass(frozen=True, kw_only=True)
class ExecutionReceipt:
    schema: str = RECEIPT_SCHEMA
    producer: Producer
    created_at: str
    status: Outcome
    run_id: str
    forge_version: str
    inputs: ReceiptInputs
    provider: ReceiptProvider | None = None
    result_sha256: str | None = None
    started_at: str
    finished_at: str
    error: ErrorInfo | None = None
    limitations: list[str] = field(default_factory=list)
    unknowns: list[str] = field(default_factory=list)
```

- [ ] **Step 10: `src/theforge/contracts/envelope.py`**

```python
"""Forge Protocol v1 envelopes and op payloads."""

import secrets
from dataclasses import dataclass, field
from typing import Any, Literal

from theforge.contracts.base import ContractError
from theforge.contracts.context import ContextPack
from theforge.contracts.task import TaskSpec
from theforge.contracts.types import ErrorInfo, HealthStatus, Producer, ResponseStatus

PROTOCOL_V1 = "forge/v1"


def new_request_id() -> str:
    return f"r_{secrets.token_hex(8)}"


@dataclass(frozen=True, kw_only=True)
class Request:
    protocol: str = PROTOCOL_V1
    kind: Literal["Request"] = "Request"
    op: str
    request_id: str
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, kw_only=True)
class Response:
    protocol: str = PROTOCOL_V1
    kind: Literal["Response"] = "Response"
    request_id: str
    producer: Producer
    status: ResponseStatus
    payload: dict[str, Any] = field(default_factory=dict)
    error: ErrorInfo | None = None
    limitations: list[str] = field(default_factory=list)
    unknowns: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.status in ("refused", "error") and self.error is None:
            raise ContractError(f"response status {self.status!r}: error is required")


@dataclass(frozen=True, kw_only=True)
class HealthCheck:
    name: str
    ok: bool
    detail: str = ""


@dataclass(frozen=True, kw_only=True)
class HealthReport:
    status: HealthStatus
    checks: list[HealthCheck] = field(default_factory=list)


@dataclass(frozen=True, kw_only=True)
class ExecuteRequest:
    task: TaskSpec
    capability: str
    action: str
    context: ContextPack
```

- [ ] **Step 11: Substituir `src/theforge/contracts/__init__.py`**

```python
"""Versioned Forge contracts (v1)."""

from theforge.contracts.base import ContractError, from_dict, to_dict
from theforge.contracts.context import ContextFile, ContextPack, ExcludedFile
from theforge.contracts.envelope import (
    PROTOCOL_V1,
    ExecuteRequest,
    HealthCheck,
    HealthReport,
    Request,
    Response,
    new_request_id,
)
from theforge.contracts.manifest import Capability, ExecutionInfo, ForgeManifest, Signals
from theforge.contracts.receipt import ExecutionReceipt, ReceiptInputs, ReceiptProvider
from theforge.contracts.result import (
    Artifact,
    Evidence,
    ExecutionResult,
    Finding,
    Location,
    Metric,
    Metrics,
)
from theforge.contracts.routing import (
    Candidate,
    Confidence,
    MatchedSignals,
    RoutingDecision,
    Selection,
)
from theforge.contracts.task import TaskSpec
from theforge.contracts.types import ErrorInfo, Producer

__all__ = [
    "PROTOCOL_V1", "Artifact", "Candidate", "Capability", "Confidence", "ContextFile",
    "ContextPack", "ContractError", "ErrorInfo", "Evidence", "ExcludedFile", "ExecuteRequest",
    "ExecutionInfo", "ExecutionReceipt", "ExecutionResult", "Finding", "ForgeManifest",
    "HealthCheck", "HealthReport", "Location", "MatchedSignals", "Metric", "Metrics",
    "Producer", "ReceiptInputs", "ReceiptProvider", "Request", "Response", "RoutingDecision",
    "Selection", "Signals", "TaskSpec", "from_dict", "new_request_id", "to_dict",
]
```

- [ ] **Step 12: `src/theforge/meta.py` e `src/theforge/errors.py`**

```python
"""Identity of The Forge as a contract producer."""

from theforge import __version__
from theforge.contracts.types import Producer

VERSION = __version__
PRODUCER = Producer(id="theforge", version=VERSION)
```

```python
"""User-facing error types mapped to CLI exit codes."""


class ForgeError(Exception):
    """Base class for expected, user-facing failures."""


class UsageError(ForgeError):
    """Invalid input or workspace state (exit 2)."""


class PersistenceError(ForgeError):
    """A run or cache file could not be written (exit 5)."""
```

- [ ] **Step 13: Ver passar**

Run: `$PY -m pytest tests/test_contracts_models.py`
Expected: `17 passed`

- [ ] **Step 14: Commit**

```bash
git add src/theforge tests/test_contracts_models.py
git commit -m "feat(contracts): add v1 manifest, task, routing, context, result, receipt and envelopes"
```

---
### Task 5: Segurança — redaction, env allowlist, guardas de path

**Files:**
- Create: `src/theforge/security/__init__.py`, `redact.py`, `env.py`, `paths.py`
- Test: `tests/test_security.py`

- [ ] **Step 1: Teste falhando** — `tests/test_security.py`

```python
import pytest
from hypothesis import given
from hypothesis import strategies as st

from theforge.security.env import safe_env
from theforge.security.paths import is_secret_name, resolve_inside
from theforge.security.redact import REDACTED, redact, redact_text


@pytest.mark.parametrize(
    ("raw", "leaked"),
    [
        ("key AKIAABCDEFGHIJKLMNOP here", "AKIAABCDEFGHIJKLMNOP"),
        ("token=abc123secretvalue", "abc123secretvalue"),
        ("password: hunter2xyz", "hunter2xyz"),
        ("AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMIK7MDENGbPxRfiCYEXAMPLEKEY",
         "wJalrXUtnFEMIK7MDENGbPxRfiCYEXAMPLEKEY"),
        ("Authorization: Bearer abcdefghijklmnopqrstuvwxyz012345",
         "abcdefghijklmnopqrstuvwxyz012345"),
        ("ghp_" + "a" * 36, "a" * 36),
        ("-----BEGIN RSA PRIVATE KEY-----\nMIIE\n-----END RSA PRIVATE KEY-----", "MIIE"),
    ],
)
def test_redact_text_removes_secrets(raw: str, leaked: str) -> None:
    out = redact_text(raw)
    assert leaked not in out
    assert REDACTED in out


def test_redact_keeps_plain_text() -> None:
    assert redact_text("tokens: 5 files") == "tokens: 5 files"


@given(st.text())
def test_redact_text_is_idempotent(text: str) -> None:
    once = redact_text(text)
    assert redact_text(once) == once


def test_redact_structure_and_sensitive_keys() -> None:
    data = {"intent": "password=hunter2xyz", "nested": [{"api_key": "plain"}], "count": 3}
    assert redact(data) == {
        "intent": f"password={REDACTED}", "nested": [{"api_key": REDACTED}], "count": 3,
    }


def test_safe_env_drops_credentials() -> None:
    env = safe_env({
        "PATH": "/bin", "AWS_SECRET_ACCESS_KEY": "x", "GITHUB_TOKEN": "y",
        "SystemRoot": "C:\\Windows",
    })
    assert env["PATH"] == "/bin"
    assert env["SystemRoot"] == "C:\\Windows"
    assert "AWS_SECRET_ACCESS_KEY" not in env and "GITHUB_TOKEN" not in env
    assert env["PYTHONIOENCODING"] == "utf-8"


@pytest.mark.parametrize(
    ("name", "secret"),
    [(".env", True), (".env.local", True), ("id_rsa", True), ("server.pem", True),
     ("creds.key", True), ("credentials.json", True), ("notes.txt", False),
     ("environment.py", False)],
)
def test_secret_names(name: str, secret: bool) -> None:
    assert is_secret_name(name) is secret


def test_resolve_inside(tmp_path) -> None:
    (tmp_path / "a.txt").write_text("x")
    assert resolve_inside(tmp_path, tmp_path / "a.txt") == (tmp_path / "a.txt").resolve()
    assert resolve_inside(tmp_path, tmp_path / ".." / "x") is None
    assert resolve_inside(tmp_path, tmp_path / "missing") is None


def test_resolve_inside_rejects_symlink_escape(tmp_path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "s.txt").write_text("s")
    root = tmp_path / "root"
    root.mkdir()
    try:
        (root / "link.txt").symlink_to(outside / "s.txt")
    except OSError:
        pytest.skip("symlinks not permitted on this host")
    assert resolve_inside(root, root / "link.txt") is None
```

- [ ] **Step 2: Ver falhar**

Run: `$PY -m pytest tests/test_security.py`
Expected: FAIL `ModuleNotFoundError: No module named 'theforge.security'`

- [ ] **Step 3: Implementar**

`src/theforge/security/__init__.py`:

```python
"""Security primitives: redaction, environment scrubbing, path guards."""
```

`src/theforge/security/redact.py`:

```python
"""Secret redaction applied before anything is persisted or echoed from providers."""

import re
from typing import Any

REDACTED = "[REDACTED]"

_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
     REDACTED),
    (re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"), REDACTED),
    (re.compile(r"\bghp_[A-Za-z0-9]{36}\b"), REDACTED),
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{22,}\b"), REDACTED),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{20,}"), REDACTED),
    (re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"), REDACTED),
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/-]{20,}=*"), REDACTED),
    (re.compile(
        r"(?i)\b(api[_-]?key|secret|token|password|passwd|client_secret"
        r"|aws_secret_access_key|aws_session_token)(\s*[:=]\s*)(?!\[REDACTED\])[^\s'\",;]+"
    ), r"\1\2" + REDACTED),
)

SENSITIVE_KEYS = frozenset({
    "password", "passwd", "secret", "token", "api_key", "apikey", "authorization",
    "access_key", "secret_key", "client_secret", "aws_secret_access_key",
})


def redact_text(text: str) -> str:
    for pattern, replacement in _PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def redact(value: Any) -> Any:
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            sensitive = str(key).lower() in SENSITIVE_KEYS and isinstance(item, str) and item
            out[key] = REDACTED if sensitive else redact(item)
        return out
    return value
```

`src/theforge/security/env.py`:

```python
"""Environment allowlist for provider subprocesses: credentials are never forwarded."""

import os
from collections.abc import Mapping

ALLOWED_ENV = frozenset({
    "PATH", "PATHEXT", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC",
    "HOME", "USERPROFILE", "TEMP", "TMP", "TMPDIR", "LANG", "LC_ALL",
})


def safe_env(source: Mapping[str, str] | None = None) -> dict[str, str]:
    src = os.environ if source is None else source
    env = {key: value for key, value in src.items() if key.upper() in ALLOWED_ENV}
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    return env
```

`src/theforge/security/paths.py`:

```python
"""Path guards: keep reads inside the workspace and away from secret files."""

from fnmatch import fnmatch
from pathlib import Path

IGNORED_DIRS = frozenset({
    ".git", ".forge", "node_modules", ".venv", "venv", "__pycache__", "dist", "build",
    ".mypy_cache", ".pytest_cache", ".ruff_cache", ".hypothesis",
})
SECRET_PATTERNS = (
    ".env", ".env.*", "*.pem", "*.key", "id_rsa*", "id_ed25519*", "*.pfx", "*.p12",
    "credentials*",
)


def is_secret_name(name: str) -> bool:
    lowered = name.lower()
    return any(fnmatch(lowered, pattern) for pattern in SECRET_PATTERNS)


def resolve_inside(root: Path, candidate: Path) -> Path | None:
    """Return the resolved path if it exists and stays inside root, else None."""
    try:
        resolved = candidate.resolve(strict=True)
    except (OSError, RuntimeError):
        return None
    root_resolved = root.resolve()
    if resolved == root_resolved or resolved.is_relative_to(root_resolved):
        return resolved
    return None
```

- [ ] **Step 4: Ver passar**

Run: `$PY -m pytest tests/test_security.py`
Expected: `20 passed` (ou `19 passed, 1 skipped` sem permissão de symlink)

- [ ] **Step 5: Commit**

```bash
git add src/theforge/security tests/test_security.py
git commit -m "feat(security): add secret redaction, env allowlist and path guards"
```

---

### Task 6: Negociação de protocolo, SubprocessTransport e bad-forge

**Files:**
- Create: `src/theforge/protocol/__init__.py`, `negotiate.py`, `transport.py`
- Create: `tests/helpers.py`, `tests/fixtures/providers/bad_forge.py`
- Test: `tests/test_protocol.py`

- [ ] **Step 1: Criar `tests/fixtures/providers/bad_forge.py`** (standalone, só stdlib)

```python
"""Misbehaving Forge Protocol provider for failure-mode tests (stdlib only).

argv: bad_forge.py MODE [PROVIDER_ID] OP
"""

import json
import os
import sys
import time

RESULT = {
    "schema": "theforge/ExecutionResult/v1",
    "created_at": "1970-01-01T00:00:00.000000Z",
    "status": "ok",
}


def main() -> int:
    mode, op = sys.argv[1], sys.argv[-1]
    pid = sys.argv[2] if len(sys.argv) > 3 else "bad-forge"
    producer = {"id": pid, "version": "0.0.1"}
    raw = sys.stdin.read()
    try:
        rid = json.loads(raw).get("request_id", "unknown")
    except (json.JSONDecodeError, AttributeError):
        rid = "unknown"
    proto = "forge/v9" if mode == "wrong-major" else "forge/v1"

    def reply(status, payload=None, error=None, request_id=None):
        sys.stdout.write(json.dumps({
            "protocol": proto, "kind": "Response", "request_id": request_id or rid,
            "producer": producer, "status": status, "payload": payload or {}, "error": error,
        }))
        return 0

    if op == "describe":
        if mode == "describe-crash":
            sys.stderr.write("describe failed\n")
            return 3
        cap_id = "Bad Id" if mode == "invalid-manifest" else "bad.thing"
        return reply("ok", {
            "schema": "theforge/ForgeManifest/v1", "id": pid, "version": "0.0.1",
            "protocols": [proto], "ops": ["describe", "health", "execute"],
            "domains": ["test"],
            "capabilities": [{
                "id": cap_id, "actions": ["run"], "default_action": "run",
                "state": "supported", "operation_class": "read_only",
                "signals": {"keywords": ["bad"], "file_globs": [], "dependencies": []},
            }],
        })
    if op == "health":
        if mode == "unhealthy":
            return reply("ok", {"status": "unavailable",
                                "checks": [{"name": "backend", "ok": False,
                                            "detail": "backend down"}]})
        return reply("ok", {"status": "ok", "checks": []})
    if op == "execute":
        if mode == "timeout":
            time.sleep(30)
        if mode == "crash":
            sys.stderr.write("boom token=supersecretvalue123\n")
            return 3
        if mode == "garbage":
            sys.stdout.write("this is not json")
            return 0
        if mode == "oversize":
            sys.stdout.write("x" * (9 * 1024 * 1024))
            return 0
        if mode == "mismatch":
            return reply("ok", dict(RESULT, producer=producer), request_id="nope")
        if mode == "bad-envelope":
            sys.stdout.write(json.dumps({"protocol": "forge/v1", "kind": "Response",
                                         "request_id": rid, "status": "ok"}))
            return 0
        if mode == "refuse":
            return reply("refused", error={"code": "BAD-REFUSED", "detail": "refused on purpose",
                                           "field": "capability",
                                           "unlock": "try another capability"})
        if mode == "bad-result":
            return reply("ok", {"status": "weird"})
        if mode == "env-probe":
            return reply("ok", {"env": sorted(os.environ)})
        if mode == "cwd-probe":
            return reply("ok", {"cwd": os.getcwd()})
        return reply("ok", dict(RESULT, producer=producer))
    return reply("refused", error={"code": "BAD-OP", "detail": op, "field": "op",
                                   "unlock": None})


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Criar `tests/helpers.py`** (completo; usado até o fim do plano)

```python
"""Shared test helpers: fixture provider argv, providers.toml writer, workspaces."""

import json
import sys
from pathlib import Path
from typing import Any

FIXTURES = Path(__file__).parent / "fixtures"
PROVIDERS = FIXTURES / "providers"


def fixture_argv(script: str, *extra: str) -> list[str]:
    return [sys.executable, str(PROVIDERS / script), *extra]


def bad_argv(mode: str, pid: str = "bad-forge") -> list[str]:
    return fixture_argv("bad_forge.py", mode, pid)


def bad_entry(mode: str, pid: str, trust: str = "local") -> dict[str, Any]:
    return {"id": pid, "argv": bad_argv(mode, pid), "trust": trust}


SPARK_ENTRY = {
    "id": "fixture-spark",
    "argv": fixture_argv("fixture_forge.py", str(PROVIDERS / "fixture-spark.json")),
    "trust": "local",
}
API_ENTRY = {
    "id": "fixture-api",
    "argv": fixture_argv("fixture_forge.py", str(PROVIDERS / "fixture-api.json")),
    "trust": "local",
}


def write_providers(forge_dir: Path, entries: list[dict[str, Any]]) -> None:
    lines: list[str] = []
    for entry in entries:
        lines += [
            "[[providers]]",
            f"id = {json.dumps(entry['id'])}",
            f"argv = {json.dumps(entry['argv'])}",
            f"trust = {json.dumps(entry.get('trust', 'local'))}",
            "",
        ]
    config = forge_dir / "config"
    config.mkdir(parents=True, exist_ok=True)
    (config / "providers.toml").write_text("\n".join(lines), encoding="utf-8")


def write_file(root: Path, rel: str, text: str = "") -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def make_workspace(root: Path, entries: list[dict[str, Any]]) -> Path:
    from theforge.state import init_workspace

    init_workspace(root)
    write_providers(root / ".forge", entries)
    return root / ".forge"


def case_a(root: Path) -> None:
    write_file(root, "jobs/orders_glue_job.py", "df = spark.read.parquet('s3://b/orders')\n")
    write_file(root, "requirements.txt", "pyspark==3.5.1\n")


def case_b(root: Path) -> None:
    write_file(
        root, "api/openapi.yaml",
        "openapi: 3.0.0\ninfo:\n  title: Orders\n  version: 1.0.0\npaths: {}\n",
    )
```

- [ ] **Step 3: Teste falhando** — `tests/test_protocol.py`

```python
from pathlib import Path

import pytest
from helpers import bad_argv

from theforge.protocol import SubprocessTransport, TransportError, choose_protocol


@pytest.mark.parametrize(
    ("offered", "expected"),
    [(["forge/v1"], "forge/v1"), (["forge/v1", "forge/v2"], "forge/v1"),
     (["forge/v9"], None), (["garbage"], None), ([], None)],
)
def test_choose_protocol(offered: list[str], expected: str | None) -> None:
    assert choose_protocol(offered) == expected


def test_describe_ok() -> None:
    resp = SubprocessTransport(bad_argv("ok")).call("describe", {}, timeout=10)
    assert resp.status == "ok" and resp.payload["id"] == "bad-forge"


def _failure(mode: str, timeout: float = 10) -> TransportError:
    with pytest.raises(TransportError) as info:
        SubprocessTransport(bad_argv(mode)).call("execute", {}, timeout=timeout)
    return info.value


@pytest.mark.parametrize(
    ("mode", "code"),
    [("crash", "FORGE-PROTO-EXIT"), ("garbage", "FORGE-PROTO-NOT-JSON"),
     ("oversize", "FORGE-PROTO-OVERSIZE"), ("mismatch", "FORGE-PROTO-MISMATCH"),
     ("wrong-major", "FORGE-PROTO-VERSION"), ("bad-envelope", "FORGE-PROTO-SCHEMA")],
)
def test_transport_failures(mode: str, code: str) -> None:
    assert _failure(mode).code == code


def test_timeout() -> None:
    assert _failure("timeout", timeout=1).code == "FORGE-PROTO-TIMEOUT"


def test_crash_stderr_is_redacted() -> None:
    assert "supersecretvalue123" not in _failure("crash").detail


def test_spawn_failure() -> None:
    with pytest.raises(TransportError) as info:
        SubprocessTransport(["definitely-not-a-real-forge-binary"]).call(
            "describe", {}, timeout=5)
    assert info.value.code == "FORGE-PROTO-SPAWN"


def test_wrong_major_describe_allowed_without_protocol_check() -> None:
    resp = SubprocessTransport(bad_argv("wrong-major")).call(
        "describe", {}, timeout=10, check_protocol=False)
    assert resp.payload["protocols"] == ["forge/v9"]


def test_provider_env_is_scrubbed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "leakme")
    resp = SubprocessTransport(bad_argv("env-probe")).call("execute", {}, timeout=10)
    names = {name.upper() for name in resp.payload["env"]}
    assert "AWS_SECRET_ACCESS_KEY" not in names
    assert "PATH" in names


def test_cwd_is_honored(tmp_path: Path) -> None:
    resp = SubprocessTransport(bad_argv("cwd-probe")).call(
        "execute", {}, timeout=10, cwd=tmp_path)
    assert Path(resp.payload["cwd"]).resolve() == tmp_path.resolve()


def test_empty_argv_rejected() -> None:
    with pytest.raises(ValueError, match="argv"):
        SubprocessTransport([])
```

- [ ] **Step 4: Ver falhar**

Run: `$PY -m pytest tests/test_protocol.py`
Expected: FAIL `ModuleNotFoundError: No module named 'theforge.protocol'`

- [ ] **Step 5: `src/theforge/protocol/negotiate.py`**

```python
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
```

- [ ] **Step 6: `src/theforge/protocol/transport.py`**

```python
"""Subprocess transport for Forge Protocol v1: `<argv> <op>`, JSON over stdin/stdout."""

import json
import subprocess
import threading
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import IO, Any, Protocol

from theforge.contracts import (
    PROTOCOL_V1,
    ContractError,
    Request,
    Response,
    from_dict,
    new_request_id,
    to_dict,
)
from theforge.contracts.canonical import canonical_json
from theforge.security.env import safe_env
from theforge.security.redact import redact_text

MAX_STDOUT_BYTES = 8 * 1024 * 1024
MAX_STDERR_BYTES = 64 * 1024
_CHUNK = 65536


class TransportError(Exception):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


class ProviderTransport(Protocol):
    def call(
        self, op: str, payload: dict[str, Any], *, timeout: float,
        cwd: Path | None = None, check_protocol: bool = True,
    ) -> Response: ...


TransportFactory = Callable[[Sequence[str]], ProviderTransport]


class SubprocessTransport:
    def __init__(
        self, argv: Sequence[str], *, protocol: str = PROTOCOL_V1,
        max_stdout: int = MAX_STDOUT_BYTES,
    ) -> None:
        if not argv:
            raise ValueError("provider argv must not be empty")
        self.argv = list(argv)
        self.protocol = protocol
        self.max_stdout = max_stdout

    def call(
        self, op: str, payload: dict[str, Any], *, timeout: float,
        cwd: Path | None = None, check_protocol: bool = True,
    ) -> Response:
        request = Request(protocol=self.protocol, op=op, request_id=new_request_id(),
                          payload=payload)
        stdout = self._run(op, canonical_json(to_dict(request)).encode("utf-8"), timeout, cwd)
        try:
            data = json.loads(stdout.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise TransportError("FORGE-PROTO-NOT-JSON", f"{op}: stdout is not JSON ({exc})") \
                from exc
        try:
            response = from_dict(Response, data)
        except ContractError as exc:
            raise TransportError("FORGE-PROTO-SCHEMA", f"{op}: {exc}") from exc
        if response.request_id != request.request_id:
            raise TransportError(
                "FORGE-PROTO-MISMATCH",
                f"{op}: response request_id {response.request_id!r} "
                f"!= {request.request_id!r}",
            )
        if check_protocol and response.protocol != self.protocol:
            raise TransportError(
                "FORGE-PROTO-VERSION",
                f"{op}: response protocol {response.protocol!r} != {self.protocol!r}",
            )
        return response

    def _run(self, op: str, stdin_bytes: bytes, timeout: float, cwd: Path | None) -> bytes:
        try:
            proc = subprocess.Popen(
                [*self.argv, op], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, cwd=cwd, env=safe_env(), shell=False,
            )
        except OSError as exc:
            raise TransportError("FORGE-PROTO-SPAWN", f"cannot start {self.argv[0]!r}: {exc}") \
                from exc
        if proc.stdin is None or proc.stdout is None or proc.stderr is None:
            proc.kill()
            raise TransportError("FORGE-PROTO-SPAWN", "provider pipes unavailable")
        out = bytearray()
        err = bytearray()
        oversize = threading.Event()

        def pump_out(stream: IO[bytes]) -> None:
            while chunk := stream.read(_CHUNK):
                if len(out) + len(chunk) > self.max_stdout:
                    oversize.set()
                    proc.kill()
                    return
                out.extend(chunk)

        def pump_err(stream: IO[bytes]) -> None:
            while chunk := stream.read(_CHUNK):
                room = MAX_STDERR_BYTES - len(err)
                if room > 0:
                    err.extend(chunk[:room])

        threads = [
            threading.Thread(target=pump_out, args=(proc.stdout,), daemon=True),
            threading.Thread(target=pump_err, args=(proc.stderr,), daemon=True),
        ]
        for thread in threads:
            thread.start()
        try:
            proc.stdin.write(stdin_bytes)
            proc.stdin.close()
        except OSError:
            pass
        try:
            returncode = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            proc.kill()
            proc.wait()
            for thread in threads:
                thread.join(timeout=5)
            raise TransportError("FORGE-PROTO-TIMEOUT", f"{op}: no response within {timeout:g}s") \
                from exc
        for thread in threads:
            thread.join(timeout=5)
        if oversize.is_set():
            raise TransportError(
                "FORGE-PROTO-OVERSIZE", f"{op}: stdout exceeded {self.max_stdout} bytes")
        if returncode != 0:
            tail = redact_text(err.decode("utf-8", errors="replace").strip()[-500:])
            raise TransportError(
                "FORGE-PROTO-EXIT", f"{op}: exit code {returncode}; stderr: {tail}")
        return bytes(out)
```

- [ ] **Step 7: `src/theforge/protocol/__init__.py`**

```python
"""Forge Protocol v1 transport and negotiation."""

from theforge.protocol.negotiate import SUPPORTED_PROTOCOLS, choose_protocol, major
from theforge.protocol.transport import (
    ProviderTransport,
    SubprocessTransport,
    TransportError,
    TransportFactory,
)

__all__ = [
    "SUPPORTED_PROTOCOLS", "ProviderTransport", "SubprocessTransport", "TransportError",
    "TransportFactory", "choose_protocol", "major",
]
```

- [ ] **Step 8: Ver passar**

Run: `$PY -m pytest tests/test_protocol.py`
Expected: `19 passed`

- [ ] **Step 9: Commit**

```bash
git add src/theforge/protocol tests/helpers.py tests/fixtures tests/test_protocol.py
git commit -m "feat(protocol): add subprocess transport with timeouts, size limits and negotiation"
```

---
### Task 7: echo-forge, fixture providers e conformance suite

**Files:**
- Create: `src/theforge/providers/__init__.py`, `src/theforge/providers/echo/__init__.py`, `provider.py`, `__main__.py`
- Create: `tests/fixtures/providers/fixture_forge.py`, `fixture-spark.json`, `fixture-api.json`
- Test: `tests/test_conformance.py`

- [ ] **Step 1: `tests/fixtures/providers/fixture-spark.json`**

```json
{
  "schema": "theforge/ForgeManifest/v1",
  "id": "fixture-spark",
  "version": "0.0.1",
  "protocols": ["forge/v1"],
  "ops": ["describe", "health", "execute"],
  "domains": ["data-engineering"],
  "capabilities": [
    {
      "id": "spark.performance",
      "actions": ["diagnose", "review", "optimize"],
      "default_action": "diagnose",
      "state": "supported",
      "operation_class": "read_only",
      "description": "Diagnose slow Spark and Glue jobs",
      "signals": {
        "keywords": ["spark", "pyspark", "glue", "lento", "slow", "performance", "job"],
        "file_globs": ["*glue*.py", "*_job.py", "*.scala"],
        "dependencies": ["pyspark", "awsglue"]
      }
    }
  ]
}
```

- [ ] **Step 2: `tests/fixtures/providers/fixture-api.json`**

```json
{
  "schema": "theforge/ForgeManifest/v1",
  "id": "fixture-api",
  "version": "0.0.1",
  "protocols": ["forge/v1"],
  "ops": ["describe", "health", "execute"],
  "domains": ["api-engineering"],
  "capabilities": [
    {
      "id": "api.contract",
      "actions": ["review", "lint"],
      "default_action": "review",
      "state": "supported",
      "operation_class": "read_only",
      "description": "Review OpenAPI contracts",
      "signals": {
        "keywords": ["openapi", "contrato", "contract", "api", "swagger"],
        "file_globs": ["openapi.yaml", "openapi.json", "*.openapi.yaml", "swagger.json"],
        "dependencies": ["fastapi", "flask"]
      }
    }
  ]
}
```

- [ ] **Step 3: `tests/fixtures/providers/fixture_forge.py`** (standalone, prova neutralidade de linguagem)

```python
"""Minimal standalone Forge Protocol v1 provider driven by a manifest file (stdlib only).

argv: fixture_forge.py MANIFEST_JSON OP
"""

import json
import sys
from pathlib import Path


def main() -> int:
    manifest = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    op = sys.argv[2]
    producer = {"id": manifest["id"], "version": manifest["version"]}
    rid = "unknown"

    def reply(status, payload=None, error=None):
        sys.stdout.write(json.dumps({
            "protocol": "forge/v1", "kind": "Response", "request_id": rid,
            "producer": producer, "status": status, "payload": payload or {}, "error": error,
        }))
        return 0

    def err(code, detail, field=None):
        return {"code": code, "detail": detail, "field": field, "unlock": None}

    try:
        req = json.loads(sys.stdin.read())
        rid = str(req["request_id"])
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        return reply("error", error=err("FIXTURE-REQ-INVALID", str(exc)))
    if op != "describe" and req.get("protocol") != "forge/v1":
        return reply("refused", error=err("FIXTURE-PROTO-UNSUPPORTED",
                                          str(req.get("protocol")), "protocol"))
    if op == "describe":
        return reply("ok", manifest)
    if op == "health":
        return reply("ok", {"status": "ok", "checks": [{"name": "fixture", "ok": True}]})
    if op == "execute":
        payload = req.get("payload") or {}
        cap = payload.get("capability")
        if cap not in {c["id"] for c in manifest["capabilities"]}:
            return reply("refused", error=err("FIXTURE-CAP-UNSUPPORTED", str(cap), "capability"))
        files = [f["path"] for f in payload["context"]["files"]]
        return reply("ok", {
            "schema": "theforge/ExecutionResult/v1", "producer": producer,
            "created_at": "1970-01-01T00:00:00.000000Z", "status": "ok",
            "findings": [{"id": "f1", "title": f"{manifest['id']} handled "
                                               f"{cap}:{payload.get('action')}",
                          "severity": "info", "evidence_ids": ["e1"]}],
            "evidence": [{"id": "e1", "epistemic": "observed", "subject": cap,
                          "claim": f"received {len(files)} context files",
                          "producer": producer}],
        })
    return reply("refused", error=err("FIXTURE-OP-UNSUPPORTED", op, "op"))


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Teste falhando** — `tests/test_conformance.py`

```python
"""Forge Protocol v1 conformance suite, parametrized by provider argv.

To certify a new provider, add its argv to PROVIDER_ARGVS.
"""

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from helpers import PROVIDERS, fixture_argv

from theforge.contracts import (
    ContextPack,
    ExecuteRequest,
    ExecutionResult,
    ForgeManifest,
    HealthReport,
    Response,
    TaskSpec,
    from_dict,
    to_dict,
)
from theforge.contracts.canonical import utc_now
from theforge.meta import PRODUCER

PROVIDER_ARGVS = {
    "echo-forge": [sys.executable, "-m", "theforge.providers.echo"],
    "fixture-spark": fixture_argv("fixture_forge.py", str(PROVIDERS / "fixture-spark.json")),
    "fixture-api": fixture_argv("fixture_forge.py", str(PROVIDERS / "fixture-api.json")),
}
pytestmark = pytest.mark.parametrize(
    "argv", list(PROVIDER_ARGVS.values()), ids=list(PROVIDER_ARGVS))


def raw(argv: list[str], op: str, body: bytes) -> tuple[int, dict[str, Any]]:
    proc = subprocess.run([*argv, op], input=body, capture_output=True, timeout=30)
    return proc.returncode, json.loads(proc.stdout.decode("utf-8"))


def request(op: str, payload: dict[str, Any] | None = None, protocol: str = "forge/v1") -> bytes:
    return json.dumps({"protocol": protocol, "kind": "Request", "op": op,
                       "request_id": "r_conformance", "payload": payload or {}}).encode()


def manifest_of(argv: list[str]) -> ForgeManifest:
    _, data = raw(argv, "describe", request("describe"))
    return from_dict(ForgeManifest, data["payload"])


def execute_payload(root: Path, capability: str, action: str) -> dict[str, Any]:
    task = TaskSpec(producer=PRODUCER, created_at=utc_now(), id="t1", intent="conformance",
                    workspace_root=str(root))
    pack = ContextPack(producer=PRODUCER, created_at=utc_now(), status="complete",
                       task_id="t1", provider_id="x", root=str(root), budget_bytes=1024)
    return to_dict(ExecuteRequest(task=task, capability=capability, action=action, context=pack))


def test_describe_returns_valid_manifest(argv: list[str]) -> None:
    code, data = raw(argv, "describe", request("describe"))
    assert code == 0
    resp = from_dict(Response, data)
    assert resp.status == "ok"
    assert resp.request_id == "r_conformance"
    assert resp.protocol == "forge/v1"
    manifest = from_dict(ForgeManifest, resp.payload)
    assert "forge/v1" in manifest.protocols
    assert {"describe", "health", "execute"} <= set(manifest.ops)
    assert resp.producer.id == manifest.id


def test_health(argv: list[str]) -> None:
    code, data = raw(argv, "health", request("health"))
    resp = from_dict(Response, data)
    assert code == 0 and resp.status == "ok"
    assert from_dict(HealthReport, resp.payload).status in ("ok", "degraded")


def test_execute_every_capability(argv: list[str], tmp_path: Path) -> None:
    for cap in manifest_of(argv).capabilities:
        body = request("execute", execute_payload(tmp_path, cap.id, cap.default_action))
        code, data = raw(argv, "execute", body)
        resp = from_dict(Response, data)
        assert code == 0 and resp.status in ("ok", "partial")
        assert from_dict(ExecutionResult, resp.payload).producer.id == resp.producer.id


def test_unsupported_capability_is_refused(argv: list[str], tmp_path: Path) -> None:
    body = request("execute", execute_payload(tmp_path, "zzz.unknown", "run"))
    code, data = raw(argv, "execute", body)
    resp = from_dict(Response, data)
    assert code == 0 and resp.status == "refused"
    assert resp.error is not None and resp.error.code


def test_invalid_request_yields_error_response(argv: list[str]) -> None:
    code, data = raw(argv, "execute", b"{not json")
    resp = from_dict(Response, data)
    assert code == 0 and resp.status in ("error", "refused") and resp.error is not None


def test_unknown_op_is_refused(argv: list[str]) -> None:
    code, data = raw(argv, "teleport", request("teleport"))
    assert code == 0 and from_dict(Response, data).status == "refused"


def test_incompatible_protocol_is_refused(argv: list[str]) -> None:
    code, data = raw(argv, "health", request("health", protocol="forge/v9"))
    assert code == 0 and from_dict(Response, data).status == "refused"


def test_echo_confirms_context_hashes(argv: list[str], tmp_path: Path) -> None:
    if argv != PROVIDER_ARGVS["echo-forge"]:
        pytest.skip("echo-forge specific")
    from theforge.contracts import ContextFile
    from theforge.contracts.canonical import sha256_hex

    (tmp_path / "notes.txt").write_bytes(b"hello")
    payload = execute_payload(tmp_path, "demo.echo", "echo")
    payload["context"]["files"] = [to_dict(ContextFile(
        path="notes.txt", sha256=sha256_hex(b"hello"), bytes=5))]
    _, data = raw(argv, "execute", request("execute", payload))
    result = from_dict(ExecutionResult, data["payload"])
    assert [e.epistemic for e in result.evidence] == ["confirmed"]
```

- [ ] **Step 5: Ver falhar**

Run: `$PY -m pytest tests/test_conformance.py`
Expected: FAIL nos casos `echo-forge` (`No module named theforge.providers`); casos fixture passam exceto o skip.

- [ ] **Step 6: `src/theforge/providers/__init__.py` e `src/theforge/providers/echo/__init__.py`**

```python
"""Builtin Forge Protocol providers."""
```

```python
"""echo-forge: native Forge Protocol v1 provider that proves the protocol end to end."""
```

- [ ] **Step 7: `src/theforge/providers/echo/provider.py`**

```python
"""echo-forge request handling. Pure function: (op, raw stdin) -> response dict."""

import json
from pathlib import Path
from typing import Any

from theforge.contracts import (
    PROTOCOL_V1,
    Capability,
    ContractError,
    ErrorInfo,
    Evidence,
    ExecuteRequest,
    ExecutionResult,
    Finding,
    ForgeManifest,
    HealthCheck,
    HealthReport,
    Location,
    Producer,
    Request,
    Response,
    Signals,
    from_dict,
    to_dict,
)
from theforge.contracts.canonical import sha256_hex, utc_now
from theforge.contracts.types import Epistemic, ResponseStatus
from theforge.meta import VERSION
from theforge.security.paths import resolve_inside

PRODUCER = Producer(id="echo-forge", version=VERSION)
DOC_GLOBS = ["*.txt", "*.md"]
UNLOCK_CAPABILITIES = "theforge capabilities list --provider echo-forge"

MANIFEST = ForgeManifest(
    id="echo-forge",
    version=VERSION,
    protocols=[PROTOCOL_V1],
    ops=["describe", "health", "execute"],
    domains=["demo"],
    capabilities=[
        Capability(
            id="demo.echo", actions=["echo"], default_action="echo", state="supported",
            operation_class="read_only",
            description="Echo the task intent and confirm context file hashes.",
            signals=Signals(keywords=["echo", "eco", "demo"], file_globs=list(DOC_GLOBS)),
        ),
        Capability(
            id="demo.inspect", actions=["inspect"], default_action="inspect",
            state="supported", operation_class="read_only",
            description="List context files with their sizes.",
            signals=Signals(keywords=["inspect", "inspecionar", "listar"],
                            file_globs=list(DOC_GLOBS)),
        ),
    ],
    limitations=["demonstration provider; performs no domain analysis"],
)


def _respond(
    request_id: str, status: ResponseStatus, *, payload: dict[str, Any] | None = None,
    error: ErrorInfo | None = None,
) -> dict[str, Any]:
    return to_dict(Response(request_id=request_id, producer=PRODUCER, status=status,
                            payload=payload or {}, error=error))


def handle(op: str, raw: bytes) -> dict[str, Any]:
    try:
        data = json.loads(raw.decode("utf-8") or "{}")
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return _respond("unknown", "error", error=ErrorInfo(
            code="ECHO-REQ-INVALID", detail=f"request is not JSON: {exc}"))
    request_id = str(data.get("request_id", "unknown")) if isinstance(data, dict) else "unknown"
    try:
        request = from_dict(Request, data)
    except ContractError as exc:
        return _respond(request_id, "error",
                        error=ErrorInfo(code="ECHO-REQ-INVALID", detail=str(exc)))
    if op != "describe" and request.protocol != PROTOCOL_V1:
        return _respond(request_id, "refused", error=ErrorInfo(
            code="ECHO-PROTO-UNSUPPORTED", detail=f"protocol {request.protocol!r} not supported",
            field="protocol", unlock=f"use {PROTOCOL_V1}"))
    if request.op != op:
        return _respond(request_id, "error", error=ErrorInfo(
            code="ECHO-REQ-INVALID", detail=f"envelope op {request.op!r} != invoked op {op!r}",
            field="op"))
    if op == "describe":
        return _respond(request_id, "ok", payload=to_dict(MANIFEST))
    if op == "health":
        report = HealthReport(status="ok", checks=[HealthCheck(name="echo", ok=True)])
        return _respond(request_id, "ok", payload=to_dict(report))
    if op == "execute":
        return _execute(request_id, request.payload)
    return _respond(request_id, "refused", error=ErrorInfo(
        code="ECHO-OP-UNSUPPORTED", detail=f"op {op!r} not supported", field="op",
        unlock="ops: describe, health, execute"))


def _execute(request_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        req = from_dict(ExecuteRequest, payload, "$.payload")
    except ContractError as exc:
        return _respond(request_id, "error", error=ErrorInfo(
            code="ECHO-REQ-INVALID", detail=str(exc), field="payload"))
    capability = MANIFEST.capability(req.capability)
    if capability is None or req.action not in capability.actions:
        return _respond(request_id, "refused", error=ErrorInfo(
            code="ECHO-CAP-UNSUPPORTED",
            detail=f"{req.capability}:{req.action} not offered by echo-forge",
            field="capability", unlock=UNLOCK_CAPABILITIES))
    root = Path(req.task.workspace_root)
    evidence: list[Evidence] = []
    for index, item in enumerate(req.context.files, start=1):
        inside = resolve_inside(root, root / item.path)
        actual: str | None = None
        if inside is not None:
            try:
                actual = sha256_hex(inside.read_bytes())
            except OSError:
                actual = None
        epistemic: Epistemic
        if actual is None:
            epistemic, claim = "unresolved", "file missing, unreadable or outside workspace root"
        elif capability.id == "demo.inspect":
            epistemic, claim = "observed", f"{item.bytes} bytes"
        elif actual == item.sha256:
            epistemic, claim = "confirmed", "content hash matches context pack"
        else:
            epistemic, claim = "unresolved", "content hash differs from context pack"
        evidence.append(Evidence(id=f"e{index}", epistemic=epistemic, subject=item.path,
                                 claim=claim, producer=PRODUCER,
                                 location=Location(path=item.path), hash=actual))
    title = (f"echo: {req.task.intent}" if capability.id == "demo.echo"
             else f"inspect: {len(req.context.files)} files")
    result = ExecutionResult(
        producer=PRODUCER, created_at=utc_now(), status="ok",
        findings=[Finding(id="f1", title=title, evidence_ids=[e.id for e in evidence])],
        evidence=evidence, limitations=list(MANIFEST.limitations),
    )
    return _respond(request_id, "ok", payload=to_dict(result))
```

- [ ] **Step 8: `src/theforge/providers/echo/__main__.py`**

```python
"""Entry point: python -m theforge.providers.echo <op>"""

import sys

from theforge.contracts.canonical import canonical_json
from theforge.providers.echo.provider import handle


def main() -> int:
    op = sys.argv[1] if len(sys.argv) > 1 else ""
    response = handle(op, sys.stdin.buffer.read())
    sys.stdout.buffer.write(canonical_json(response).encode("utf-8"))
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 9: Ver passar**

Run: `$PY -m pytest tests/test_conformance.py`
Expected: `22 passed, 2 skipped`

- [ ] **Step 10: Commit**

```bash
git add src/theforge/providers tests/fixtures tests/test_conformance.py
git commit -m "feat(providers): add native echo-forge, fixture providers and conformance suite"
```

---

### Task 8: Configuração do registry (fontes de providers)

**Files:**
- Create: `src/theforge/registry/__init__.py`, `src/theforge/registry/config.py`
- Test: `tests/test_registry_config.py`

- [ ] **Step 1: Teste falhando** — `tests/test_registry_config.py`

```python
import sys
from pathlib import Path

import pytest

from theforge.errors import UsageError
from theforge.registry.config import builtin_entries, resolve_entries, user_config_dir


def test_builtin_echo_entry() -> None:
    entry = builtin_entries()[0]
    assert entry.id == "echo-forge" and entry.trust == "builtin"
    assert entry.argv[0] == sys.executable


def test_project_overrides_user_and_expands_python(tmp_path: Path) -> None:
    user = tmp_path / "user"
    user.mkdir()
    forge = tmp_path / ".forge"
    (forge / "config").mkdir(parents=True)
    (user / "providers.toml").write_text(
        '[[providers]]\nid = "x-forge"\nargv = ["x"]\ntrust = "trusted"\n', encoding="utf-8")
    (forge / "config" / "providers.toml").write_text(
        '[[providers]]\nid = "x-forge"\nargv = ["{python}", "x.py"]\n', encoding="utf-8")
    entries = {e.id: e for e in resolve_entries(forge, user)}
    assert entries["x-forge"].source == "project"
    assert entries["x-forge"].trust == "unverified"
    assert entries["x-forge"].argv == [sys.executable, "x.py"]
    assert "echo-forge" in entries


def _project(tmp_path: Path, body: str) -> Path:
    forge = tmp_path / ".forge"
    (forge / "config").mkdir(parents=True)
    (forge / "config" / "providers.toml").write_text(body, encoding="utf-8")
    return forge


def test_builtin_trust_is_reserved(tmp_path: Path) -> None:
    forge = _project(tmp_path, '[[providers]]\nid = "x"\nargv = ["x"]\ntrust = "builtin"\n')
    with pytest.raises(UsageError, match="reserved"):
        resolve_entries(forge, tmp_path / "none")


def test_empty_argv_rejected(tmp_path: Path) -> None:
    forge = _project(tmp_path, '[[providers]]\nid = "x"\nargv = []\n')
    with pytest.raises(UsageError, match="argv"):
        resolve_entries(forge, tmp_path / "none")


def test_malformed_toml(tmp_path: Path) -> None:
    forge = _project(tmp_path, "[[providers]\n")
    with pytest.raises(UsageError, match="cannot read"):
        resolve_entries(forge, tmp_path / "none")


def test_user_config_dir_override(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("THEFORGE_CONFIG_DIR", str(tmp_path))
    assert user_config_dir() == tmp_path
```

- [ ] **Step 2: Ver falhar**

Run: `$PY -m pytest tests/test_registry_config.py`
Expected: FAIL `ModuleNotFoundError: No module named 'theforge.registry'`

- [ ] **Step 3: `src/theforge/registry/config.py`**

```python
"""Provider entries from builtin, user and project sources (later wins by id)."""

import os
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from theforge.contracts import ContractError, from_dict
from theforge.contracts.manifest import PROVIDER_ID
from theforge.contracts.types import TrustLevel
from theforge.errors import UsageError

Source = Literal["builtin", "user", "project"]
PROVIDERS_FILE = "providers.toml"
PYTHON_PLACEHOLDER = "{python}"


@dataclass(frozen=True, kw_only=True)
class ProviderEntry:
    id: str
    argv: list[str]
    trust: TrustLevel = "unverified"
    source: Source = "project"

    def __post_init__(self) -> None:
        if not PROVIDER_ID.match(self.id):
            raise ContractError(f"invalid provider id {self.id!r}")
        if not self.argv:
            raise ContractError(f"provider {self.id}: argv must not be empty")


def builtin_entries() -> list[ProviderEntry]:
    return [ProviderEntry(id="echo-forge", argv=[sys.executable, "-m", "theforge.providers.echo"],
                          trust="builtin", source="builtin")]


def user_config_dir() -> Path:
    override = os.environ.get("THEFORGE_CONFIG_DIR")
    if override:
        return Path(override)
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        base = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
        return base / "theforge"
    xdg = os.environ.get("XDG_CONFIG_HOME")
    return (Path(xdg) if xdg else Path.home() / ".config") / "theforge"


def load_entries(path: Path, source: Source) -> list[ProviderEntry]:
    if not path.is_file():
        return []
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise UsageError(f"{path}: cannot read providers file ({exc})") from exc
    items = data.get("providers", [])
    if not isinstance(items, list):
        raise UsageError(f"{path}: 'providers' must be an array of tables")
    entries: list[ProviderEntry] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise UsageError(f"{path}: providers[{index}] must be a table")
        if item.get("trust") == "builtin":
            raise UsageError(f"{path}: providers[{index}]: trust 'builtin' is reserved")
        raw = {**item, "source": source}
        if isinstance(raw.get("argv"), list):
            raw["argv"] = [sys.executable if a == PYTHON_PLACEHOLDER else a for a in raw["argv"]]
        try:
            entries.append(from_dict(ProviderEntry, raw, f"{path.name}.providers[{index}]"))
        except ContractError as exc:
            raise UsageError(str(exc)) from exc
    return entries


def resolve_entries(forge_dir: Path | None, user_dir: Path | None = None) -> list[ProviderEntry]:
    merged: dict[str, ProviderEntry] = {e.id: e for e in builtin_entries()}
    for entry in load_entries((user_dir or user_config_dir()) / PROVIDERS_FILE, "user"):
        merged[entry.id] = entry
    if forge_dir is not None:
        for entry in load_entries(forge_dir / "config" / PROVIDERS_FILE, "project"):
            merged[entry.id] = entry
    return sorted(merged.values(), key=lambda e: e.id)
```

- [ ] **Step 4: `src/theforge/registry/__init__.py`** (Task 9 expande)

```python
"""Provider registry: sources, describe/refresh, cache and trust."""

from theforge.registry.config import (
    ProviderEntry,
    builtin_entries,
    load_entries,
    resolve_entries,
    user_config_dir,
)

__all__ = [
    "ProviderEntry", "builtin_entries", "load_entries", "resolve_entries", "user_config_dir",
]
```

- [ ] **Step 5: Ver passar**

Run: `$PY -m pytest tests/test_registry_config.py`
Expected: `6 passed`

- [ ] **Step 6: Commit**

```bash
git add src/theforge/registry tests/test_registry_config.py
git commit -m "feat(registry): load provider entries from builtin, user and project sources"
```

---
### Task 9: Registry (describe, cache, trust) e health

**Files:**
- Create: `src/theforge/registry/registry.py`, `src/theforge/registry/health.py`
- Modify: `src/theforge/registry/__init__.py`
- Test: `tests/test_registry.py`

- [ ] **Step 1: Teste falhando** — `tests/test_registry.py`

```python
import json
from pathlib import Path
from typing import Any

import pytest
from helpers import SPARK_ENTRY, bad_argv, bad_entry, write_providers

from theforge.errors import UsageError
from theforge.registry import Registry, check_health


def make_forge(tmp_path: Path, entries: list[dict[str, Any]]) -> Path:
    forge = tmp_path / ".forge"
    write_providers(forge, entries)
    return forge


def test_refresh_describes_and_caches(tmp_path: Path) -> None:
    forge = make_forge(tmp_path, [SPARK_ENTRY])
    records = {r.entry.id: r for r in Registry(forge).refresh()}
    assert records["echo-forge"].state == "ready"
    assert records["fixture-spark"].state == "ready"
    assert records["fixture-spark"].protocol == "forge/v1"
    assert (forge / "registry" / "fixture-spark.json").is_file()


def test_records_use_cache_without_spawning(tmp_path: Path) -> None:
    forge = make_forge(tmp_path, [SPARK_ENTRY])
    Registry(forge).refresh()

    def boom(argv: object) -> Any:
        raise AssertionError("cache hit must not spawn providers")

    assert all(r.state == "ready" for r in Registry(forge, transport_factory=boom).records())


def test_tampered_cache_is_discarded(tmp_path: Path) -> None:
    forge = make_forge(tmp_path, [SPARK_ENTRY])
    Registry(forge).refresh()
    path = forge / "registry" / "fixture-spark.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["manifest"]["version"] = "6.6.6"
    path.write_text(json.dumps(doc), encoding="utf-8")
    registry = Registry(forge)
    record = registry.get("fixture-spark")
    assert record.manifest is not None and record.manifest.version == "0.0.1"
    assert any("fixture-spark" in warning for warning in registry.warnings)


def test_corrupt_cache_is_discarded(tmp_path: Path) -> None:
    forge = make_forge(tmp_path, [SPARK_ENTRY])
    Registry(forge).refresh()
    (forge / "registry" / "fixture-spark.json").write_text("{nope", encoding="utf-8")
    registry = Registry(forge)
    assert registry.get("fixture-spark").state == "ready"
    assert registry.warnings


@pytest.mark.parametrize(
    ("mode", "state"),
    [("wrong-major", "incompatible"), ("invalid-manifest", "invalid"),
     ("describe-crash", "unreachable")],
)
def test_bad_providers_degrade(tmp_path: Path, mode: str, state: str) -> None:
    record = Registry(make_forge(tmp_path, [bad_entry(mode, "bad-a")])).get("bad-a")
    assert record.state == state and record.error
    assert not record.routable(allow_unverified=True)


def test_manifest_id_must_match_entry(tmp_path: Path) -> None:
    entry = {"id": "impostor", "argv": bad_argv("ok", "bad-forge"), "trust": "local"}
    record = Registry(make_forge(tmp_path, [entry])).get("impostor")
    assert record.state == "invalid" and "does not match" in (record.error or "")


def test_blocked_is_never_spawned(tmp_path: Path) -> None:
    entry = {"id": "nope-forge", "argv": ["definitely-not-a-real-forge-binary"],
             "trust": "blocked"}
    record = Registry(make_forge(tmp_path, [entry])).get("nope-forge")
    assert record.state == "blocked" and not record.routable(allow_unverified=True)


def test_unverified_routable_only_with_opt_in(tmp_path: Path) -> None:
    record = Registry(make_forge(tmp_path, [bad_entry("ok", "bad-a", trust="unverified")])) \
        .get("bad-a")
    assert not record.routable() and record.routable(allow_unverified=True)


def test_unknown_provider(tmp_path: Path) -> None:
    with pytest.raises(UsageError, match="unknown provider"):
        Registry(make_forge(tmp_path, [])).get("nope")


def test_health_ok_and_unavailable(tmp_path: Path) -> None:
    registry = Registry(make_forge(tmp_path, [bad_entry("unhealthy", "bad-a")]))
    assert check_health(registry.get("echo-forge")).status == "ok"
    outcome = check_health(registry.get("bad-a"))
    assert outcome.status == "unavailable"
    assert outcome.error is not None and outcome.error.code == "FORGE-HEALTH-UNAVAILABLE"


def test_health_on_not_ready(tmp_path: Path) -> None:
    registry = Registry(make_forge(tmp_path, [bad_entry("describe-crash", "bad-a")]))
    outcome = check_health(registry.get("bad-a"))
    assert outcome.status == "error"
    assert outcome.error is not None and outcome.error.code == "FORGE-PROVIDER-NOT-READY"


def test_registry_without_forge_dir_still_describes() -> None:
    records = Registry(None).records()
    assert [r.entry.id for r in records] == ["echo-forge"] and records[0].state == "ready"
```

- [ ] **Step 2: Ver falhar**

Run: `$PY -m pytest tests/test_registry.py`
Expected: FAIL `ImportError: cannot import name 'Registry'`

- [ ] **Step 3: `src/theforge/registry/registry.py`**

```python
"""Registry: describe providers, negotiate protocol, cache ready manifests, apply trust."""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from theforge.contracts import ContractError, ForgeManifest, from_dict, to_dict
from theforge.contracts.canonical import sha256_of
from theforge.errors import PersistenceError, UsageError
from theforge.protocol import (
    SUPPORTED_PROTOCOLS,
    SubprocessTransport,
    TransportError,
    TransportFactory,
    choose_protocol,
)
from theforge.registry.config import ProviderEntry, resolve_entries

RecordState = Literal["ready", "incompatible", "invalid", "unreachable", "blocked"]
CACHE_SCHEMA = "theforge/RegistryCache/v1"
DESCRIBE_TIMEOUT = 10.0
ROUTABLE_TRUST = frozenset({"builtin", "trusted", "local"})


@dataclass(frozen=True, kw_only=True)
class RegistryRecord:
    entry: ProviderEntry
    state: RecordState
    manifest: ForgeManifest | None = None
    manifest_sha256: str | None = None
    protocol: str | None = None
    error: str | None = None

    def routable(self, allow_unverified: bool = False) -> bool:
        if self.state != "ready" or self.manifest is None:
            return False
        if self.entry.trust in ROUTABLE_TRUST:
            return True
        return allow_unverified and self.entry.trust == "unverified"


class Registry:
    def __init__(
        self, forge_dir: Path | None, *, user_dir: Path | None = None,
        transport_factory: TransportFactory = SubprocessTransport,
        timeout: float = DESCRIBE_TIMEOUT,
    ) -> None:
        self.forge_dir = forge_dir
        self.user_dir = user_dir
        self.transport_factory = transport_factory
        self.timeout = timeout
        self.warnings: list[str] = []

    def entries(self) -> list[ProviderEntry]:
        return resolve_entries(self.forge_dir, self.user_dir)

    def refresh(self) -> list[RegistryRecord]:
        records = [self._describe(entry) for entry in self.entries()]
        for record in records:
            self._write_cache(record)
        return records

    def records(self) -> list[RegistryRecord]:
        out: list[RegistryRecord] = []
        for entry in self.entries():
            record = self._read_cache(entry)
            if record is None:
                record = self._describe(entry)
                self._write_cache(record)
            out.append(record)
        return out

    def get(self, provider_id: str) -> RegistryRecord:
        for record in self.records():
            if record.entry.id == provider_id:
                return record
        raise UsageError(f"unknown provider {provider_id!r} (see `theforge registry list`)")

    def _describe(self, entry: ProviderEntry) -> RegistryRecord:
        if entry.trust == "blocked":
            return RegistryRecord(entry=entry, state="blocked", error="provider is blocked")
        try:
            response = self.transport_factory(entry.argv).call(
                "describe", {}, timeout=self.timeout, check_protocol=False)
        except TransportError as exc:
            return RegistryRecord(entry=entry, state="unreachable",
                                  error=f"{exc.code}: {exc.detail}")
        if response.status != "ok":
            code = response.error.code if response.error else response.status
            return RegistryRecord(entry=entry, state="invalid", error=f"describe {code}")
        try:
            manifest = from_dict(ForgeManifest, response.payload, "$.payload")
        except ContractError as exc:
            return RegistryRecord(entry=entry, state="invalid", error=str(exc))
        if manifest.id != entry.id:
            return RegistryRecord(
                entry=entry, state="invalid",
                error=f"manifest id {manifest.id!r} does not match registry entry {entry.id!r}")
        digest = sha256_of(to_dict(manifest))
        protocol = choose_protocol(manifest.protocols)
        if protocol is None:
            return RegistryRecord(
                entry=entry, state="incompatible", manifest=manifest, manifest_sha256=digest,
                error=f"no common protocol (offered {manifest.protocols}, "
                      f"supported {list(SUPPORTED_PROTOCOLS)})")
        return RegistryRecord(entry=entry, state="ready", manifest=manifest,
                              manifest_sha256=digest, protocol=protocol)

    def _cache_path(self, provider_id: str) -> Path | None:
        if self.forge_dir is None:
            return None
        return self.forge_dir / "registry" / f"{provider_id}.json"

    def _write_cache(self, record: RegistryRecord) -> None:
        path = self._cache_path(record.entry.id)
        if path is None or record.state != "ready":
            return
        doc = {"schema": CACHE_SCHEMA, **to_dict(record)}
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(doc, indent=2, sort_keys=True), encoding="utf-8")
        except OSError as exc:
            raise PersistenceError(f"cannot write registry cache {path}: {exc}") from exc

    def _read_cache(self, entry: ProviderEntry) -> RegistryRecord | None:
        path = self._cache_path(entry.id)
        if path is None or not path.is_file():
            return None
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(doc, dict) or doc.get("schema") != CACHE_SCHEMA:
                raise ValueError("unexpected cache schema")
            record = from_dict(RegistryRecord, doc)
            if record.entry != entry:
                return None
            if record.manifest is None or record.state != "ready":
                raise ValueError("cache entry is not a ready manifest")
            if sha256_of(to_dict(record.manifest)) != record.manifest_sha256:
                raise ValueError("manifest hash mismatch")
            return record
        except (OSError, ValueError) as exc:
            self.warnings.append(f"registry cache for {entry.id} discarded: {exc}")
            return None
```

- [ ] **Step 4: `src/theforge/registry/health.py`**

```python
"""Provider health check shared by doctor, `providers health` and The Forger."""

from dataclasses import dataclass
from typing import Literal

from theforge.contracts import ContractError, ErrorInfo, HealthReport, from_dict
from theforge.protocol import SubprocessTransport, TransportError, TransportFactory
from theforge.registry.registry import RegistryRecord

HEALTH_TIMEOUT = 10.0


@dataclass(frozen=True, kw_only=True)
class HealthOutcome:
    status: Literal["ok", "degraded", "unavailable", "error"]
    error: ErrorInfo | None = None


def check_health(
    record: RegistryRecord, *, transport_factory: TransportFactory = SubprocessTransport,
    timeout: float = HEALTH_TIMEOUT,
) -> HealthOutcome:
    if record.state != "ready":
        return HealthOutcome(status="error", error=ErrorInfo(
            code="FORGE-PROVIDER-NOT-READY",
            detail=f"{record.entry.id} is {record.state}: {record.error}"))
    try:
        response = transport_factory(record.entry.argv).call("health", {}, timeout=timeout)
    except TransportError as exc:
        return HealthOutcome(status="error", error=ErrorInfo(code=exc.code, detail=exc.detail))
    if response.status != "ok":
        return HealthOutcome(status="error", error=response.error or ErrorInfo(
            code="FORGE-HEALTH-FAILED", detail=f"health status {response.status}"))
    try:
        report = from_dict(HealthReport, response.payload, "$.payload")
    except ContractError as exc:
        return HealthOutcome(status="error",
                             error=ErrorInfo(code="FORGE-PROTO-SCHEMA", detail=str(exc)))
    if report.status == "unavailable":
        failing = "; ".join(c.detail or c.name for c in report.checks if not c.ok)
        return HealthOutcome(status="unavailable", error=ErrorInfo(
            code="FORGE-HEALTH-UNAVAILABLE", detail=failing or "provider reports unavailable"))
    return HealthOutcome(status=report.status)
```

- [ ] **Step 5: Substituir `src/theforge/registry/__init__.py`**

```python
"""Provider registry: sources, describe/refresh, cache, trust and health."""

from theforge.registry.config import (
    ProviderEntry,
    builtin_entries,
    load_entries,
    resolve_entries,
    user_config_dir,
)
from theforge.registry.health import HealthOutcome, check_health
from theforge.registry.registry import Registry, RegistryRecord

__all__ = [
    "HealthOutcome", "ProviderEntry", "Registry", "RegistryRecord", "builtin_entries",
    "check_health", "load_entries", "resolve_entries", "user_config_dir",
]
```

- [ ] **Step 6: Ver passar**

Run: `$PY -m pytest tests/test_registry.py`
Expected: `14 passed`

- [ ] **Step 7: Commit**

```bash
git add src/theforge/registry tests/test_registry.py
git commit -m "feat(registry): describe providers, negotiate protocol, cache manifests, check health"
```

---

### Task 10: Workspace scan e sinais determinísticos

**Files:**
- Create: `src/theforge/context/__init__.py`, `src/theforge/context/scan.py`
- Create: `src/theforge/routing/__init__.py`, `src/theforge/routing/signals.py`
- Test: `tests/test_scan_signals.py`

- [ ] **Step 1: Teste falhando** — `tests/test_scan_signals.py`

```python
import os
from pathlib import Path

import pytest
from helpers import write_file

from theforge.context import scan_workspace
from theforge.contracts import ExcludedFile
from theforge.routing.signals import (
    glob_matches,
    keyword_matches,
    normalize_tokens,
    workspace_dependencies,
)


def test_scan_lists_files_and_skips_ignored(tmp_path: Path) -> None:
    write_file(tmp_path, "src/app.py")
    write_file(tmp_path, ".git/config")
    write_file(tmp_path, "node_modules/x.js")
    write_file(tmp_path, ".forge/runs/a.json")
    write_file(tmp_path, ".env", "A=1")
    scan = scan_workspace(tmp_path, ["."])
    assert scan.files == ["src/app.py"]
    assert ExcludedFile(path=".env", reason="secret") in scan.excluded


def test_scan_targets_and_missing(tmp_path: Path) -> None:
    write_file(tmp_path, "api/a.yaml")
    write_file(tmp_path, "jobs/j.py")
    scan = scan_workspace(tmp_path, ["api", "nope"])
    assert scan.files == ["api/a.yaml"]
    assert ExcludedFile(path="nope", reason="missing") in scan.excluded


def test_scan_target_outside_root(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    root.mkdir()
    (tmp_path / "other").mkdir()
    scan = scan_workspace(root, ["../other"])
    assert scan.files == []
    assert ExcludedFile(path="../other", reason="outside_root") in scan.excluded


def test_scan_symlink_escape(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    root.mkdir()
    secret = tmp_path / "outside.txt"
    secret.write_text("s")
    try:
        os.symlink(secret, root / "link.txt")
    except OSError:
        pytest.skip("symlinks not permitted on this host")
    scan = scan_workspace(root, ["."])
    assert scan.files == []
    assert ExcludedFile(path="link.txt", reason="outside_root") in scan.excluded


def test_normalize_tokens() -> None:
    assert normalize_tokens("Análise do Job está LENTO!") == ["analise", "do", "job", "esta",
                                                              "lento"]


def test_keyword_matches_multiword_and_order() -> None:
    assert keyword_matches({"glue", "job", "lento"}, ["glue job", "spark", "lento"]) == \
        ["glue job", "lento"]


def test_workspace_dependencies(tmp_path: Path) -> None:
    write_file(tmp_path, "pyproject.toml",
               '[project]\ndependencies = ["PySpark>=3.5", "boto3"]\n'
               '[tool.poetry.dependencies]\npython = "^3.11"\nFastAPI = "*"\n')
    write_file(tmp_path, "requirements-dev.txt", "# c\n-r base.txt\naws_glue_libs==4\n\n")
    write_file(tmp_path, "package.json",
               '{"dependencies": {"express": "4"}, "devDependencies": {"Jest": "29"}}')
    assert workspace_dependencies(tmp_path) == {
        "pyspark", "boto3", "fastapi", "aws-glue-libs", "express", "jest"}


def test_workspace_dependencies_tolerates_garbage(tmp_path: Path) -> None:
    write_file(tmp_path, "pyproject.toml", "not = [toml")
    write_file(tmp_path, "package.json", "{")
    assert workspace_dependencies(tmp_path) == set()


def test_glob_matches() -> None:
    files = ["api/openapi.yaml", "jobs/orders_glue_job.py"]
    assert glob_matches(files, ["openapi.yaml", "*glue*.py", "*.scala"]) == \
        ["openapi.yaml", "*glue*.py"]
```

- [ ] **Step 2: Ver falhar**

Run: `$PY -m pytest tests/test_scan_signals.py`
Expected: FAIL `ModuleNotFoundError: No module named 'theforge.context'`

- [ ] **Step 3: `src/theforge/context/scan.py`**

```python
"""Workspace scan: list candidate files under targets, never escaping the root."""

import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from theforge.contracts import ExcludedFile
from theforge.security.paths import IGNORED_DIRS, is_secret_name, resolve_inside

MAX_FILES = 20_000


@dataclass(frozen=True, kw_only=True)
class WorkspaceScan:
    root: Path
    files: list[str]
    excluded: list[ExcludedFile]


def scan_workspace(root: Path, targets: Sequence[str]) -> WorkspaceScan:
    root_resolved = root.resolve()
    files: set[str] = set()
    excluded: dict[str, str] = {}
    for target in list(targets) or ["."]:
        start = root_resolved / target
        inside = resolve_inside(root_resolved, start)
        if inside is None:
            excluded[target] = "missing" if not os.path.lexists(start) else "outside_root"
            continue
        if inside.is_file():
            _consider(root_resolved, inside, files, excluded)
            continue
        for dirpath, dirnames, filenames in os.walk(inside, followlinks=False):
            kept: list[str] = []
            for name in sorted(dirnames):
                if name in IGNORED_DIRS:
                    continue
                if os.path.islink(os.path.join(dirpath, name)):
                    rel = (Path(dirpath) / name).relative_to(root_resolved).as_posix()
                    excluded[rel] = "symlinked_dir"
                    continue
                kept.append(name)
            dirnames[:] = kept
            for name in sorted(filenames):
                if len(files) >= MAX_FILES:
                    break
                _consider(root_resolved, Path(dirpath) / name, files, excluded)
    return WorkspaceScan(
        root=root_resolved,
        files=sorted(files),
        excluded=[ExcludedFile(path=p, reason=r) for p, r in sorted(excluded.items())],
    )


def _consider(root: Path, path: Path, files: set[str], excluded: dict[str, str]) -> None:
    rel = path.relative_to(root).as_posix()
    if is_secret_name(path.name):
        excluded[rel] = "secret"
    elif path.is_symlink() and resolve_inside(root, path) is None:
        excluded[rel] = "outside_root"
    else:
        files.add(rel)
```

- [ ] **Step 4: `src/theforge/context/__init__.py`** (Task 12 expande)

```python
"""Context: workspace scan and Context Broker."""

from theforge.context.scan import WorkspaceScan, scan_workspace

__all__ = ["WorkspaceScan", "scan_workspace"]
```

- [ ] **Step 5: `src/theforge/routing/signals.py`**

```python
"""Deterministic routing signals: intent tokens, workspace dependencies, file globs."""

import json
import re
import tomllib
import unicodedata
from pathlib import Path, PurePosixPath
from typing import Any

_TOKEN = re.compile(r"\w+")
_REQ_NAME = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")


def normalize_tokens(text: str) -> list[str]:
    decomposed = unicodedata.normalize("NFKD", text.lower())
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return _TOKEN.findall(stripped)


def keyword_matches(intent_tokens: set[str], keywords: list[str]) -> list[str]:
    hits: list[str] = []
    for keyword in keywords:
        tokens = normalize_tokens(keyword)
        if tokens and all(token in intent_tokens for token in tokens):
            hits.append(keyword)
    return hits


def normalize_dep(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def glob_matches(files: list[str], globs: list[str]) -> list[str]:
    return [g for g in globs if any(PurePosixPath(f).match(g) for f in files)]


def workspace_dependencies(root: Path) -> set[str]:
    names: set[str] = set()
    names |= _pyproject_deps(root / "pyproject.toml")
    for req in sorted(root.glob("requirements*.txt")):
        names |= _requirements_deps(req)
    names |= _package_json_deps(root / "package.json")
    return {normalize_dep(n) for n in names}


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8") if path.is_file() else None
    except (OSError, UnicodeDecodeError):
        return None


def _pyproject_deps(path: Path) -> set[str]:
    text = _read(path)
    if text is None:
        return set()
    try:
        data: dict[str, Any] = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return set()
    names: set[str] = set()
    project = data.get("project")
    if isinstance(project, dict) and isinstance(project.get("dependencies"), list):
        for spec in project["dependencies"]:
            if isinstance(spec, str) and (m := _REQ_NAME.match(spec)):
                names.add(m.group(1))
    tool = data.get("tool")
    poetry = tool.get("poetry") if isinstance(tool, dict) else None
    deps = poetry.get("dependencies") if isinstance(poetry, dict) else None
    if isinstance(deps, dict):
        names |= {str(k) for k in deps if str(k).lower() != "python"}
    return names


def _requirements_deps(path: Path) -> set[str]:
    text = _read(path)
    if text is None:
        return set()
    names: set[str] = set()
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", "-")):
            continue
        if m := _REQ_NAME.match(stripped):
            names.add(m.group(1))
    return names


def _package_json_deps(path: Path) -> set[str]:
    text = _read(path)
    if text is None:
        return set()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return set()
    names: set[str] = set()
    if isinstance(data, dict):
        for key in ("dependencies", "devDependencies"):
            section = data.get(key)
            if isinstance(section, dict):
                names |= {str(k) for k in section}
    return names
```

- [ ] **Step 6: `src/theforge/routing/__init__.py`** (Task 11 expande)

```python
"""Deterministic capability routing."""
```

- [ ] **Step 7: Ver passar**

Run: `$PY -m pytest tests/test_scan_signals.py`
Expected: `9 passed` (ou `8 passed, 1 skipped` sem symlink)

- [ ] **Step 8: Commit**

```bash
git add src/theforge/context src/theforge/routing tests/test_scan_signals.py
git commit -m "feat(context): add guarded workspace scan and deterministic routing signals"
```

---
### Task 11: Router determinístico

**Files:**
- Create: `src/theforge/routing/router.py`
- Modify: `src/theforge/routing/__init__.py`
- Test: `tests/test_router.py`

- [ ] **Step 1: Teste falhando** — `tests/test_router.py`

```python
import pytest

from theforge.contracts import Capability, ForgeManifest, Signals, TaskSpec
from theforge.contracts.canonical import utc_now
from theforge.errors import UsageError
from theforge.meta import PRODUCER
from theforge.registry import ProviderEntry, RegistryRecord
from theforge.routing import route


def cap(cid: str, *, actions: tuple[str, ...] = ("run",), kw: tuple[str, ...] = (),
        globs: tuple[str, ...] = (), deps: tuple[str, ...] = (),
        state: str = "supported") -> Capability:
    return Capability(id=cid, actions=list(actions), default_action=actions[0],
                      state=state, operation_class="read_only",
                      signals=Signals(keywords=list(kw), file_globs=list(globs),
                                      dependencies=list(deps)))


def record(pid: str, caps: list[Capability], trust: str = "local",
           state: str = "ready") -> RegistryRecord:
    manifest = ForgeManifest(id=pid, version="1", protocols=["forge/v1"],
                             ops=["describe", "health", "execute"], capabilities=list(caps))
    return RegistryRecord(entry=ProviderEntry(id=pid, argv=["x"], trust=trust),
                          state=state, manifest=manifest,
                          manifest_sha256="h", protocol="forge/v1")


def task(intent: str, **kw: object) -> TaskSpec:
    return TaskSpec(producer=PRODUCER, created_at=utc_now(), id="t1", intent=intent,
                    workspace_root="/ws", **kw)


SPARK = record("spark-forge", [cap("spark.performance", actions=("diagnose", "optimize"),
                                   kw=("glue", "lento", "performance"),
                                   globs=("*glue*.py",), deps=("pyspark",))])
API = record("api-forge", [cap("api.contract", actions=("review",),
                               kw=("openapi", "contrato", "api"), globs=("openapi.yaml",))])


def test_case_a_routes_to_spark() -> None:
    d = route(task("analise esse Glue Job porque está lento"), [SPARK, API],
              ["jobs/orders_glue_job.py"], {"pyspark"})
    assert d.status == "routed"
    assert (d.selected[0].provider, d.selected[0].action) == ("spark-forge", "diagnose")
    assert d.confidence.level == "high"
    assert d.candidates[0].rank_key == [3, 1, 1, 2]
    assert d.confidence.measured_signals == [
        "dependencies:pyspark", "file_globs:*glue*.py", "keywords:glue,lento"]


def test_case_b_routes_to_api() -> None:
    d = route(task("avalie esse contrato OpenAPI"), [SPARK, API], ["api/openapi.yaml"], set())
    assert d.status == "routed" and d.selected[0].provider == "api-forge"
    assert d.candidates[0].rank_key == [2, 0, 1, 2]


def test_tie_is_ambiguous() -> None:
    d = route(task("performance da api"), [SPARK, API], [], set())
    assert d.status == "ambiguous" and d.selected == []
    assert d.confidence.unresolved[0].startswith("tie between")


def test_single_signal_type_is_ambiguous() -> None:
    d = route(task("glue"), [SPARK], [], set())
    assert d.status == "ambiguous" and "only 1 signal type" in d.reason


def test_no_route() -> None:
    assert route(task("hello"), [SPARK], [], set()).status == "no_route"


def test_explicit_capability_tie_breaks_by_trust_then_id() -> None:
    caps = SPARK.manifest.capabilities if SPARK.manifest else []
    trusted = record("zzz-forge", caps, trust="trusted")
    unverified = record("aaa-forge", caps, trust="unverified")
    d = route(task("x", requested_capability="spark.performance"),
              [SPARK, trusted, unverified], [], set(), allow_unverified=True)
    assert d.selected[0].provider == "zzz-forge"
    assert [c.provider for c in d.candidates] == ["zzz-forge", "spark-forge", "aaa-forge"]
    assert "tie-break" in d.reason


def test_explicit_unknown_capability() -> None:
    assert route(task("x", requested_capability="zzz.nope"), [SPARK], [], set()).status == \
        "no_route"


def test_requested_action_validated() -> None:
    with pytest.raises(UsageError, match="not offered"):
        route(task("x", requested_capability="spark.performance", requested_action="delete"),
              [SPARK], [], set())


def test_requested_action_honored() -> None:
    d = route(task("x", requested_capability="spark.performance", requested_action="optimize"),
              [SPARK], [], set())
    assert d.selected[0].action == "optimize"


def test_unverified_excluded_by_default() -> None:
    rec = record("u-forge", [cap("demo.run")], trust="unverified")
    assert route(task("x", requested_capability="demo.run"), [rec], [], set()).status == \
        "no_route"


def test_unsupported_capability_never_routed() -> None:
    rec = record("u-forge", [cap("demo.run", state="unsupported")])
    assert route(task("x", requested_capability="demo.run"), [rec], [], set()).status == \
        "no_route"


def test_not_ready_records_skipped() -> None:
    rec = record("u-forge", [cap("demo.run")], state="incompatible")
    assert route(task("x", requested_capability="demo.run"), [rec], [], set()).status == \
        "no_route"
```

- [ ] **Step 2: Ver falhar**

Run: `$PY -m pytest tests/test_router.py`
Expected: FAIL `ImportError: cannot import name 'route'`

- [ ] **Step 3: `src/theforge/routing/router.py`**

```python
"""Deterministic routing: explicit capability or ranked declared signals. Never guesses."""

from collections.abc import Sequence

from theforge.contracts import (
    Candidate,
    Capability,
    Confidence,
    MatchedSignals,
    RoutingDecision,
    Selection,
    TaskSpec,
)
from theforge.contracts.canonical import utc_now
from theforge.contracts.types import TRUST_RANK
from theforge.errors import UsageError
from theforge.meta import PRODUCER
from theforge.registry import RegistryRecord
from theforge.routing.signals import (
    glob_matches,
    keyword_matches,
    normalize_dep,
    normalize_tokens,
)

MIN_SIGNAL_TYPES = 2


def route(
    task: TaskSpec, records: Sequence[RegistryRecord], files: list[str],
    dependencies: set[str], *, allow_unverified: bool = False,
) -> RoutingDecision:
    routable = [r for r in records if r.routable(allow_unverified)]
    if task.requested_capability:
        return _route_explicit(task, routable, task.requested_capability)
    return _route_by_signals(task, routable, files, dependencies)


def resolve_action(task: TaskSpec, capability: Capability) -> str:
    action = task.requested_action or capability.default_action
    if action not in capability.actions:
        raise UsageError(f"action {action!r} is not offered by {capability.id} "
                         f"(actions: {', '.join(capability.actions)})")
    return action


def _decision(
    task: TaskSpec, *, status: str, reason: str, level: str,
    candidates: Sequence[Candidate] = (), selected: Sequence[Selection] = (),
    measured: Sequence[str] = (), unresolved: Sequence[str] = (),
) -> RoutingDecision:
    return RoutingDecision(
        producer=PRODUCER, created_at=utc_now(), status=status,  # type: ignore[arg-type]
        task_id=task.id, candidates=list(candidates), selected=list(selected), reason=reason,
        confidence=Confidence(level=level, measured_signals=list(measured),  # type: ignore[arg-type]
                              unresolved=list(unresolved)),
    )


def _route_explicit(
    task: TaskSpec, routable: list[RegistryRecord], cap_id: str
) -> RoutingDecision:
    matches: list[tuple[RegistryRecord, Capability]] = []
    for record in routable:
        capability = record.manifest.capability(cap_id) if record.manifest else None
        if capability is not None and capability.state != "unsupported":
            matches.append((record, capability))
    if not matches:
        return _decision(task, status="no_route", level="low",
                         reason=f"no routable provider declares capability {cap_id}",
                         unresolved=[f"capability:{cap_id}"])
    matches.sort(key=lambda m: (TRUST_RANK[m[0].entry.trust], m[0].entry.id))
    record, capability = matches[0]
    action = resolve_action(task, capability)
    candidates = [Candidate(provider=r.entry.id, capability=cap_id,
                            rank_key=[TRUST_RANK[r.entry.trust]]) for r, _ in matches]
    reason = f"requested capability {cap_id}"
    if len(matches) > 1:
        reason += f"; {len(matches)} providers declare it, tie-break by trust then id"
    return _decision(task, status="routed", level="high", reason=reason, candidates=candidates,
                     selected=[Selection(provider=record.entry.id, capability=cap_id,
                                         action=action)],
                     measured=["requested_capability"])


def _route_by_signals(
    task: TaskSpec, routable: list[RegistryRecord], files: list[str], dependencies: set[str],
) -> RoutingDecision:
    intent = set(normalize_tokens(task.intent))
    scored: list[tuple[Candidate, Capability]] = []
    for record in routable:
        if record.manifest is None:
            continue
        for capability in record.manifest.capabilities:
            if capability.state == "unsupported":
                continue
            signals = capability.signals
            deps = sorted({normalize_dep(d) for d in signals.dependencies} & dependencies)
            globs = glob_matches(files, signals.file_globs)
            kws = keyword_matches(intent, signals.keywords)
            types = sum(1 for hits in (deps, globs, kws) if hits)
            if types == 0:
                continue
            candidate = Candidate(
                provider=record.entry.id, capability=capability.id,
                matched=MatchedSignals(dependencies=deps, file_globs=globs, keywords=kws),
                rank_key=[types, len(deps), len(globs), len(kws)],
            )
            scored.append((candidate, capability))
    scored.sort(key=lambda s: ([-k for k in s[0].rank_key], s[0].provider, s[0].capability))
    candidates = [s[0] for s in scored]
    if not scored:
        return _decision(task, status="no_route", level="low",
                         reason="no capability matched any signal", unresolved=["intent"])
    top, capability = scored[0]
    measured = _measured(top.matched)
    issue: str | None = None
    if len(scored) > 1 and scored[1][0].rank_key == top.rank_key:
        other = scored[1][0]
        issue = (f"tie between {top.provider}/{top.capability} and "
                 f"{other.provider}/{other.capability} at rank {top.rank_key}")
    elif top.rank_key[0] < MIN_SIGNAL_TYPES:
        issue = (f"only {top.rank_key[0]} signal type matched for "
                 f"{top.provider}/{top.capability} (need {MIN_SIGNAL_TYPES})")
    if issue is not None:
        return _decision(task, status="ambiguous", level="low", reason=f"ambiguous: {issue}",
                         candidates=candidates, measured=measured, unresolved=[issue])
    action = resolve_action(task, capability)
    reason = (f"{top.provider} {top.capability} matched {top.rank_key[0]} signal types "
              f"({'; '.join(measured)})")
    return _decision(task, status="routed", level="high", reason=reason, candidates=candidates,
                     selected=[Selection(provider=top.provider, capability=top.capability,
                                         action=action)],
                     measured=measured)


def _measured(matched: MatchedSignals) -> list[str]:
    groups = (("dependencies", matched.dependencies), ("file_globs", matched.file_globs),
              ("keywords", matched.keywords))
    return [f"{name}:{','.join(hits)}" for name, hits in groups if hits]
```

- [ ] **Step 4: Substituir `src/theforge/routing/__init__.py`**

```python
"""Deterministic capability routing."""

from theforge.routing.router import MIN_SIGNAL_TYPES, resolve_action, route

__all__ = ["MIN_SIGNAL_TYPES", "resolve_action", "route"]
```

- [ ] **Step 5: Ver passar**

Run: `$PY -m pytest tests/test_router.py tests/test_scan_signals.py`
Expected: `21 passed` (12 router + 9 scan)

- [ ] **Step 6: Commit**

```bash
git add src/theforge/routing tests/test_router.py
git commit -m "feat(routing): add explainable deterministic capability router"
```

---

### Task 12: Context Broker

**Files:**
- Create: `src/theforge/context/broker.py`
- Modify: `src/theforge/context/__init__.py`
- Test: `tests/test_broker.py`

- [ ] **Step 1: Teste falhando** — `tests/test_broker.py`

```python
import hashlib
from pathlib import Path

from helpers import write_file

from theforge.context import BUDGETS, build_context_pack, scan_workspace
from theforge.contracts import ExcludedFile, TaskSpec
from theforge.contracts.canonical import utc_now
from theforge.meta import PRODUCER


def task(root: Path, profile: str = "balanced") -> TaskSpec:
    return TaskSpec(producer=PRODUCER, created_at=utc_now(), id="t1", intent="x",
                    workspace_root=str(root), budget_profile=profile)


def test_pack_selects_by_glob_and_hashes(tmp_path: Path) -> None:
    write_file(tmp_path, "api/openapi.yaml", "openapi: 3.0.0\n")
    write_file(tmp_path, "api/main.py", "x=1\n")
    write_file(tmp_path, ".env", "A=1")
    pack = build_context_pack(task(tmp_path), "api-forge", ["openapi.yaml", "*.yaml"],
                              scan_workspace(tmp_path, ["."]))
    assert [f.path for f in pack.files] == ["api/openapi.yaml"]
    item = pack.files[0]
    assert item.sha256 == hashlib.sha256(b"openapi: 3.0.0\n").hexdigest()
    assert item.bytes == 15 and item.reason == "glob:openapi.yaml,*.yaml"
    assert pack.status == "complete" and not pack.truncated
    assert pack.used_bytes == 15 and pack.budget_bytes == BUDGETS["balanced"]
    assert ExcludedFile(path=".env", reason="secret") in pack.excluded


def test_pack_orders_by_glob_hits_then_path(tmp_path: Path) -> None:
    for name in ("b.yaml", "a.yaml", "openapi.yaml"):
        write_file(tmp_path, name, "x")
    pack = build_context_pack(task(tmp_path), "p", ["*.yaml", "openapi.yaml"],
                              scan_workspace(tmp_path, ["."]))
    assert [f.path for f in pack.files] == ["openapi.yaml", "a.yaml", "b.yaml"]


def test_pack_respects_budget(tmp_path: Path) -> None:
    write_file(tmp_path, "big.txt", "x" * 70_000)
    write_file(tmp_path, "small.txt", "0123456789")
    pack = build_context_pack(task(tmp_path, "economy"), "p", ["*.txt"],
                              scan_workspace(tmp_path, ["."]))
    assert [f.path for f in pack.files] == ["small.txt"]
    assert ExcludedFile(path="big.txt", reason="budget") in pack.excluded
    assert pack.truncated and pack.status == "truncated"


def test_pack_without_globs_is_empty(tmp_path: Path) -> None:
    write_file(tmp_path, "a.txt", "x")
    pack = build_context_pack(task(tmp_path), "p", [], scan_workspace(tmp_path, ["."]))
    assert pack.files == [] and pack.used_bytes == 0
```

- [ ] **Step 2: Ver falhar**

Run: `$PY -m pytest tests/test_broker.py`
Expected: FAIL `ImportError: cannot import name 'BUDGETS'`

- [ ] **Step 3: `src/theforge/context/broker.py`**

```python
"""Context Broker: provider-specific ContextPack by reference + hash, within budget."""

from pathlib import PurePosixPath

from theforge.context.scan import WorkspaceScan
from theforge.contracts import ContextFile, ContextPack, ExcludedFile, TaskSpec
from theforge.contracts.canonical import sha256_hex, utc_now
from theforge.meta import PRODUCER

BUDGETS: dict[str, int] = {"economy": 64 * 1024, "balanced": 256 * 1024, "max": 1024 * 1024}


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
        try:
            size = path.stat().st_size
            if used + size > budget:
                excluded.append(ExcludedFile(path=rel, reason="budget"))
                truncated = True
                continue
            data = path.read_bytes()
        except OSError:
            excluded.append(ExcludedFile(path=rel, reason="unreadable"))
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
```

- [ ] **Step 4: Substituir `src/theforge/context/__init__.py`**

```python
"""Context: workspace scan and Context Broker."""

from theforge.context.broker import BUDGETS, build_context_pack
from theforge.context.scan import WorkspaceScan, scan_workspace

__all__ = ["BUDGETS", "WorkspaceScan", "build_context_pack", "scan_workspace"]
```

- [ ] **Step 5: Ver passar**

Run: `$PY -m pytest tests/test_broker.py`
Expected: `4 passed`

- [ ] **Step 6: Commit**

```bash
git add src/theforge/context tests/test_broker.py
git commit -m "feat(context): add budgeted Context Broker producing ContextPack by reference"
```

---

### Task 13: Run store e estado `.forge/`

**Files:**
- Create: `src/theforge/runs/__init__.py`, `src/theforge/runs/store.py`, `src/theforge/state.py`
- Test: `tests/test_runs_state.py`

- [ ] **Step 1: Teste falhando** — `tests/test_runs_state.py`

```python
from pathlib import Path

import pytest

from theforge.contracts import TaskSpec
from theforge.contracts.canonical import sha256_of, utc_now
from theforge.errors import PersistenceError, UsageError
from theforge.meta import PRODUCER
from theforge.runs import RUN_ID, RunStore, new_run_id
from theforge.state import find_forge_dir, init_workspace, require_forge_dir


def make_task(intent: str = "eco password=hunter2xyz") -> TaskSpec:
    return TaskSpec(producer=PRODUCER, created_at=utc_now(), id="t1", intent=intent,
                    workspace_root="/ws")


def test_new_run_id_format() -> None:
    assert RUN_ID.match(new_run_id())


def test_write_read_redacts_and_hashes(tmp_path: Path) -> None:
    store = RunStore(tmp_path / ".forge")
    run_id = new_run_id()
    store.create(run_id)
    digest = store.write(run_id, "task", make_task())
    data = store.read(run_id, "task")
    assert data["intent"] == "eco password=[REDACTED]"
    assert digest == sha256_of(data)
    assert store.read_optional(run_id, "result") is None
    assert store.list_runs() == [run_id]
    assert store.work_dir(run_id).is_dir()


def test_run_id_validation(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="invalid run id"):
        RunStore(tmp_path).run_dir("../../etc")


def test_unknown_artifact_name(tmp_path: Path) -> None:
    store = RunStore(tmp_path)
    run_id = new_run_id()
    store.create(run_id)
    with pytest.raises(ValueError, match="unknown run artifact"):
        store.write(run_id, "secrets", make_task())


def test_persistence_error(tmp_path: Path) -> None:
    not_a_dir = tmp_path / "forge-file"
    not_a_dir.write_text("x")
    with pytest.raises(PersistenceError):
        RunStore(not_a_dir).create(new_run_id())


def test_init_workspace(tmp_path: Path) -> None:
    created = init_workspace(tmp_path)
    assert ".forge/config/providers.toml" in created
    assert ".forge/.gitignore" in created
    assert "!config/" in (tmp_path / ".forge" / ".gitignore").read_text(encoding="utf-8")
    assert init_workspace(tmp_path) == []
    assert find_forge_dir(tmp_path) == tmp_path / ".forge"
    other = tmp_path / "other"
    other.mkdir()
    assert find_forge_dir(other) is None
    with pytest.raises(UsageError, match="theforge init"):
        require_forge_dir(other)
```

- [ ] **Step 2: Ver falhar**

Run: `$PY -m pytest tests/test_runs_state.py`
Expected: FAIL `ModuleNotFoundError: No module named 'theforge.runs'`

- [ ] **Step 3: `src/theforge/runs/store.py`**

```python
"""Run store: one directory per run, redacted JSON artifacts, hashes over what is on disk."""

import json
import re
import secrets
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from theforge.contracts import to_dict
from theforge.contracts.canonical import sha256_of
from theforge.errors import PersistenceError
from theforge.security.redact import redact

RUN_ID = re.compile(r"^\d{8}T\d{6}Z-[0-9a-f]{8}$")
ARTIFACTS = ("task", "routing", "context", "result", "receipt")


def new_run_id() -> str:
    return f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{secrets.token_hex(4)}"


class RunStore:
    def __init__(self, forge_dir: Path) -> None:
        self.runs_dir = forge_dir / "runs"

    def run_dir(self, run_id: str) -> Path:
        if not RUN_ID.match(run_id):
            raise ValueError(f"invalid run id {run_id!r}")
        return self.runs_dir / run_id

    def work_dir(self, run_id: str) -> Path:
        return self.run_dir(run_id) / "work"

    def create(self, run_id: str) -> Path:
        directory = self.run_dir(run_id)
        try:
            (directory / "work").mkdir(parents=True)
        except OSError as exc:
            raise PersistenceError(f"cannot create run directory {directory}: {exc}") from exc
        return directory

    def write(self, run_id: str, name: str, contract: Any) -> str:
        if name not in ARTIFACTS:
            raise ValueError(f"unknown run artifact {name!r}")
        data = redact(to_dict(contract))
        path = self.run_dir(run_id) / f"{name}.json"
        tmp = path.with_suffix(".json.tmp")
        try:
            tmp.write_text(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False),
                           encoding="utf-8")
            tmp.replace(path)
        except OSError as exc:
            raise PersistenceError(f"cannot write {path}: {exc}") from exc
        return sha256_of(data)

    def read(self, run_id: str, name: str) -> dict[str, Any]:
        data = self.read_optional(run_id, name)
        if data is None:
            raise LookupError(f"run {run_id} has no {name}")
        return data

    def read_optional(self, run_id: str, name: str) -> dict[str, Any] | None:
        path = self.run_dir(run_id) / f"{name}.json"
        if not path.is_file():
            return None
        loaded: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        return loaded

    def list_runs(self) -> list[str]:
        if not self.runs_dir.is_dir():
            return []
        return sorted(p.name for p in self.runs_dir.iterdir() if RUN_ID.match(p.name))
```

- [ ] **Step 4: `src/theforge/runs/__init__.py`**

```python
"""Run store and receipts on disk."""

from theforge.runs.store import ARTIFACTS, RUN_ID, RunStore, new_run_id

__all__ = ["ARTIFACTS", "RUN_ID", "RunStore", "new_run_id"]
```

- [ ] **Step 5: `src/theforge/state.py`**

```python
"""Workspace state directory `.forge/`: layout, init and lookup."""

from pathlib import Path

from theforge.errors import PersistenceError, UsageError

FORGE_DIR_NAME = ".forge"
SUBDIRS = ("config", "registry", "runs", "cache")
GITIGNORE = (
    "# Managed by The Forge: only config/ is committable.\n"
    "*\n!.gitignore\n!config/\n!config/**\n"
)
PROVIDERS_TEMPLATE = """\
# Providers for this workspace. Each entry: id, argv (list), trust.
# trust: trusted | local | unverified | blocked   (default: unverified)
# "{python}" in argv is replaced by the interpreter running The Forge.
#
# [[providers]]
# id = "my-forge"
# argv = ["my-forge-cli", "protocol"]
# trust = "local"
"""


def find_forge_dir(root: Path) -> Path | None:
    candidate = root / FORGE_DIR_NAME
    return candidate if candidate.is_dir() else None


def require_forge_dir(root: Path) -> Path:
    forge_dir = find_forge_dir(root)
    if forge_dir is None:
        raise UsageError(f"{root} is not initialized; run `theforge init`")
    return forge_dir


def init_workspace(root: Path) -> list[str]:
    forge_dir = root / FORGE_DIR_NAME
    created: list[str] = []
    try:
        for directory in (forge_dir, *(forge_dir / sub for sub in SUBDIRS)):
            if not directory.exists():
                directory.mkdir(parents=True)
                created.append(directory.relative_to(root).as_posix())
        files = ((forge_dir / ".gitignore", GITIGNORE),
                 (forge_dir / "config" / "providers.toml", PROVIDERS_TEMPLATE))
        for path, content in files:
            if not path.exists():
                path.write_text(content, encoding="utf-8")
                created.append(path.relative_to(root).as_posix())
    except OSError as exc:
        raise PersistenceError(f"cannot initialize {forge_dir}: {exc}") from exc
    return created
```

- [ ] **Step 6: Ver passar**

Run: `$PY -m pytest tests/test_runs_state.py`
Expected: `6 passed`

- [ ] **Step 7: Commit**

```bash
git add src/theforge/runs src/theforge/state.py tests/test_runs_state.py
git commit -m "feat(runs): add redacting run store and .forge workspace layout"
```

---
### Task 14: The Forger (orquestrador)

**Files:**
- Create: `src/theforge/forger/__init__.py`, `src/theforge/forger/orchestrator.py`
- Test: `tests/test_forger.py`

- [ ] **Step 1: Teste falhando** — `tests/test_forger.py`

```python
from pathlib import Path

import pytest
from helpers import API_ENTRY, SPARK_ENTRY, bad_entry, case_a, case_b, make_workspace, write_file

from theforge.contracts.canonical import sha256_of
from theforge.forger import AskRequest, Forger
from theforge.registry import Registry
from theforge.runs import ARTIFACTS, RunStore


def forger(root: Path, **kw: float) -> Forger:
    forge = root / ".forge"
    return Forger(root, Registry(forge), RunStore(forge), **kw)


def test_case_a_end_to_end(tmp_path: Path) -> None:
    make_workspace(tmp_path, [SPARK_ENTRY, API_ENTRY])
    case_a(tmp_path)
    out = forger(tmp_path).ask(AskRequest(intent="analise esse Glue Job porque está lento"))
    assert out.status == "ok"
    assert out.decision.selected[0].provider == "fixture-spark"
    assert out.result is not None
    assert out.result.metrics.duration_ms.kind == "measured"
    assert out.result.metrics.tokens.kind == "unknown"
    store = RunStore(tmp_path / ".forge")
    for name in ARTIFACTS:
        assert store.read_optional(out.run_id, name) is not None
    receipt = out.receipt
    assert receipt.inputs.task_sha256 == sha256_of(store.read(out.run_id, "task"))
    assert receipt.inputs.routing_sha256 == sha256_of(store.read(out.run_id, "routing"))
    assert receipt.inputs.context_sha256 == sha256_of(store.read(out.run_id, "context"))
    assert receipt.result_sha256 == sha256_of(store.read(out.run_id, "result"))
    assert receipt.provider is not None and receipt.provider.id == "fixture-spark"
    assert receipt.provider.trust == "local" and receipt.provider.manifest_sha256
    files = [f["path"] for f in store.read(out.run_id, "context")["files"]]
    assert files == ["jobs/orders_glue_job.py"]


def test_case_b_routes_to_api(tmp_path: Path) -> None:
    make_workspace(tmp_path, [SPARK_ENTRY, API_ENTRY])
    case_b(tmp_path)
    out = forger(tmp_path).ask(AskRequest(intent="avalie esse contrato OpenAPI",
                                          targets=["api"]))
    assert out.status == "ok"
    assert (out.decision.selected[0].provider, out.decision.selected[0].action) == \
        ("fixture-api", "review")


def test_ambiguous_writes_receipt_only(tmp_path: Path) -> None:
    make_workspace(tmp_path, [SPARK_ENTRY, API_ENTRY])
    out = forger(tmp_path).ask(AskRequest(intent="performance da api"))
    store = RunStore(tmp_path / ".forge")
    assert out.status == "ambiguous" and out.receipt.status == "ambiguous"
    assert store.read_optional(out.run_id, "context") is None
    assert store.read_optional(out.run_id, "result") is None
    assert store.read_optional(out.run_id, "receipt") is not None


def test_no_route(tmp_path: Path) -> None:
    make_workspace(tmp_path, [])
    assert forger(tmp_path).ask(AskRequest(intent="bom dia")).status == "no_route"


def test_echo_explicit_capability_confirms_hashes(tmp_path: Path) -> None:
    make_workspace(tmp_path, [])
    write_file(tmp_path, "notes.txt", "hello\n")
    out = forger(tmp_path).ask(AskRequest(intent="eco", capability="demo.echo"))
    assert out.status == "ok" and out.result is not None
    assert [e.epistemic for e in out.result.evidence] == ["confirmed"]


def test_refused_is_reported(tmp_path: Path) -> None:
    make_workspace(tmp_path, [bad_entry("refuse", "bad-a")])
    out = forger(tmp_path).ask(AskRequest(intent="run it", capability="bad.thing"))
    assert out.status == "refused" and out.receipt.status == "refused"
    assert out.error is not None and out.error.code == "BAD-REFUSED"
    assert out.error.unlock == "try another capability"


@pytest.mark.parametrize(
    ("mode", "code"),
    [("crash", "FORGE-PROTO-EXIT"), ("garbage", "FORGE-PROTO-NOT-JSON"),
     ("oversize", "FORGE-PROTO-OVERSIZE"), ("mismatch", "FORGE-PROTO-MISMATCH"),
     ("bad-result", "FORGE-PROTO-SCHEMA")],
)
def test_provider_failures_never_succeed(tmp_path: Path, mode: str, code: str) -> None:
    make_workspace(tmp_path, [bad_entry(mode, "bad-a")])
    out = forger(tmp_path).ask(AskRequest(intent="run it", capability="bad.thing"))
    assert out.status == "provider_failure" and out.result is None
    assert out.error is not None and out.error.code == code
    store = RunStore(tmp_path / ".forge")
    assert store.read(out.run_id, "receipt")["status"] == "provider_failure"
    assert store.read_optional(out.run_id, "result") is None


def test_timeout(tmp_path: Path) -> None:
    make_workspace(tmp_path, [bad_entry("timeout", "bad-a")])
    out = forger(tmp_path, execute_timeout=1.5).ask(
        AskRequest(intent="run it", capability="bad.thing"))
    assert out.error is not None and out.error.code == "FORGE-PROTO-TIMEOUT"


def test_unhealthy_primary_falls_back(tmp_path: Path) -> None:
    make_workspace(tmp_path, [bad_entry("unhealthy", "bad-a", trust="trusted"),
                              bad_entry("ok", "bad-b", trust="local")])
    out = forger(tmp_path).ask(AskRequest(intent="run it", capability="bad.thing"))
    assert out.status == "ok"
    assert out.decision.selected[0].provider == "bad-b"
    assert out.decision.fallbacks_used == ["bad-a:FORGE-HEALTH-UNAVAILABLE"]


def test_all_unhealthy_is_provider_failure(tmp_path: Path) -> None:
    make_workspace(tmp_path, [bad_entry("unhealthy", "bad-a")])
    out = forger(tmp_path).ask(AskRequest(intent="run it", capability="bad.thing"))
    assert out.status == "provider_failure"
    assert out.error is not None and out.error.code == "FORGE-HEALTH-UNAVAILABLE"


def test_incompatible_provider_not_routed(tmp_path: Path) -> None:
    make_workspace(tmp_path, [bad_entry("wrong-major", "bad-a")])
    out = forger(tmp_path).ask(AskRequest(intent="run it", capability="bad.thing"))
    assert out.status == "no_route"


def test_unverified_requires_opt_in(tmp_path: Path) -> None:
    make_workspace(tmp_path, [bad_entry("ok", "bad-a", trust="unverified")])
    request = AskRequest(intent="run it", capability="bad.thing")
    assert forger(tmp_path).ask(request).status == "no_route"
    opted = AskRequest(intent="run it", capability="bad.thing", allow_unverified=True)
    assert forger(tmp_path).ask(opted).status == "ok"


def test_secrets_never_persisted(tmp_path: Path) -> None:
    make_workspace(tmp_path, [])
    write_file(tmp_path, ".env", "AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMIK7MDENGbPxRfiCYEXAMPLEKEY\n")
    write_file(tmp_path, "notes.txt", "token=abc123secretvalue\n")
    out = forger(tmp_path).ask(AskRequest(intent="eco password=hunter2xyz"))
    assert out.status == "ok"
    blob = "".join(p.read_text(encoding="utf-8")
                   for p in (tmp_path / ".forge" / "runs").rglob("*.json"))
    for secret in ("hunter2xyz", "abc123secretvalue", "wJalrXUtnFEMIK7MDENGbPxRfiCYEXAMPLEKEY"):
        assert secret not in blob
```

- [ ] **Step 2: Ver falhar**

Run: `$PY -m pytest tests/test_forger.py`
Expected: FAIL `ModuleNotFoundError: No module named 'theforge.forger'`

- [ ] **Step 3: `src/theforge/forger/orchestrator.py`**

```python
"""The Forger: task -> route -> health -> context -> execute -> receipt.

Every artifact is persisted as soon as it exists, so a run that fails midway is
still explainable. No path reports success without a valid ExecutionResult.
"""

import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Literal

from theforge.context import build_context_pack, scan_workspace
from theforge.contracts import (
    Candidate,
    ContractError,
    ErrorInfo,
    ExecuteRequest,
    ExecutionReceipt,
    ExecutionResult,
    Metric,
    Metrics,
    ReceiptInputs,
    ReceiptProvider,
    RoutingDecision,
    Selection,
    TaskSpec,
    from_dict,
    to_dict,
)
from theforge.contracts.canonical import utc_now
from theforge.contracts.types import BudgetProfile, Outcome
from theforge.meta import PRODUCER, VERSION
from theforge.protocol import SubprocessTransport, TransportError, TransportFactory
from theforge.registry import Registry, RegistryRecord, check_health
from theforge.routing import MIN_SIGNAL_TYPES, route
from theforge.routing.signals import workspace_dependencies
from theforge.runs import RunStore, new_run_id

EXECUTE_TIMEOUTS: dict[str, float] = {"economy": 60.0, "balanced": 180.0, "max": 600.0}


@dataclass(frozen=True, kw_only=True)
class AskRequest:
    intent: str
    targets: list[str] = field(default_factory=lambda: ["."])
    capability: str | None = None
    action: str | None = None
    profile: BudgetProfile = "balanced"
    allow_unverified: bool = False


@dataclass(frozen=True, kw_only=True)
class AskOutcome:
    run_id: str
    status: Outcome
    decision: RoutingDecision
    receipt: ExecutionReceipt
    result: ExecutionResult | None = None
    error: ErrorInfo | None = None


@dataclass
class _Trace:
    run_id: str
    started_at: str
    task_sha: str
    routing_sha: str | None = None
    context_sha: str | None = None
    result_sha: str | None = None
    record: RegistryRecord | None = None


class Forger:
    def __init__(
        self, root: Path, registry: Registry, store: RunStore, *,
        transport_factory: TransportFactory = SubprocessTransport,
        execute_timeout: float | None = None,
    ) -> None:
        self.root = root.resolve()
        self.registry = registry
        self.store = store
        self.transport_factory = transport_factory
        self.execute_timeout = execute_timeout

    def ask(self, request: AskRequest) -> AskOutcome:
        run_id = new_run_id()
        started = utc_now()
        self.store.create(run_id)
        task = TaskSpec(
            producer=PRODUCER, created_at=started, id=run_id, intent=request.intent,
            workspace_root=str(self.root), targets=list(request.targets),
            budget_profile=request.profile, requested_capability=request.capability,
            requested_action=request.action,
        )
        trace = _Trace(run_id=run_id, started_at=started,
                       task_sha=self.store.write(run_id, "task", task))
        records = {r.entry.id: r for r in self.registry.records()}
        scan = scan_workspace(self.root, task.targets)
        decision = route(task, list(records.values()), scan.files,
                         workspace_dependencies(self.root),
                         allow_unverified=request.allow_unverified)
        if decision.status != "routed":
            trace.routing_sha = self.store.write(run_id, "routing", decision)
            return self._finish(trace, decision, decision.status)

        decision, record, health_error = self._select_healthy(decision, records)
        trace.routing_sha = self.store.write(run_id, "routing", decision)
        if record is None or record.manifest is None:
            return self._finish(trace, decision, "provider_failure", error=health_error)
        trace.record = record

        selection = decision.selected[0]
        capability = record.manifest.capability(selection.capability)
        globs = list(capability.signals.file_globs) if capability else []
        pack = build_context_pack(task, record.entry.id, globs, scan)
        trace.context_sha = self.store.write(run_id, "context", pack)

        payload = to_dict(ExecuteRequest(task=task, capability=selection.capability,
                                         action=selection.action, context=pack))
        started_exec = time.perf_counter()
        try:
            response = self.transport_factory(record.entry.argv).call(
                "execute", payload, timeout=self._timeout(task),
                cwd=self.store.work_dir(run_id))
        except TransportError as exc:
            return self._finish(trace, decision, "provider_failure",
                                error=ErrorInfo(code=exc.code, detail=exc.detail))
        duration_ms = (time.perf_counter() - started_exec) * 1000

        if response.status in ("refused", "error"):
            status: Outcome = "refused" if response.status == "refused" else "provider_failure"
            error = response.error or ErrorInfo(code="FORGE-PROTO-SCHEMA",
                                                detail="error response without error body")
            return self._finish(trace, decision, status, error=error)
        try:
            result = from_dict(ExecutionResult, response.payload, "$.payload")
        except ContractError as exc:
            return self._finish(trace, decision, "provider_failure", error=ErrorInfo(
                code="FORGE-PROTO-SCHEMA", detail=f"execute: {exc}"))
        result_status: Literal["ok", "partial"] = "ok" if response.status == "ok" else "partial"
        result = replace(result, status=result_status, metrics=Metrics(
            duration_ms=Metric(value=round(duration_ms, 3), kind="measured"),
            context_bytes=Metric(value=float(pack.used_bytes), kind="measured"),
            tokens=Metric(value=None, kind="unknown"),
        ))
        trace.result_sha = self.store.write(run_id, "result", result)
        return self._finish(trace, decision, result_status, result=result)

    def _timeout(self, task: TaskSpec) -> float:
        if self.execute_timeout is not None:
            return self.execute_timeout
        return EXECUTE_TIMEOUTS[task.budget_profile]

    def _select_healthy(
        self, decision: RoutingDecision, records: dict[str, RegistryRecord]
    ) -> tuple[RoutingDecision, RegistryRecord | None, ErrorInfo | None]:
        primary = decision.selected[0]
        tried: list[str] = []
        last_error: ErrorInfo | None = None
        for candidate in self._fallback_order(decision):
            record = records[candidate.provider]
            health = check_health(record, transport_factory=self.transport_factory)
            if health.error is None:
                if not tried:
                    return decision, record, None
                capability = (record.manifest.capability(candidate.capability)
                              if record.manifest else None)
                action = primary.action
                if capability is not None and action not in capability.actions:
                    action = capability.default_action
                switched = replace(
                    decision,
                    selected=[Selection(provider=candidate.provider,
                                        capability=candidate.capability, action=action)],
                    fallbacks_used=tried,
                    reason=f"{decision.reason}; fallback to {candidate.provider} after "
                           f"unhealthy {', '.join(tried)}",
                )
                return switched, record, None
            tried.append(f"{candidate.provider}:{health.error.code}")
            last_error = health.error
        return replace(decision, fallbacks_used=tried), None, last_error

    @staticmethod
    def _fallback_order(decision: RoutingDecision) -> list[Candidate]:
        primary = decision.selected[0]
        key = (primary.provider, primary.capability)
        first = [c for c in decision.candidates if (c.provider, c.capability) == key]
        rest = [c for c in decision.candidates
                if (c.provider, c.capability) != key
                and (len(c.rank_key) == 1 or c.rank_key[0] >= MIN_SIGNAL_TYPES)]
        return first + rest

    def _finish(
        self, trace: _Trace, decision: RoutingDecision, status: Outcome, *,
        result: ExecutionResult | None = None, error: ErrorInfo | None = None,
    ) -> AskOutcome:
        record = trace.record
        provider = None
        if record is not None and record.manifest is not None:
            provider = ReceiptProvider(id=record.entry.id, version=record.manifest.version,
                                       trust=record.entry.trust,
                                       manifest_sha256=record.manifest_sha256)
        receipt = ExecutionReceipt(
            producer=PRODUCER, created_at=utc_now(), status=status, run_id=trace.run_id,
            forge_version=VERSION,
            inputs=ReceiptInputs(task_sha256=trace.task_sha, routing_sha256=trace.routing_sha,
                                 context_sha256=trace.context_sha),
            provider=provider, result_sha256=trace.result_sha, started_at=trace.started_at,
            finished_at=utc_now(), error=error,
        )
        self.store.write(trace.run_id, "receipt", receipt)
        return AskOutcome(run_id=trace.run_id, status=status, decision=decision,
                          receipt=receipt, result=result, error=error)
```

- [ ] **Step 4: `src/theforge/forger/__init__.py`**

```python
"""The Forger: orchestrator of a single routed run."""

from theforge.forger.orchestrator import AskOutcome, AskRequest, Forger

__all__ = ["AskOutcome", "AskRequest", "Forger"]
```

- [ ] **Step 5: Ver passar**

Run: `$PY -m pytest tests/test_forger.py`
Expected: `17 passed`

- [ ] **Step 6: Commit**

```bash
git add src/theforge/forger tests/test_forger.py
git commit -m "feat(forger): orchestrate route, health fallback, context, execute and receipts"
```

---

### Task 15: Doctor (environment resolver)

**Files:**
- Create: `src/theforge/environment/__init__.py`, `src/theforge/environment/doctor.py`
- Test: `tests/test_doctor.py`

- [ ] **Step 1: Teste falhando** — `tests/test_doctor.py`

```python
from pathlib import Path

from helpers import make_workspace

from theforge.environment import detect_host, run_doctor
from theforge.registry import Registry


def test_detect_host() -> None:
    assert detect_host({"CLAUDECODE": "1"}) == "claude-code"
    assert detect_host({"CODEX_HOME": "x"}) == "codex"
    assert detect_host({"CI": "true"}) == "ci"
    assert detect_host({}) == "terminal"


def test_doctor_uninitialized(tmp_path: Path) -> None:
    report = run_doctor(tmp_path, Registry(None), env={})
    checks = {c["name"]: c for c in report["checks"]}
    assert checks["python"]["status"] == "ok"
    assert checks["workspace"]["status"] == "warn"
    assert checks["provider:echo-forge"]["status"] == "ok"
    assert checks["host"]["detail"] == "terminal"
    assert report["healthy"] is True


def test_doctor_missing_provider_warns(tmp_path: Path) -> None:
    make_workspace(tmp_path, [{"id": "ghost-forge",
                               "argv": ["definitely-not-a-real-forge-binary"],
                               "trust": "local"}])
    report = run_doctor(tmp_path, Registry(tmp_path / ".forge"), env={})
    checks = {c["name"]: c for c in report["checks"]}
    assert checks["workspace"]["status"] == "ok"
    assert checks["provider:ghost-forge"]["status"] == "warn"
    assert "FORGE-PROVIDER-NOT-READY" in checks["provider:ghost-forge"]["detail"]
    assert report["healthy"] is True
```

- [ ] **Step 2: Ver falhar**

Run: `$PY -m pytest tests/test_doctor.py`
Expected: FAIL `ModuleNotFoundError: No module named 'theforge.environment'`

- [ ] **Step 3: `src/theforge/environment/doctor.py`**

```python
"""`theforge doctor`: host, workspace and provider readiness. Read-only, offline."""

import os
import platform
import shutil
import sys
import tempfile
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from theforge.meta import VERSION
from theforge.protocol import SubprocessTransport, TransportFactory
from theforge.registry import Registry, check_health

REPORT_SCHEMA = "theforge/EnvironmentReport/v0"


@dataclass(frozen=True, kw_only=True)
class Check:
    name: str
    status: Literal["ok", "warn", "fail"]
    detail: str


def detect_host(env: Mapping[str, str]) -> str:
    if env.get("CLAUDECODE") == "1" or "CLAUDE_CODE_ENTRYPOINT" in env:
        return "claude-code"
    if any(key.startswith("CODEX_") for key in env):
        return "codex"
    if env.get("CI"):
        return "ci"
    return "terminal"


def _writable(directory: Path) -> bool:
    try:
        with tempfile.NamedTemporaryFile(dir=directory):
            return True
    except OSError:
        return False


def run_doctor(
    root: Path, registry: Registry, *, env: Mapping[str, str] | None = None,
    transport_factory: TransportFactory = SubprocessTransport,
) -> dict[str, Any]:
    environment = os.environ if env is None else env
    git = shutil.which("git")
    checks = [
        Check(name="os", status="ok", detail=f"{platform.system()} {platform.release()}"),
        Check(name="architecture", status="ok", detail=platform.machine() or "unknown"),
        Check(name="python", status="ok" if sys.version_info >= (3, 11) else "fail",
              detail=platform.python_version()),
        Check(name="git", status="ok" if git else "warn", detail=git or "not found on PATH"),
        Check(name="host", status="ok", detail=detect_host(environment)),
    ]
    forge_dir = registry.forge_dir
    if forge_dir is None:
        checks.append(Check(name="workspace", status="warn",
                            detail=f"{root} not initialized (run `theforge init`)"))
    else:
        checks.append(Check(name="workspace", status="ok" if _writable(forge_dir) else "fail",
                            detail=str(forge_dir)))
    for record in registry.records():
        health = check_health(record, transport_factory=transport_factory)
        healthy = health.status in ("ok", "degraded")
        status: Literal["ok", "warn", "fail"] = "ok"
        if not healthy:
            status = "fail" if record.entry.trust == "builtin" else "warn"
        detail = f"{record.state}/{health.status}"
        if health.error is not None:
            detail += f" {health.error.code}"
        checks.append(Check(name=f"provider:{record.entry.id}", status=status, detail=detail))
    return {
        "schema": REPORT_SCHEMA, "forge_version": VERSION, "root": str(root),
        "checks": [asdict(c) for c in checks],
        "healthy": all(c.status != "fail" for c in checks),
    }
```

- [ ] **Step 4: `src/theforge/environment/__init__.py`**

```python
"""Environment resolver (`theforge doctor`)."""

from theforge.environment.doctor import Check, detect_host, run_doctor

__all__ = ["Check", "detect_host", "run_doctor"]
```

- [ ] **Step 5: Ver passar**

Run: `$PY -m pytest tests/test_doctor.py`
Expected: `3 passed`

- [ ] **Step 6: Commit**

```bash
git add src/theforge/environment tests/test_doctor.py
git commit -m "feat(environment): add offline doctor for host, workspace and providers"
```

---
### Task 16: CLI `theforge` / `forge`

**Files:**
- Create: `src/theforge/cli/__init__.py`, `main.py`, `commands.py`, `render.py`, `src/theforge/__main__.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Teste falhando** — `tests/test_cli.py`

```python
import json
from pathlib import Path

import pytest
from helpers import API_ENTRY, SPARK_ENTRY, bad_entry, case_b, make_workspace

from theforge.cli.main import main


def run(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, str, str]:
    code = main(list(argv))
    out, err = capsys.readouterr()
    return code, out, err


def test_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as info:
        main(["--version"])
    assert info.value.code == 0
    assert "theforge 0.1.0" in capsys.readouterr().out


def test_init_is_idempotent(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = run(capsys, "init", "--root", str(tmp_path), "--json")
    assert code == 0 and ".forge/config/providers.toml" in json.loads(out)["created"]
    code, out, _ = run(capsys, "init", "--root", str(tmp_path), "--json")
    assert code == 0 and json.loads(out)["created"] == []


def test_registry_and_capabilities(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    make_workspace(tmp_path, [API_ENTRY])
    root = str(tmp_path)
    code, out, _ = run(capsys, "registry", "refresh", "--root", root, "--json")
    providers = {p["id"]: p for p in json.loads(out)["providers"]}
    assert code == 0 and providers["fixture-api"]["state"] == "ready"
    code, out, _ = run(capsys, "registry", "show", "fixture-api", "--root", root, "--json")
    assert code == 0 and json.loads(out)["manifest"]["id"] == "fixture-api"
    code, out, _ = run(capsys, "capabilities", "list", "--root", root)
    assert code == 0 and "demo.echo" in out and "api.contract" in out
    code, out, _ = run(capsys, "capabilities", "search", "openapi", "--root", root, "--json")
    assert [c["id"] for c in json.loads(out)["capabilities"]] == ["api.contract"]
    code, out, _ = run(capsys, "capabilities", "search", "iceberg", "--root", root, "--json")
    assert json.loads(out)["capabilities"] == []
    code, out, _ = run(capsys, "providers", "health", "--root", root, "--json")
    assert code == 0


def test_ask_requires_init(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, _, err = run(capsys, "ask", "oi", "--root", str(tmp_path))
    assert code == 2 and "theforge init" in err


def test_ask_exit_codes_and_explain(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    make_workspace(tmp_path, [SPARK_ENTRY, API_ENTRY, bad_entry("refuse", "bad-a")])
    case_b(tmp_path)
    root = str(tmp_path)
    code, out, _ = run(capsys, "ask", "avalie esse contrato OpenAPI", "--target", "api",
                       "--root", root, "--json")
    data = json.loads(out)
    assert code == 0 and data["status"] == "ok"
    code, out, _ = run(capsys, "explain", data["run_id"], "--root", root)
    assert code == 0 and "fixture-api api.contract:review" in out
    code, _, _ = run(capsys, "ask", "run it", "--capability", "bad.thing", "--root", root)
    assert code == 4
    code, _, err = run(capsys, "ask", "x", "--capability", "api.contract", "--action", "delete",
                       "--root", root)
    assert code == 2 and "not offered" in err


def test_ask_ambiguous_exit_3(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    make_workspace(tmp_path, [SPARK_ENTRY, API_ENTRY])
    code, out, _ = run(capsys, "ask", "performance da api", "--root", str(tmp_path))
    assert code == 3 and "--capability" in out


def test_explain_errors(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    make_workspace(tmp_path, [])
    root = str(tmp_path)
    assert run(capsys, "explain", "20260101T000000Z-deadbeef", "--root", root)[0] == 2
    assert run(capsys, "explain", "../escape", "--root", root)[0] == 2


def test_persistence_failure_exit_5(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    make_workspace(tmp_path, [])
    runs = tmp_path / ".forge" / "runs"
    runs.rmdir()
    runs.write_text("not a dir", encoding="utf-8")
    code, _, err = run(capsys, "ask", "eco", "--capability", "demo.echo",
                       "--root", str(tmp_path))
    assert code == 5 and "persistence error" in err


def test_status_and_doctor(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    make_workspace(tmp_path, [])
    root = str(tmp_path)
    code, out, _ = run(capsys, "status", "--root", root, "--json")
    assert code == 0 and json.loads(out)["initialized"] is True
    code, out, _ = run(capsys, "doctor", "--root", root, "--json")
    assert code == 0 and any(c["name"] == "python" for c in json.loads(out)["checks"])
```

- [ ] **Step 2: Ver falhar**

Run: `$PY -m pytest tests/test_cli.py`
Expected: FAIL `ModuleNotFoundError: No module named 'theforge.cli'`

- [ ] **Step 3: `src/theforge/cli/__init__.py` e `src/theforge/__main__.py`**

```python
"""Command-line interface: parsing and rendering only."""
```

```python
"""python -m theforge"""

from theforge.cli.main import main

raise SystemExit(main())
```

- [ ] **Step 4: `src/theforge/cli/main.py`**

```python
"""Argument parsing and exit-code mapping for `theforge` / `forge`."""

import argparse
import sys
from collections.abc import Sequence

from theforge import __version__
from theforge.cli import commands
from theforge.errors import PersistenceError, UsageError


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--root", default=".", help="workspace root (default: current dir)")
    common.add_argument("--json", action="store_true", help="machine-readable JSON output")

    parser = argparse.ArgumentParser(
        prog="theforge", description="The Forge: one entry point, many specialists.")
    parser.add_argument("--version", action="version", version=f"theforge {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", parents=[common], help="create .forge/ in the workspace") \
        .set_defaults(handler=commands.cmd_init)
    sub.add_parser("doctor", parents=[common], help="inspect host, workspace and providers") \
        .set_defaults(handler=commands.cmd_doctor)
    sub.add_parser("status", parents=[common], help="summarize workspace state") \
        .set_defaults(handler=commands.cmd_status)

    registry = sub.add_parser("registry", help="provider registry") \
        .add_subparsers(dest="registry_command", required=True)
    registry.add_parser("list", parents=[common]) \
        .set_defaults(handler=commands.cmd_registry_list)
    registry.add_parser("refresh", parents=[common]) \
        .set_defaults(handler=commands.cmd_registry_refresh)
    show = registry.add_parser("show", parents=[common])
    show.add_argument("provider_id")
    show.set_defaults(handler=commands.cmd_registry_show)

    caps = sub.add_parser("capabilities", help="declared capabilities") \
        .add_subparsers(dest="capabilities_command", required=True)
    cap_list = caps.add_parser("list", parents=[common])
    cap_list.add_argument("--provider")
    cap_list.set_defaults(handler=commands.cmd_capabilities_list)
    cap_search = caps.add_parser("search", parents=[common])
    cap_search.add_argument("query")
    cap_search.set_defaults(handler=commands.cmd_capabilities_search)

    providers = sub.add_parser("providers", help="provider operations") \
        .add_subparsers(dest="providers_command", required=True)
    providers.add_parser("health", parents=[common]) \
        .set_defaults(handler=commands.cmd_providers_health)

    ask = sub.add_parser("ask", parents=[common], help="route a task to a specialist")
    ask.add_argument("intent")
    ask.add_argument("--capability")
    ask.add_argument("--action")
    ask.add_argument("--profile", choices=["economy", "balanced", "max"], default="balanced")
    ask.add_argument("--target", dest="targets", action="append")
    ask.add_argument("--allow-unverified", action="store_true")
    ask.set_defaults(handler=commands.cmd_ask)

    explain = sub.add_parser("explain", parents=[common], help="explain a past run")
    explain.add_argument("run_id")
    explain.set_defaults(handler=commands.cmd_explain)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.handler(args))
    except UsageError as exc:
        print(f"theforge: error: {exc}", file=sys.stderr)
        return 2
    except PersistenceError as exc:
        print(f"theforge: persistence error: {exc}", file=sys.stderr)
        return 5
```

- [ ] **Step 5: `src/theforge/cli/commands.py`**

```python
"""Command handlers: gather data, render (text or JSON), return the exit code."""

import argparse
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from theforge.cli import render
from theforge.contracts import to_dict
from theforge.environment import run_doctor
from theforge.errors import UsageError
from theforge.forger import AskRequest, Forger
from theforge.registry import Registry, RegistryRecord, check_health
from theforge.routing.signals import normalize_tokens
from theforge.runs import ARTIFACTS, RunStore
from theforge.state import find_forge_dir, init_workspace, require_forge_dir

EXIT_BY_STATUS = {"ok": 0, "partial": 0, "ambiguous": 3, "no_route": 3, "refused": 4,
                  "provider_failure": 4}


def _root(args: argparse.Namespace) -> Path:
    root = Path(args.root).resolve()
    if not root.is_dir():
        raise UsageError(f"workspace root {root} is not a directory")
    return root


def _emit(args: argparse.Namespace, data: dict[str, Any],
          text: Callable[[dict[str, Any]], str]) -> None:
    if args.json:
        print(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False))
    else:
        print(text(data))


def _warn(registry: Registry) -> None:
    for warning in registry.warnings:
        print(f"theforge: warning: {warning}", file=sys.stderr)


def _summary(record: RegistryRecord) -> dict[str, Any]:
    manifest = record.manifest
    return {
        "id": record.entry.id, "trust": record.entry.trust, "source": record.entry.source,
        "state": record.state, "version": manifest.version if manifest else None,
        "protocol": record.protocol, "error": record.error,
        "capabilities": [c.id for c in manifest.capabilities] if manifest else [],
    }


def _capability_rows(records: list[RegistryRecord],
                     provider: str | None = None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for record in records:
        if record.manifest is None or (provider and record.entry.id != provider):
            continue
        for cap in record.manifest.capabilities:
            rows.append({
                "provider": record.entry.id, "trust": record.entry.trust, "id": cap.id,
                "actions": list(cap.actions), "default_action": cap.default_action,
                "state": cap.state, "operation_class": cap.operation_class,
                "description": cap.description, "keywords": list(cap.signals.keywords),
            })
    return sorted(rows, key=lambda row: (row["id"], row["provider"]))


def cmd_init(args: argparse.Namespace) -> int:
    root = _root(args)
    created = init_workspace(root)
    _emit(args, {"forge_dir": str(root / ".forge"), "created": created}, render.init)
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    root = _root(args)
    registry = Registry(find_forge_dir(root))
    report = run_doctor(root, registry)
    _warn(registry)
    _emit(args, report, render.doctor)
    return 0 if report["healthy"] else 1


def cmd_status(args: argparse.Namespace) -> int:
    root = _root(args)
    forge_dir = find_forge_dir(root)
    runs = RunStore(forge_dir).list_runs() if forge_dir else []
    cached = sorted(p.stem for p in (forge_dir / "registry").glob("*.json")) if forge_dir else []
    data = {"root": str(root), "initialized": forge_dir is not None, "cached_providers": cached,
            "runs": len(runs), "last_run": runs[-1] if runs else None}
    _emit(args, data, render.status)
    return 0


def _list(args: argparse.Namespace, refresh: bool) -> int:
    registry = Registry(find_forge_dir(_root(args)))
    records = registry.refresh() if refresh else registry.records()
    _warn(registry)
    _emit(args, {"providers": [_summary(r) for r in records]}, render.providers)
    return 0


def cmd_registry_list(args: argparse.Namespace) -> int:
    return _list(args, refresh=False)


def cmd_registry_refresh(args: argparse.Namespace) -> int:
    return _list(args, refresh=True)


def cmd_registry_show(args: argparse.Namespace) -> int:
    registry = Registry(find_forge_dir(_root(args)))
    record = registry.get(args.provider_id)
    _warn(registry)
    data = {**_summary(record), "argv": record.entry.argv,
            "manifest": to_dict(record.manifest) if record.manifest else None,
            "manifest_sha256": record.manifest_sha256}
    _emit(args, data, render.provider_detail)
    return 0


def cmd_capabilities_list(args: argparse.Namespace) -> int:
    registry = Registry(find_forge_dir(_root(args)))
    rows = _capability_rows(registry.records(), args.provider)
    _warn(registry)
    _emit(args, {"capabilities": rows}, render.capabilities)
    return 0


def cmd_capabilities_search(args: argparse.Namespace) -> int:
    query = set(normalize_tokens(args.query))
    if not query:
        raise UsageError("empty search query")
    registry = Registry(find_forge_dir(_root(args)))
    rows = [
        row for row in _capability_rows(registry.records())
        if query <= set(normalize_tokens(" ".join([row["id"], row["description"],
                                                    *row["keywords"]])))
    ]
    _warn(registry)
    _emit(args, {"query": args.query, "capabilities": rows}, render.capabilities)
    return 0


def cmd_providers_health(args: argparse.Namespace) -> int:
    registry = Registry(find_forge_dir(_root(args)))
    rows = []
    for record in registry.records():
        outcome = check_health(record)
        rows.append({"id": record.entry.id, "trust": record.entry.trust,
                     "status": outcome.status,
                     "error": to_dict(outcome.error) if outcome.error else None})
    _warn(registry)
    _emit(args, {"providers": rows}, render.health)
    return 0 if all(row["status"] in ("ok", "degraded") for row in rows) else 1


def cmd_ask(args: argparse.Namespace) -> int:
    root = _root(args)
    forge_dir = require_forge_dir(root)
    registry = Registry(forge_dir)
    outcome = Forger(root, registry, RunStore(forge_dir)).ask(AskRequest(
        intent=args.intent, targets=args.targets or ["."], capability=args.capability,
        action=args.action, profile=args.profile, allow_unverified=args.allow_unverified,
    ))
    _warn(registry)
    data = {
        "run_id": outcome.run_id, "status": outcome.status,
        "decision": to_dict(outcome.decision),
        "result": to_dict(outcome.result) if outcome.result else None,
        "error": to_dict(outcome.error) if outcome.error else None,
    }
    _emit(args, data, render.ask)
    return EXIT_BY_STATUS[outcome.status]


def cmd_explain(args: argparse.Namespace) -> int:
    store = RunStore(require_forge_dir(_root(args)))
    try:
        run_dir = store.run_dir(args.run_id)
    except ValueError as exc:
        raise UsageError(str(exc)) from exc
    if not run_dir.is_dir():
        raise UsageError(f"unknown run {args.run_id}")
    data: dict[str, Any] = {"run_id": args.run_id}
    for name in ARTIFACTS:
        data[name] = store.read_optional(args.run_id, name)
    _emit(args, data, render.explain)
    return 0
```

- [ ] **Step 6: `src/theforge/cli/render.py`**

```python
"""Human-readable renderers. Pure functions: dict in, text out."""

from typing import Any


def init(data: dict[str, Any]) -> str:
    if not data["created"]:
        return f"{data['forge_dir']} already initialized"
    return "\n".join([f"Initialized {data['forge_dir']}",
                      *(f"  created {path}" for path in data["created"])])


def doctor(data: dict[str, Any]) -> str:
    lines = [f"The Forge {data['forge_version']} - {data['root']}"]
    for check in data["checks"]:
        lines.append(f"{check['name']:.<32} {check['status']:<5} {check['detail']}")
    lines.append("healthy" if data["healthy"] else "UNHEALTHY")
    return "\n".join(lines)


def status(data: dict[str, Any]) -> str:
    if not data["initialized"]:
        return f"{data['root']}: not initialized (run `theforge init`)"
    return "\n".join([
        f"Workspace:  {data['root']}",
        f"Providers:  {', '.join(data['cached_providers']) or 'none cached'}",
        f"Runs:       {data['runs']} (last: {data['last_run'] or '-'})",
    ])


def providers(data: dict[str, Any]) -> str:
    lines = []
    for p in data["providers"]:
        line = (f"{p['id']:<20} {p['state']:<13} trust={p['trust']:<10} "
                f"source={p['source']:<8} version={p['version'] or '-'}")
        if p["error"]:
            line += f"  error: {p['error']}"
        lines.append(line)
    return "\n".join(lines) or "no providers"


def provider_detail(data: dict[str, Any]) -> str:
    lines = [providers({"providers": [data]}),
             f"argv:      {' '.join(data['argv'])}",
             f"protocol:  {data['protocol'] or '-'}",
             f"manifest:  {data['manifest_sha256'] or '-'}"]
    for cap in (data["manifest"] or {}).get("capabilities", []):
        lines.append(f"  {cap['id']:<28} actions={','.join(cap['actions'])} "
                     f"state={cap['state']} class={cap['operation_class']}")
    return "\n".join(lines)


def capabilities(data: dict[str, Any]) -> str:
    rows = data["capabilities"]
    if not rows:
        return "no capabilities found"
    lines = []
    for c in rows:
        line = f"{c['id']:<28} {c['provider']:<20} actions={','.join(c['actions'])} " \
               f"state={c['state']}"
        if c["description"]:
            line += f"  - {c['description']}"
        lines.append(line)
    return "\n".join(lines)


def health(data: dict[str, Any]) -> str:
    lines = []
    for p in data["providers"]:
        line = f"{p['id']:<20} {p['status']}"
        if p["error"]:
            line += f"  {p['error']['code']}: {p['error']['detail']}"
        lines.append(line)
    return "\n".join(lines) or "no providers"


def ask(data: dict[str, Any]) -> str:
    decision = data["decision"]
    lines = [f"Run {data['run_id']}: {data['status']}"]
    if decision["selected"]:
        sel = decision["selected"][0]
        lines.append(f"Selected:   {sel['provider']} {sel['capability']}:{sel['action']} "
                     f"(confidence {decision['confidence']['level']})")
    lines.append(f"Reason:     {decision['reason']}")
    if data["status"] in ("ambiguous", "no_route"):
        for cand in decision["candidates"]:
            lines.append(f"  candidate {cand['provider']}/{cand['capability']} "
                         f"rank={cand['rank_key']}")
        lines.append("Hint:       pass --capability <id> (see `theforge capabilities list`)")
    result = data["result"]
    if result:
        lines.append(f"Findings:   {len(result['findings'])}   "
                     f"Evidence: {len(result['evidence'])}")
        lines.extend(f"  [{f['severity']}] {f['title']}" for f in result["findings"])
    error = data["error"]
    if error:
        lines.append(f"Error:      {error['code']}: {error['detail']}")
        if error.get("unlock"):
            lines.append(f"Unlock:     {error['unlock']}")
    lines.append(f"Explain:    theforge explain {data['run_id']}")
    return "\n".join(lines)


def _signals(matched: dict[str, list[str]]) -> str:
    parts = [f"{key}[{','.join(hits)}]" for key in ("dependencies", "file_globs", "keywords")
             if (hits := matched.get(key))]
    return " ".join(parts) or "requested"


def explain(data: dict[str, Any]) -> str:
    task = data.get("task") or {}
    routing = data.get("routing") or {}
    context = data.get("context")
    result = data.get("result")
    receipt = data.get("receipt") or {}
    lines = [f"Run:         {data['run_id']}  status: {receipt.get('status', 'incomplete')}"]
    if task:
        lines.append(f"Task:        \"{task['intent']}\" (targets: {', '.join(task['targets'])};"
                     f" profile: {task['budget_profile']})")
    if routing:
        candidates = routing.get("candidates", [])
        if not candidates:
            lines.append("Candidates:  none")
        for index, cand in enumerate(candidates):
            label = "Candidates:" if index == 0 else ""
            lines.append(f"{label:<13}{cand['provider']}/{cand['capability']}  "
                         f"{_signals(cand['matched'])}  rank={cand['rank_key']}")
        selected = ", ".join(f"{s['provider']} {s['capability']}:{s['action']} ({s['role']})"
                             for s in routing.get("selected", [])) or "none"
        lines.append(f"Selected:    {selected}   pattern: {routing['pattern']}")
        lines.append(f"Reason:      {routing['reason']}")
        conf = routing["confidence"]
        lines.append(f"Confidence:  {conf['level']}   measured: {conf['measured_signals']}"
                     f"   unresolved: {conf['unresolved']}")
        lines.append(f"Fallbacks:   {', '.join(routing.get('fallbacks_used', [])) or 'none'}")
    if context:
        lines.append(f"Context:     {len(context['files'])} files, {context['used_bytes']}/"
                     f"{context['budget_bytes']} bytes ({context['status']}); "
                     f"excluded {len(context['excluded'])}")
    if result:
        lines.append(f"Result:      {result['status']}: {len(result['findings'])} findings, "
                     f"{len(result['evidence'])} evidence")
    error = receipt.get("error")
    if error:
        unlock = f" (unlock: {error['unlock']})" if error.get("unlock") else ""
        lines.append(f"Error:       {error['code']}: {error['detail']}{unlock}")
    if receipt:
        inputs = receipt["inputs"]
        hashes = " ".join(f"{key.removesuffix('_sha256')}={(value or '-')[:12]}"
                          for key, value in sorted(inputs.items()))
        lines.append(f"Receipt:     {hashes} result={(receipt.get('result_sha256') or '-')[:12]}")
    return "\n".join(lines)
```

- [ ] **Step 7: Ver passar**

Run: `$PY -m pytest tests/test_cli.py`
Expected: `9 passed`

- [ ] **Step 8: Rodar suite inteira**

Run: `$PY -m pytest`
Expected: tudo verde (skips só de symlink, se houver)

- [ ] **Step 9: Commit**

```bash
git add src/theforge/cli src/theforge/__main__.py tests/test_cli.py
git commit -m "feat(cli): add theforge/forge CLI with init, doctor, registry, capabilities, ask, explain"
```

---
### Task 17: E2E de onboarding e golden do `explain`

**Files:**
- Create: `tests/golden/explain_case_b.txt`
- Test: `tests/test_e2e.py`

- [ ] **Step 1: Criar `tests/golden/explain_case_b.txt`** (newline final; `<RUN>`/`<HASH>` normalizados)

```text
Run:         <RUN>  status: ok
Task:        "avalie esse contrato OpenAPI" (targets: api; profile: balanced)
Candidates:  fixture-api/api.contract  file_globs[openapi.yaml] keywords[openapi,contrato]  rank=[2, 0, 1, 2]
Selected:    fixture-api api.contract:review (primary)   pattern: route
Reason:      fixture-api api.contract matched 2 signal types (file_globs:openapi.yaml; keywords:openapi,contrato)
Confidence:  high   measured: ['file_globs:openapi.yaml', 'keywords:openapi,contrato']   unresolved: []
Fallbacks:   none
Context:     1 files, 64/262144 bytes (complete); excluded 0
Result:      ok: 1 findings, 1 evidence
Receipt:     context=<HASH> routing=<HASH> task=<HASH> result=<HASH>
```

- [ ] **Step 2: Teste** — `tests/test_e2e.py`

```python
"""Onboarding flow through the real CLI in a subprocess (spec §14, criteria 1-4)."""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

from helpers import API_ENTRY, SPARK_ENTRY, case_b, write_providers

GOLDEN = Path(__file__).parent / "golden" / "explain_case_b.txt"


def cli(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    return subprocess.run([sys.executable, "-m", "theforge", *args, "--root", str(root)],
                          capture_output=True, text=True, encoding="utf-8", timeout=120,
                          env=env)


def normalize(text: str) -> str:
    text = re.sub(r"\d{8}T\d{6}Z-[0-9a-f]{8}", "<RUN>", text)
    return re.sub(r"\b[0-9a-f]{12}\b", "<HASH>", text)


def test_onboarding_flow(tmp_path: Path) -> None:
    assert cli(tmp_path, "init").returncode == 0
    write_providers(tmp_path / ".forge", [SPARK_ENTRY, API_ENTRY])
    case_b(tmp_path)

    r = cli(tmp_path, "registry", "refresh", "--json")
    assert r.returncode == 0, r.stderr
    states = {p["id"]: p["state"] for p in json.loads(r.stdout)["providers"]}
    assert states == {"echo-forge": "ready", "fixture-api": "ready", "fixture-spark": "ready"}

    r = cli(tmp_path, "capabilities", "list", "--json")
    ids = sorted(c["id"] for c in json.loads(r.stdout)["capabilities"])
    assert ids == ["api.contract", "demo.echo", "demo.inspect", "spark.performance"]

    r = cli(tmp_path, "ask", "avalie esse contrato OpenAPI", "--target", "api", "--json")
    assert r.returncode == 0, r.stderr
    run_id = json.loads(r.stdout)["run_id"]

    r = cli(tmp_path, "explain", run_id)
    assert r.returncode == 0, r.stderr
    actual = normalize(r.stdout)
    if os.environ.get("UPDATE_GOLDEN") == "1":
        GOLDEN.write_text(actual, encoding="utf-8", newline="\n")
    assert actual == GOLDEN.read_text(encoding="utf-8")
```

- [ ] **Step 3: Rodar**

Run: `$PY -m pytest tests/test_e2e.py`
Expected: `1 passed`. Se só o golden divergir por formatação, rode `UPDATE_GOLDEN=1 $PY -m pytest tests/test_e2e.py`, **revise o diff** com `git diff tests/golden` (deve conter exatamente os campos do Step 1) e rode de novo sem a variável.

- [ ] **Step 4: Commit**

```bash
git add tests/test_e2e.py tests/golden
git commit -m "test(e2e): cover onboarding flow and golden explain output"
```

---

### Task 18: Export de JSON Schemas e paridade

**Files:**
- Create: `src/theforge/contracts/schema.py`, `schemas/*.schema.json` (gerados)
- Test: `tests/test_schemas.py`

- [ ] **Step 1: Teste falhando** — `tests/test_schemas.py`

```python
import json
from pathlib import Path

from jsonschema import Draft202012Validator

from theforge.contracts import ExecutionResult, ForgeManifest, TaskSpec, to_dict
from theforge.contracts.canonical import utc_now
from theforge.contracts.schema import EXPORTED, json_schema
from theforge.meta import PRODUCER
from theforge.providers.echo.provider import MANIFEST

SCHEMAS_DIR = Path(__file__).parents[1] / "schemas"


def test_committed_schemas_match_contracts() -> None:
    for cls in EXPORTED:
        path = SCHEMAS_DIR / f"{cls.__name__}.schema.json"
        committed = json.loads(path.read_text(encoding="utf-8"))
        assert committed == json_schema(cls), (
            f"{path.name} is stale; run python -m theforge.contracts.schema schemas")


def test_no_extra_schema_files() -> None:
    names = {p.name for p in SCHEMAS_DIR.glob("*.schema.json")}
    assert names == {f"{cls.__name__}.schema.json" for cls in EXPORTED}


def test_real_instances_validate() -> None:
    Draft202012Validator(json_schema(ForgeManifest)).validate(to_dict(MANIFEST))
    task = TaskSpec(producer=PRODUCER, created_at=utc_now(), id="t", intent="x",
                    workspace_root="/ws")
    Draft202012Validator(json_schema(TaskSpec)).validate(to_dict(task))
    result = ExecutionResult(producer=PRODUCER, created_at=utc_now(), status="ok")
    Draft202012Validator(json_schema(ExecutionResult)).validate(to_dict(result))


def test_schema_rejects_what_contracts_reject() -> None:
    data = to_dict(MANIFEST)
    data["capabilities"][0]["state"] = "maybe"
    data["capabilities"][1]["id"] = "Bad Id"
    errors = list(Draft202012Validator(json_schema(ForgeManifest)).iter_errors(data))
    assert len(errors) == 2
```

- [ ] **Step 2: Ver falhar**

Run: `$PY -m pytest tests/test_schemas.py`
Expected: FAIL `ModuleNotFoundError: No module named 'theforge.contracts.schema'`

- [ ] **Step 3: `src/theforge/contracts/schema.py`**

```python
"""Generate JSON Schema (draft 2020-12) from contract dataclasses.

Usage: python -m theforge.contracts.schema schemas
"""

import json
import sys
import types
from dataclasses import MISSING, fields, is_dataclass
from pathlib import Path
from typing import Any, Literal, Union, cast, get_args, get_origin, get_type_hints

from theforge.contracts import (
    ContextPack,
    Evidence,
    ExecuteRequest,
    ExecutionReceipt,
    ExecutionResult,
    ForgeManifest,
    HealthReport,
    Request,
    Response,
    RoutingDecision,
    TaskSpec,
)

EXPORTED: tuple[type[Any], ...] = (
    ForgeManifest, TaskSpec, RoutingDecision, ContextPack, ExecutionResult, Evidence,
    ExecutionReceipt, Request, Response, HealthReport, ExecuteRequest,
)
DIALECT = "https://json-schema.org/draft/2020-12/schema"


def json_schema(cls: type[Any]) -> dict[str, Any]:
    return {"$schema": DIALECT, "title": cls.__name__, **_object(cls)}


def _object(cls: type[Any]) -> dict[str, Any]:
    hints = get_type_hints(cls)
    properties: dict[str, Any] = {}
    required: list[str] = []
    for f in fields(cast(Any, cls)):
        schema = _type(hints[f.name])
        if "pattern" in f.metadata:
            schema = {**schema, "pattern": f.metadata["pattern"]}
        properties[f.name] = schema
        if f.default is MISSING and f.default_factory is MISSING:
            required.append(f.name)
    return {"type": "object", "properties": properties, "required": required}


def _type(tp: Any) -> dict[str, Any]:
    if tp is Any:
        return {}
    origin = get_origin(tp)
    args = get_args(tp)
    if origin in (Union, types.UnionType):
        return {"anyOf": [_type(a) for a in args]}
    if origin is Literal:
        return {"enum": list(args)}
    if origin is list:
        return {"type": "array", "items": _type(args[0])}
    if origin is dict:
        return {"type": "object", "additionalProperties": _type(args[1])}
    if isinstance(tp, type) and is_dataclass(tp):
        return _object(tp)
    scalars: dict[Any, str] = {str: "string", int: "integer", float: "number",
                               bool: "boolean", type(None): "null"}
    if tp in scalars:
        return {"type": scalars[tp]}
    raise TypeError(f"unsupported annotation {tp!r}")


def export(directory: Path) -> list[Path]:
    directory.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for cls in EXPORTED:
        path = directory / f"{cls.__name__}.schema.json"
        path.write_text(json.dumps(json_schema(cls), indent=2, sort_keys=True) + "\n",
                        encoding="utf-8", newline="\n")
        written.append(path)
    return written


if __name__ == "__main__":
    for written_path in export(Path(sys.argv[1] if len(sys.argv) > 1 else "schemas")):
        print(written_path)
```

- [ ] **Step 4: Gerar schemas**

Run: `$PY -m theforge.contracts.schema schemas`
Expected: 11 linhas `schemas/<Name>.schema.json`

- [ ] **Step 5: Ver passar**

Run: `$PY -m pytest tests/test_schemas.py`
Expected: `4 passed`

- [ ] **Step 6: Commit**

```bash
git add src/theforge/contracts/schema.py schemas tests/test_schemas.py
git commit -m "feat(contracts): publish JSON Schemas with dataclass parity tests"
```

---
### Task 19: Documentação, ADRs e CLAUDE.md

**Files:**
- Modify: `README.md`
- Create: `CLAUDE.md`, `docs/architecture.md`, `docs/protocol.md`, `docs/provider-authoring.md`, `docs/security.md`, `docs/cli.md`, `docs/adr/0001-exec-protocol.md` … `docs/adr/0008-cli-name.md`

- [ ] **Step 1: Substituir `README.md`**

~~~~markdown
# The Forge

> Uma entrada. Vários especialistas. Apenas o contexto necessário. Resultado verificável.

The Forge é um control plane local-first. Ele descobre Forges especialistas (Spark Forge, API Forge, …), escolhe o provider certo por capability de forma determinística e explicável e registra cada execução com evidência e receipt verificáveis. **The Forger** é o orquestrador interno.

**Status:** ciclo 1 (protocolo + core local). Os adapters reais de Spark Forge e API Forge chegam no ciclo 2. Hoje o core é provado com o provider nativo `echo-forge` e com providers de teste.

## Instalação (desenvolvimento)

```bash
git clone <repo> the-forger && cd the-forger
python3.11 -m venv .venv                      # qualquer Python >= 3.11
.venv/bin/python -m pip install -e ".[dev]"   # Windows: .venv\Scripts\python
```

O runtime só usa a stdlib. Os comandos são `theforge` e o alias `forge`. Use `theforge` se `forge` colidir com Foundry ou Laravel Forge no seu PATH.

## Primeiros passos

```bash
theforge doctor
theforge init
theforge capabilities list
theforge ask "eco olá" --capability demo.echo
theforge explain <run_id>
```

## Registrar um provider

Em `.forge/config/providers.toml`:

```toml
[[providers]]
id = "my-forge"
argv = ["my-forge-cli", "protocol"]   # "{python}" vira o interpretador atual
trust = "local"                        # trusted | local | unverified | blocked (padrão: unverified)
```

Depois rode `theforge registry refresh`. Providers `unverified` só entram no routing com `--allow-unverified`.

## Exit codes de `ask`

| Código | Significado |
|---|---|
| 0 | ok / partial |
| 2 | uso inválido ou workspace não inicializado |
| 3 | no_route / ambiguous |
| 4 | provider_failure / refused |
| 5 | falha ao persistir o run |

## Documentação

- [Arquitetura](docs/architecture.md)
- [Forge Protocol v1](docs/protocol.md)
- [Escrevendo um provider](docs/provider-authoring.md)
- [Segurança](docs/security.md)
- [CLI](docs/cli.md)
- [ADRs](docs/adr/)
- [Spec do ciclo 1](docs/superpowers/specs/2026-10-02-the-forge-protocol-core-design.md)

## Desenvolvimento

```bash
.venv/bin/python -m pytest            # suite offline
.venv/bin/python -m pytest -m slow    # gate de instalação limpa (baixa hatchling)
.venv/bin/ruff check .
.venv/bin/mypy
.venv/bin/python -m theforge.contracts.schema schemas   # regenerar schemas
```
~~~~

- [ ] **Step 2: Criar `CLAUDE.md`** (curto, só invariantes)

~~~~markdown
# The Forge — guia para agentes

The Forge = control plane (WHO/WHEN/HOW). Forges especialistas = WHAT. Nunca coloque conhecimento de domínio (Spark, API, …) aqui: ele vem dos sinais declarados pelos providers.

## Invariantes
- Runtime stdlib-only (Python >= 3.11). Dependências só em `[dev]`.
- Integração com providers só via Forge Protocol (subprocess + JSON). Nunca `import sparkforge`/`apiforge`.
- Routing determinístico. Ambiguidade vira `ambiguous`, nunca um chute. Sem LLM no core.
- Nenhum caminho reporta sucesso sem um `ExecutionResult` válido.
- Tudo que é persistido passa por `security.redact`. Credenciais nunca chegam ao env dos providers.
- Contratos: `schema = "theforge/<Name>/v1"`. Mudança de contrato exige regenerar `schemas/` (`python -m theforge.contracts.schema schemas`).

## Comandos
- Testes: `python -m pytest` (offline); gate: `python -m pytest -m slow`
- Lint/tipos: `ruff check .` · `mypy`

## Mais contexto
`docs/architecture.md`, `docs/protocol.md`, `docs/adr/`, spec em `docs/superpowers/specs/`.
~~~~

- [ ] **Step 3: Criar `docs/architecture.md`**

~~~~markdown
# Arquitetura (ciclo 1)

```mermaid
flowchart TD
    U[usuário / host / CI] --> CLI[cli: theforge / forge]
    CLI --> F[forger: orquestrador]
    F --> R[registry: fontes, describe, cache, trust]
    F --> RT[routing: sinais determinísticos]
    F --> C[context: scan + Context Broker]
    F --> RS[runs: run store + receipts]
    R --> T[protocol: SubprocessTransport]
    F --> T
    T -->|"argv op, JSON stdin/stdout"| E[echo-forge]
    T --> S[Spark Forge adapter - ciclo 2]
    T --> A[API Forge adapter - ciclo 2]
```

## Fluxo de `ask`

```mermaid
sequenceDiagram
    participant CLI
    participant Forger
    participant Registry
    participant Provider
    CLI->>Forger: AskRequest
    Forger->>Forger: TaskSpec (persistido)
    Forger->>Registry: records()
    Forger->>Forger: route() -> RoutingDecision
    Forger->>Provider: health
    Forger->>Forger: ContextPack (persistido)
    Forger->>Provider: execute(task, capability, action, context)
    Provider-->>Forger: Response(ExecutionResult)
    Forger->>Forger: ExecutionResult + ExecutionReceipt (persistidos)
    Forger-->>CLI: AskOutcome
```

## Responsabilidades

| Módulo | Faz | Não faz |
|---|---|---|
| `contracts` | dataclasses v1, validação, JSON canônico, schemas | I/O |
| `protocol` | spawn, timeout, limite de stdout, validação do envelope | decidir rota |
| `registry` | carregar entradas, `describe`, negociar protocolo, cache, trust, health | executar tarefas |
| `routing` | ranquear capabilities por sinais declarados | conhecer domínios |
| `context` | listar arquivos com segurança, montar ContextPack por referência | ler conteúdo para o provider |
| `forger` | orquestrar um run, fallback de health, receipts | lógica de domínio |
| `runs` | persistir artefatos redigidos, hashes | interpretar resultados |
| `cli` | parsing, render, exit codes | lógica de negócio |

## Estado `.forge/`

| Dir | Classe | Git |
|---|---|---|
| `config/` | persistent | committable |
| `registry/` | cacheable | ignorado |
| `runs/<run_id>/` | persistent local | ignorado |
| `cache/` | ephemeral | ignorado |

## Fora do ciclo 1
Adapters reais (ciclo 2), LLM/semantic routing, multi-provider (parallel/pipeline/debate), economy avançada, installer, workspace graph.
~~~~

- [ ] **Step 4: Criar `docs/protocol.md`**

~~~~markdown
# Forge Protocol v1

## Invocação
`<argv do provider> <op>`. O request JSON entra pelo stdin e a response JSON sai pelo stdout, um documento cada.

- Exit 0 sempre que houver uma response de protocolo válida, inclusive `refused`.
- Exit ≠ 0, stdout que não é JSON, stdout acima de 8 MB ou timeout são falhas de transporte (`provider_failure`).

## Ops
| Op | Obrigatória | Payload do request | Payload da response |
|---|---|---|---|
| `describe` | sim | `{}` | `ForgeManifest` |
| `health` | sim | `{}` | `HealthReport` (`ok\|degraded\|unavailable`) |
| `execute` | não | `ExecuteRequest{task, capability, action, context}` | `ExecutionResult` |
| `plan`, `verify`, `estimate` | reservadas | — | — |

O provider declara as ops que suporta em `describe.ops`.

## Envelopes
```json
{"protocol":"forge/v1","kind":"Request","op":"execute","request_id":"r_…","payload":{}}
```
```json
{"protocol":"forge/v1","kind":"Response","request_id":"r_…",
 "producer":{"id":"my-forge","version":"1.0.0"},
 "status":"ok|partial|refused|error","payload":{},
 "error":{"code":"…","detail":"…","field":null,"unlock":null},
 "limitations":[],"unknowns":[]}
```
- `request_id` precisa ecoar o do request.
- `error` é obrigatório quando o status é `refused` ou `error`.

## Versionamento
- `describe.protocols` lista os majors suportados; o core escolhe o maior em comum.
- Sem major em comum, o provider fica `incompatible` e sai do routing.
- Campos desconhecidos são ignorados (forward-compat dentro do major). Breaking change exige um novo major.
- Para qualquer op que não seja `describe`, o provider deve recusar requests com protocolo que não suporta.

## Códigos de erro do core
| Código | Causa |
|---|---|
| `FORGE-PROTO-SPAWN` | executável não encontrado ou sem permissão |
| `FORGE-PROTO-TIMEOUT` | sem resposta no tempo limite |
| `FORGE-PROTO-EXIT` | exit ≠ 0 (stderr redigido no detalhe) |
| `FORGE-PROTO-NOT-JSON` | stdout não é JSON |
| `FORGE-PROTO-OVERSIZE` | stdout > 8 MB |
| `FORGE-PROTO-SCHEMA` | envelope ou payload inválido |
| `FORGE-PROTO-MISMATCH` | `request_id` divergente |
| `FORGE-PROTO-VERSION` | protocolo da response ≠ negociado |
| `FORGE-PROVIDER-NOT-READY` | provider não está `ready` no registry |
| `FORGE-HEALTH-UNAVAILABLE` | health reporta `unavailable` |
| `FORGE-HEALTH-FAILED` | health respondeu com status ≠ ok |

## Contratos
Os JSON Schemas ficam em `schemas/`. Nomes reservados (sem implementação): ExecutionPlan, VerificationResult, Budget, RiskAssessment, GraphNode, GraphEdge, InstallationPlan, DecisionRecord, WorkspaceDescriptor, EnvironmentReport (v0 não estável em `doctor`).
~~~~

- [ ] **Step 5: Criar `docs/provider-authoring.md`**

~~~~markdown
# Escrevendo um provider

Um provider é qualquer executável que implementa o [Forge Protocol v1](protocol.md). A linguagem é livre.

## Mínimo
1. Ler `argv[-1]` como op e o request JSON do stdin.
2. `describe`: responder com o `ForgeManifest` (`id` igual ao id registrado; `ops` contendo `describe` e `health`).
3. `health`: responder `{"status":"ok","checks":[]}`.
4. `execute`: ler `payload.capability`, `payload.action` e `payload.context.files` (paths relativos a `payload.task.workspace_root`) e responder com um `ExecutionResult`.
5. Capability desconhecida → `status: "refused"` com `error.code` e, se fizer sentido, `unlock`.
6. Sempre exit 0 com uma response válida. Crash vira `provider_failure` no core.

Exemplo completo e standalone: `tests/fixtures/providers/fixture_forge.py`.

## Capabilities e sinais
- Formato do id: `domínio.assunto` (`^[a-z][a-z0-9-]*(\.[a-z][a-z0-9-]*)+$`).
- Os sinais (`keywords`, `file_globs`, `dependencies`) são a única fonte de conhecimento do router. Declare sinais específicos: o routing exige ≥ 2 tipos de sinal casados para ter confiança `high`.
- `operation_class` declara o efeito colateral: `read_only` … `destructive`.

## Regras de segurança
- Leia apenas os arquivos listados no ContextPack e confira se continuam dentro de `workspace_root`.
- Não espere credenciais no ambiente: o core repassa só uma allowlist de variáveis.
- O cwd é um diretório de trabalho do run (`.forge/runs/<id>/work`). Efeitos colaterais devem ficar ali.

## Certificação
Adicione o argv do provider em `PROVIDER_ARGVS` de `tests/test_conformance.py` e rode `python -m pytest tests/test_conformance.py`.
~~~~

- [ ] **Step 6: Criar `docs/security.md`**

~~~~markdown
# Segurança — threat model resumido (ciclo 1)

| Ameaça | Mitigação no ciclo 1 | Pendente |
|---|---|---|
| Provider malicioso ou desconhecido | trust (`unverified` fora do routing por padrão, `blocked` nunca executa); subprocess isolado; env por allowlist | sandbox de SO, assinatura |
| Manifest adulterado | id do manifest precisa bater com a entrada; cache com sha256 verificado na leitura | assinatura de manifest |
| Injeção de shell | `argv` em lista, `shell=False` | — |
| Path traversal / symlink | `resolve_inside` no scan e no echo-forge; `..` e symlinks para fora viram `excluded` | — |
| Leitura de secrets do workspace | `.env*`, `*.pem`, `*.key`, `id_rsa*`, `credentials*` excluídos do ContextPack | detecção por conteúdo |
| Vazamento de credencial em artefatos | redaction de padrões e chaves sensíveis antes de persistir; stderr do provider redigido | — |
| Exaustão de recursos | timeout por op; stdout limitado a 8 MB; stderr a 64 KB | limite de CPU/memória |
| Prompt injection via workspace | core não usa LLM no ciclo 1 | relevante no ciclo com LLM |
| Supply chain do core | zero dependências de runtime; build reprodutível via hatchling | lockfile do dev, assinatura |
| Mutação inesperada | `operation_class` declarado; cwd isolado por run | policy allow/ask/deny (ciclo futuro) |
~~~~

- [ ] **Step 7: Criar `docs/cli.md`**

~~~~markdown
# CLI

`theforge` (alias `forge`). Toda subcomando aceita `--root <dir>` (padrão: diretório atual) e `--json`.

| Comando | Faz | Exit |
|---|---|---|
| `init` | cria `.forge/` (idempotente) | 0 |
| `doctor` | OS, Python, git, host, workspace, providers | 0 / 1 se algo `fail` |
| `status` | resumo do workspace | 0 |
| `registry list` | providers (usa cache) | 0 |
| `registry refresh` | re-`describe` de todos os providers | 0 |
| `registry show <id>` | manifest, argv e hash | 0 / 2 se desconhecido |
| `capabilities list [--provider id]` | capabilities declaradas | 0 |
| `capabilities search <q>` | busca em id, descrição e keywords | 0 |
| `providers health` | health de cada provider | 0 / 1 |
| `ask "<texto>" [--capability id] [--action a] [--profile economy\|balanced\|max] [--target path]... [--allow-unverified]` | roteia e executa | 0 / 2 / 3 / 4 / 5 |
| `explain <run_id>` | reconstrói a decisão e o resultado de um run | 0 / 2 |
~~~~

- [ ] **Step 8: Criar os 8 ADRs em `docs/adr/`**

`docs/adr/0001-exec-protocol.md`:

~~~~markdown
# ADR 0001 — Exec-protocol via subprocess em vez de imports ou MCP

- Status: aceito (2026-10-02)

## Contexto
Spark Forge exige Python >=3.10; API Forge exige ==3.12 e tem dependências pesadas. As duas CLIs já emitem JSON. Os dois têm módulos internos enormes, que tornam tentador importar internals.

## Decisão
Providers são executáveis chamados como `<argv> <op>`, com JSON pelo stdin e stdout.

## Alternativas
- **Imports in-process:** acoplamento e conflito de versões de Python.
- **MCP:** exige dependência, é assíncrono, acoplado a host e contraria o core offline.

## Consequências
Isolamento de ambientes e neutralidade de linguagem, com custo de ~100–300 ms de processo por op. Adapters do ciclo 2 traduzem as CLIs existentes.
~~~~

`docs/adr/0002-json-single-schema-convention.md`:

~~~~markdown
# ADR 0002 — JSON e uma única convenção de schema

- Status: aceito (2026-10-02)

## Contexto
O API Forge mistura três convenções de versão (`version` int, `apiforge/*/v1`, `af-*/1`).

## Decisão
Todo contrato persistido usa `schema: "theforge/<Name>/v1"` e hash sha256 sobre JSON canônico (chaves ordenadas, separadores compactos, UTF-8). `schemas/*.json` é o artefato publicado; as dataclasses são a implementação, com paridade testada.

## Consequências
Um único parser genérico (`from_dict`). Campos desconhecidos são ignorados, o que dá forward-compat dentro do major.
~~~~

`docs/adr/0003-python-stdlib-only.md`:

~~~~markdown
# ADR 0003 — Python >= 3.11, stdlib-only em runtime

- Status: aceito (2026-10-02)

## Decisão
O core usa argparse, dataclasses, tomllib e subprocess. pydantic, typer e rich ficam de fora.

## Motivo
Startup rápido, instalação offline, superfície de supply chain mínima. 3.11 traz `tomllib` e `datetime.UTC`.

## Consequências
A validação é escrita à mão (`contracts.base`). Um teste garante a lista vazia de dependências.
~~~~

`docs/adr/0004-no-forge-kernel-yet.md`:

~~~~markdown
# ADR 0004 — Sem forge-kernel por enquanto

- Status: aceito (2026-10-02)

## Contexto
A auditoria encontrou conceitos convergentes (receipts, context, budget, workspace manifest) com schemas divergentes.

## Decisão
Nenhum pacote compartilhado entre os três projetos. O ponto de integração é o protocolo.

## Reavaliar quando
A mesma abstração estiver provada em ≥ 2 providers via protocolo e a duplicação gerar defeito real.
~~~~

`docs/adr/0005-deterministic-routing-first.md`:

~~~~markdown
# ADR 0005 — Routing determinístico primeiro, sem LLM no ciclo 1

- Status: aceito (2026-10-02)

## Decisão
Ranking lexicográfico por (tipos de sinal casados, deps, globs, keywords), usando sinais declarados pelos providers. Confiança `high` exige vencedor único e ≥ 2 tipos de sinal. Fora disso o resultado é `ambiguous`, com candidatos e a dica `--capability`.

## Motivo
Barato, reprodutível, explicável. Não existe peso inventado.

## Consequências
Pedidos vagos exigem `--capability`. O LLM entra num ciclo futuro, só para resolver ambiguidade.
~~~~

`docs/adr/0006-local-registry-and-trust.md`:

~~~~markdown
# ADR 0006 — Registry local e trust model

- Status: aceito (2026-10-02)

## Decisão
Fontes em precedência crescente: builtin → usuário → projeto. Trust: `builtin|trusted|local|unverified|blocked`. O padrão é `unverified`, que fica fora do routing sem opt-in. `blocked` nunca é executado. `builtin` é reservado. O cache guarda só manifests `ready`, verificados por sha256.

## Consequências
Código de terceiros nunca é tratado como confiável em silêncio.
~~~~

`docs/adr/0007-context-pack-by-reference.md`:

~~~~markdown
# ADR 0007 — ContextPack por referência

- Status: aceito (2026-10-02)

## Decisão
O ContextPack lista paths, sha256, bytes e o motivo da seleção, sem conteúdo. O provider lê só os paths permitidos. Há budget por perfil (64 KB / 256 KB / 1 MB) e exclusões registradas.

## Motivo
Economia de contexto, verificabilidade (o hash prova o que foi entregue) e nenhum conteúdo de workspace persistido nos runs.
~~~~

`docs/adr/0008-cli-name.md`:

~~~~markdown
# ADR 0008 — Nome `theforge` com alias `forge`

- Status: aceito (2026-10-02)

## Contexto
`forge` colide com Foundry (Ethereum) e com Laravel Forge CLI.

## Decisão
O pacote e o import se chamam `theforge`. Há dois console scripts: `theforge` e o alias `forge`. A documentação mostra `theforge`.
~~~~

- [ ] **Step 9: Commit**

```bash
git add README.md CLAUDE.md docs/architecture.md docs/protocol.md docs/provider-authoring.md docs/security.md docs/cli.md docs/adr
git commit -m "docs: add architecture, protocol, provider authoring, security, CLI and ADRs"
```

---

### Task 20: Quality gates

**Files:**
- Test: `tests/test_packaging.py`

- [ ] **Step 1: Criar `tests/test_packaging.py`**

```python
import json
import os
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

REPO = Path(__file__).parents[1]


def test_zero_runtime_dependencies() -> None:
    data = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    assert data["project"].get("dependencies", []) == []


@pytest.mark.slow
def test_fresh_install(tmp_path: Path) -> None:
    venv = tmp_path / "venv"
    subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True)
    bin_dir = venv / ("Scripts" if os.name == "nt" else "bin")
    python = bin_dir / ("python.exe" if os.name == "nt" else "python")
    subprocess.run([str(python), "-m", "pip", "install", "--quiet", str(REPO)], check=True)
    suffix = ".exe" if os.name == "nt" else ""
    assert (bin_dir / f"forge{suffix}").exists()
    workspace = tmp_path / "ws"
    workspace.mkdir()
    out = subprocess.run([str(bin_dir / f"theforge{suffix}"), "doctor", "--json",
                          "--root", str(workspace)], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    checks = {c["name"]: c for c in json.loads(out.stdout)["checks"]}
    assert checks["provider:echo-forge"]["status"] == "ok"
```

- [ ] **Step 2: Lint**

Run: `$PY -m ruff check . --fix && $PY -m ruff check .`
Expected: `All checks passed!` Se sobrar E501, quebre a linha sem mudar comportamento.

- [ ] **Step 3: Tipos**

Run: `$PY -m mypy`
Expected: `Success: no issues found`. Se o mypy reclamar de `# type: ignore` não usado em `routing/router.py`, remova o comentário.

- [ ] **Step 4: Suite offline completa**

Run: `$PY -m pytest`
Expected: tudo verde (skips só de symlink).

- [ ] **Step 5: Paridade de schemas**

Run: `$PY -m theforge.contracts.schema schemas && git status --porcelain schemas`
Expected: sem saída do `git status`, ou seja, os schemas estão em dia.

- [ ] **Step 6: Gate de instalação limpa**

Run: `$PY -m pytest -m slow`
Expected: `1 passed` (usa rede para baixar hatchling no venv temporário).

- [ ] **Step 7: Commit**

```bash
git add tests/test_packaging.py
git add -u
git commit -m "test(gates): add zero-dependency and fresh-install gates; fix lint and typing"
```

- [ ] **Step 8: Relatório do ciclo** (§88)

Reporte ao usuário: Implemented, Tests (contagem do pytest), Evidence (comandos e saídas dos Steps 2–6), Known limitations (adapters reais ausentes, sem LLM, sem sandbox de SO), Technical debt, Next phase (ciclo 2: adapters Spark/API reutilizando a conformance suite).

---

## Cobertura do spec

| Spec | Task |
|---|---|
| §5 protocolo, envelopes, versionamento, segurança do transporte | 4, 6, 7 |
| §6 contratos + regras (cabeçalho, hash, redaction, schemas) | 2, 3, 4, 5, 13, 18 |
| §7.1 registry e trust | 8, 9 |
| §7.2 Context Broker | 10, 12 |
| §7.3 `.forge/` | 13 |
| §7.4 CLI | 16 |
| §8 fluxo e routing | 11, 14 |
| §9 erros e exit codes | 6, 14, 16 |
| §10 testes (unit, conformance, failure, fixtures, e2e, golden, offline, property) | 1–18 |
| §11 quality gates | 20 |
| §12 ADRs, §13 docs | 19 |
| §14 critérios de aceite 1–8 | 20 (1), 16–17 (2–4), 14 (5), 7 (6), 1+20 (7), 14 (8) |
