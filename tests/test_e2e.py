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
