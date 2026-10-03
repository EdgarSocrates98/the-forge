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


def test_run_id_rejects_trailing_newline(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="invalid run id"):
        RunStore(tmp_path).run_dir(new_run_id() + "\n")


def test_read_optional_validates_artifact_name(tmp_path: Path) -> None:
    store = RunStore(tmp_path)
    run_id = new_run_id()
    store.create(run_id)
    with pytest.raises(ValueError, match="unknown run artifact"):
        store.read_optional(run_id, "../../x")


def test_read_optional_corrupt_json_is_persistence_error(tmp_path: Path) -> None:
    store = RunStore(tmp_path)
    run_id = new_run_id()
    store.create(run_id)
    (store.run_dir(run_id) / "task.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(PersistenceError, match="cannot read"):
        store.read_optional(run_id, "task")


def test_read_optional_non_dict_is_persistence_error(tmp_path: Path) -> None:
    store = RunStore(tmp_path)
    run_id = new_run_id()
    store.create(run_id)
    (store.run_dir(run_id) / "task.json").write_text("[1, 2]", encoding="utf-8")
    with pytest.raises(PersistenceError, match="cannot read"):
        store.read_optional(run_id, "task")


def test_persistence_error(tmp_path: Path) -> None:
    not_a_dir = tmp_path / "forge-file"
    not_a_dir.write_text("x")
    with pytest.raises(PersistenceError):
        RunStore(not_a_dir).create(new_run_id())


def test_init_workspace(tmp_path: Path) -> None:
    created = init_workspace(tmp_path)
    assert ".forge/config/providers.toml" in created
    assert ".forge/.gitignore" in created
    assert ".forge/registry" not in created
    assert "!config/" in (tmp_path / ".forge" / ".gitignore").read_text(encoding="utf-8")
    assert init_workspace(tmp_path) == []
    assert find_forge_dir(tmp_path) == tmp_path / ".forge"
    other = tmp_path / "other"
    other.mkdir()
    assert find_forge_dir(other) is None
    with pytest.raises(UsageError, match="theforge init"):
        require_forge_dir(other)
