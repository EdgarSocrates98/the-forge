"""Validate cross-Forge contracts without importing any Forge runtime."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


SPECIALISTS = {
    "the-forge",
    "spark-forge-aws",
    "spark-forge-azure",
    "api-forge",
    "platform-forge",
    "forge-doctor-api",
    "forge-doctor-data",
}

SAFE_REF = re.compile(r"^[A-Za-z0-9_./-]+$")


def validate_ref(ref: str) -> str:
    if not SAFE_REF.fullmatch(ref) or ref.startswith("-"):
        raise ValueError("ref must be a simple Git ref without options")
    return ref


def show(repo: Path, ref: str, path: str) -> str | None:
    result = subprocess.run(
        ("git", "show", f"{ref}:{path}"),
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return result.stdout if result.returncode == 0 else None


def tree(repo: Path, ref: str) -> list[str]:
    result = subprocess.run(
        ("git", "ls-tree", "-r", "--name-only", ref),
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return result.stdout.splitlines()


def json_file(repo: Path, ref: str, path: str) -> dict[str, Any] | None:
    raw = show(repo, ref, path)
    if raw is None:
        return None
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {"__parse_error__": True}
    return value if isinstance(value, dict) else {"__invalid_shape__": True}


def project_scripts(pyproject: str | None) -> set[str]:
    if not pyproject:
        return set()
    block = pyproject.split("[project.scripts]", 1)
    if len(block) != 2:
        return set()
    block = block[1].split("[", 1)[0]
    return set(re.findall(r'^([\w.-]+)\s*=', block, re.MULTILINE))


def check(name: str, condition: bool, detail: str, evidence: str) -> dict[str, str]:
    return {
        "id": name,
        "status": "PASS" if condition else "FAIL",
        "detail": detail,
        "evidence": evidence,
    }


def validate(repo_name: str, repo: Path, ref: str) -> list[dict[str, str]]:
    paths = set(tree(repo, ref))
    forge = json_file(repo, ref, "forge.json")
    agentic = json_file(repo, ref, "forge.agentic.json")
    package = json_file(repo, ref, "package.json")
    pyproject = show(repo, ref, "pyproject.toml")
    checks: list[dict[str, str]] = []
    has_install = any(Path(path).name.lower() in {"install.sh", "install.ps1"} for path in paths)
    checks.append(
        check(
            "installers",
            has_install or repo_name in {"forge-cli", "forge-portal"},
            "official installer exists or project is an optional host/UI without one",
            "git tree",
        )
    )

    if repo_name in SPECIALISTS:
        checks.append(check("forge_manifest", forge is not None and "forge_id" in forge, "Forge manifest has forge_id", "forge.json"))
        if forge and "forge_id" in forge:
            checks.append(check("forge_id_unique_shape", forge["forge_id"] == repo_name, "forge_id matches repository identity", "forge.json:forge_id"))
            cli = forge.get("cli")
            scripts = project_scripts(pyproject)
            if package:
                scripts |= set((package.get("bin") or {}).keys())
            checks.append(check("cli_entrypoint", bool(cli), "CLI name declared", "forge.json:cli"))
            checks.append(check("cli_script_declared", not cli or cli in scripts or repo_name == "the-forge", "CLI is represented by a native entrypoint", "forge.json + pyproject/package.json"))

        if repo_name != "the-forge":
            checks.append(check("agentic_manifest", agentic is not None and agentic.get("schema") == "forge/SpecialistAgenticManifest/v1", "agentic manifest uses versioned schema", "forge.agentic.json"))
            if agentic:
                checks.append(check("provider_identity", agentic.get("provider") == repo_name, "provider matches Forge identity", "forge.agentic.json:provider"))
                checks.append(check("readonly_default", agentic.get("read_only_default") is True, "read_only_default is true", "forge.agentic.json:read_only_default"))
                checks.append(check("no_credentials_default", agentic.get("requires_credentials") is False, "fixture workflows do not require credentials", "forge.agentic.json:requires_credentials"))
                workflows = agentic.get("workflows") or []
                checks.append(check("workflow_contract", bool(workflows) and all(isinstance(item, dict) and item.get("id") and item.get("command") for item in workflows), "workflows have id and command", "forge.agentic.json:workflows"))

    if repo_name in {"spark-forge-aws", "spark-forge-azure", "api-forge", "platform-forge", "forge-doctor-api", "forge-doctor-data"}:
        cli = (forge or {}).get("cli")
        mcp = (forge or {}).get("mcp_command")
        checks.append(check("mcp_declared", bool(mcp), "MCP command is declared when supported", "forge.json:mcp_command"))
        if mcp and cli:
            scripts = project_scripts(pyproject)
            if package:
                scripts |= set((package.get("bin") or {}).keys())
            checks.append(
                check(
                    "mcp_cli_consistent",
                    mcp[0] in scripts or mcp[0] in {cli, "python", "-m"},
                    "MCP command uses native Forge surface",
                    "forge.json:mcp_command + native entrypoints",
                )
            )

    forbidden: list[str] = []
    if repo_name != "forge-portal":
        imported = ["forge_cli", "forge_portal"]
        if repo_name != "the-forge":
            imported.append("theforge")
        pattern = "|".join(imported)
        grep = subprocess.run(
            (
                "git",
                "grep",
                "-I",
                "-n",
                "-E",
                rf"^[[:space:]]*(from|import)[[:space:]]+({pattern})([.]|[[:space:]]|$)",
                ref,
                "--",
                "src",
                "scripts",
            ),
            cwd=repo,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        forbidden = grep.stdout.splitlines() if grep.returncode in {0, 1} else ["git grep failed"]
    checks.append(check("runtime_independence", not forbidden, "runtime source has no explicit convenience-project dependency", ", ".join(forbidden) or "source scan"))

    return checks


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace-root", type=Path, required=True)
    parser.add_argument("--ref", default="origin/main")
    parser.add_argument("--output", type=Path, default=Path("audit/reports/contract-validation.json"))
    args = parser.parse_args()
    validate_ref(args.ref)
    workspace = args.workspace_root.resolve()
    records: dict[str, Any] = {}
    for name in (
        "the-forge",
        "spark-forge-aws",
        "spark-forge-azure",
        "api-forge",
        "platform-forge",
        "forge-doctor-api",
        "forge-doctor-data",
        "forge-cli",
        "forge-portal",
    ):
        repo = workspace / name
        checks = validate(name, repo, args.ref)
        records[name] = {
            "sha": subprocess.run(("git", "rev-parse", args.ref), cwd=repo, capture_output=True, text=True, check=False).stdout.strip(),
            "status": "PASS" if all(item["status"] == "PASS" for item in checks) else "FAIL",
            "checks": checks,
        }
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    document = {
        "schema_version": "1.0",
        "generated_at": datetime.now(UTC).isoformat(),
        "ref": args.ref,
        "status": "PASS" if all(item["status"] == "PASS" for item in records.values()) else "FAIL",
        "repositories": records,
        "provenance": "git show REF:FILE + git ls-tree + git rev-parse",
    }
    output.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": document["status"], "output": str(output)}))
    return 0 if document["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
