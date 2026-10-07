"""CLI proof for governed adaptive experiments (Cycle 4.1)."""

import json
from pathlib import Path

from theforge.cli.main import main
from theforge.contracts import ExecutionObservation, StrategyExperiment, to_dict
from theforge.meta import PRODUCER
from theforge.observations import record_observation


def _obs(run: str, provider: str, surface: str, created_at: str) -> ExecutionObservation:
    return ExecutionObservation(
        producer=PRODUCER,
        created_at=created_at,
        run_id=run,
        provider=provider,
        capability="data.performance",
        task_family="data.spark.performance",
        surface_fingerprint=surface,
        status="ok",
        verification="passed",
    )


def test_economy_experiment_is_read_only_and_never_promotes(
    tmp_path: Path, capsys
) -> None:
    forge = tmp_path / ".forge"
    forge.mkdir()
    for item in (
        _obs("r1", "spark-a", "sa", "2026-10-07T13:00:00Z"),
        _obs("r2", "spark-b", "sb", "2026-10-07T13:01:00Z"),
        _obs("r3", "spark-a", "sa", "2026-10-07T13:02:00Z"),
        _obs("r4", "spark-b", "sb", "2026-10-07T13:03:00Z"),
    ):
        assert record_observation(tmp_path, item) is None

    experiment = StrategyExperiment(
        producer=PRODUCER,
        created_at="2026-10-07T12:00:00Z",
        experiment_id="exp-cli",
        capability="data.performance",
        task_family="data.spark.performance",
        champion="spark-a",
        challenger="spark-b",
        champion_surface="sa",
        challenger_surface="sb",
        minimum_runs=4,
        minimum_verified_runs=4,
    )
    spec = tmp_path / "experiment.json"
    spec.write_text(json.dumps(to_dict(experiment)), encoding="utf-8")

    before = (forge / "metrics" / "observations.jsonl").read_bytes()
    code = main([
        "economy",
        "experiment",
        "--spec",
        str(spec),
        "--root",
        str(tmp_path),
        "--json",
    ])
    out = json.loads(capsys.readouterr().out)
    after = (forge / "metrics" / "observations.jsonl").read_bytes()

    assert code == 0
    assert out["state"] == "eligible_for_review"
    assert out["operator_approval_required"] is True
    assert out["state"] != "promoted"
    assert before == after


def test_economy_experiment_rejects_unknown_contract_fields(
    tmp_path: Path, capsys
) -> None:
    (tmp_path / ".forge").mkdir()
    spec = tmp_path / "bad.json"
    spec.write_text(json.dumps({
        "producer": {"id": "theforge", "version": "0.2.1"},
        "created_at": "t",
        "experiment_id": "e",
        "capability": "data.performance",
        "task_family": None,
        "champion": "a",
        "challenger": "b",
        "champion_surface": "sa",
        "challenger_surface": "sb",
        "surprise": "instruction-like extension",
    }), encoding="utf-8")

    code = main([
        "economy",
        "experiment",
        "--spec",
        str(spec),
        "--root",
        str(tmp_path),
        "--json",
    ])
    captured = capsys.readouterr()
    assert code == 2
    assert "invalid strategy experiment" in captured.err
