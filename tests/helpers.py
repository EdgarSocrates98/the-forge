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
