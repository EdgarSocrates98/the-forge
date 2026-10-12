"""Collect a reproducible, read-only baseline for the nine Forge repositories."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


REPOSITORIES = {
    "the-forge": "EdgarSocrates98/the-forge",
    "spark-forge-aws": "EdgarSocrates98/spark-forge-aws",
    "spark-forge-azure": "EdgarSocrates98/spark-forge-azure",
    "api-forge": "EdgarSocrates98/api-forge",
    "platform-forge": "EdgarSocrates98/platform-forge",
    "forge-doctor-api": "EdgarSocrates98/forge-doctor-api",
    "forge-doctor-data": "EdgarSocrates98/forge-doctor-data",
    "forge-cli": "EdgarSocrates98/forge-cli",
    "forge-portal": "EdgarSocrates98/forge-portal",
}

SAFE_REF = re.compile(r"^[A-Za-z0-9_./-]+$")


def validate_ref(ref: str) -> str:
    if not SAFE_REF.fullmatch(ref) or ref.startswith("-"):
        raise ValueError("ref must be a simple Git ref without options")
    return ref


def run(repo: Path, *args: str) -> str:
    result = subprocess.run(
        args,
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return result.stdout.strip()


def provenance(ref: str, source: str, command: str) -> dict[str, str]:
    return {
        "ref": ref,
        "source": source,
        "command": command,
        "collected_at": datetime.now(UTC).isoformat(),
    }


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
    raw = run(repo, "git", "ls-tree", "-r", "--name-only", ref)
    return [line for line in raw.splitlines() if line]


def first_match(text: str, pattern: str) -> str | None:
    match = re.search(pattern, text, re.MULTILINE)
    return match.group(1) if match else None


def pyproject_summary(text: str) -> dict[str, Any]:
    project_name = first_match(text, r'^name\s*=\s*["\']([^"\']+)["\']')
    version = first_match(text, r'^version\s*=\s*["\']([^"\']+)["\']')
    python = first_match(text, r'^requires-python\s*=\s*["\']([^"\']+)["\']')
    scripts: dict[str, str] = {}
    in_scripts = False
    for line in text.splitlines():
        if line.strip() == "[project.scripts]":
            in_scripts = True
            continue
        if in_scripts and line.startswith("["):
            break
        if in_scripts:
            match = re.match(r'^([\w.-]+)\s*=\s*["\']([^"\']+)["\']', line)
            if match:
                scripts[match.group(1)] = match.group(2)
    return {
        "name": project_name,
        "version": version,
        "requires_python": python,
        "scripts": scripts,
    }


def package_summary(text: str) -> dict[str, Any]:
    try:
        package = json.loads(text)
    except json.JSONDecodeError:
        return {"parse_error": True}
    return {
        "name": package.get("name"),
        "version": package.get("version"),
        "engines": package.get("engines", {}),
        "package_manager": package.get("packageManager"),
        "scripts": package.get("scripts", {}),
    }


def json_summary(text: str | None) -> dict[str, Any] | None:
    if text is None:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"parse_error": True}


def dependencies(repo: Path, ref: str, paths: list[str]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    pyproject = show(repo, ref, "pyproject.toml")
    if pyproject is not None:
        section = pyproject.split("[project.optional-dependencies]", 1)[0]
        deps = re.findall(r'^\s*"?([A-Za-z0-9_.-]+)(?:\[[^]]+\])?\s*[<>=!~]', section, re.MULTILINE)
        result["python_project_dependencies"] = sorted(set(deps))
    package = show(repo, ref, "package.json")
    if package is not None:
        parsed = json_summary(package) or {}
        result["npm_dependencies"] = sorted(
            set((parsed.get("dependencies") or {}).keys())
            | set((parsed.get("devDependencies") or {}).keys())
        )
    result["internal_forge_references"] = [
        path
        for path in paths
        if any(token in path.lower() for token in ("forge", "doctor"))
        and path.lower().endswith((".json", ".toml", ".yaml", ".yml", ".md"))
    ][:200]
    return result


def collect(repo_name: str, repo: Path, ref: str) -> dict[str, Any]:
    paths = tree(repo, ref)
    pyproject = show(repo, ref, "pyproject.toml")
    package = show(repo, ref, "package.json")
    forge = show(repo, ref, "forge.json")
    agentic = show(repo, ref, "forge.agentic.json")
    mcp = show(repo, ref, ".mcp.json")
    workflows = [path for path in paths if path.startswith(".github/workflows/")]
    tests = [
        path
        for path in paths
        if path.startswith(("tests/", "test/", "e2e/", "evals/"))
        or re.search(r"(^|/)(test_[^/]+|[^/]+_test)\.(py|ts|tsx|js)$", path)
    ]
    install_files = [
        path
        for path in paths
        if Path(path).name.lower() in {"install.sh", "install.ps1", "setup.sh", "setup.ps1"}
    ]
    metadata = pyproject_summary(pyproject) if pyproject else package_summary(package or "")
    return {
        "repository": REPOSITORIES[repo_name],
        "local_path": str(repo),
        "ref": ref,
        "sha": run(repo, "git", "rev-parse", ref),
        "remote": run(repo, "git", "remote", "get-url", "origin"),
        "metadata": metadata,
        "installation": install_files,
        "entrypoints": metadata.get("scripts", {}),
        "contracts": {
            "forge_json": json_summary(forge),
            "forge_agentic_json": json_summary(agentic),
            "mcp_json": json_summary(mcp),
        },
        "tests": {"count": len(tests), "paths": tests[:300]},
        "workflows": workflows,
        "tags": run(repo, "git", "tag", "--list").splitlines(),
        "provenance": {
            "sha": provenance(ref, "git", f"git rev-parse {ref}"),
            "tree": provenance(ref, "git", f"git ls-tree -r --name-only {ref}"),
            "metadata": provenance(ref, "pyproject.toml or package.json", "git show REF:FILE"),
            "contracts": provenance(ref, "forge*.json/.mcp.json", "git show REF:FILE"),
            "tests": provenance(ref, "git tree", f"git ls-tree -r --name-only {ref}"),
            "workflows": provenance(ref, ".github/workflows", f"git ls-tree -r --name-only {ref}"),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace-root", type=Path, required=True)
    parser.add_argument("--ref", default="origin/main")
    parser.add_argument("--output", type=Path, default=Path("audit/baseline"))
    args = parser.parse_args()
    validate_ref(args.ref)
    workspace = args.workspace_root.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    collected = {
        name: collect(name, workspace / name, args.ref) for name in REPOSITORIES
    }
    generated = datetime.now(UTC).isoformat()
    envelope = {
        "schema_version": "1.0",
        "generated_at": generated,
        "ref": args.ref,
        "repositories": collected,
    }
    views = {
        "repositories.json": {
            name: {
                key: value
                for key, value in record.items()
                if key in {"repository", "local_path", "ref", "sha", "remote", "provenance"}
            }
            for name, record in collected.items()
        },
        "versions.json": {
            name: {
                "repository": record["repository"],
                "sha": record["sha"],
                "metadata": record["metadata"],
                "tags": record["tags"],
                "provenance": record["provenance"]["metadata"],
            }
            for name, record in collected.items()
        },
        "capabilities.json": {
            name: {
                "repository": record["repository"],
                "sha": record["sha"],
                "entrypoints": record["entrypoints"],
                "contracts": record["contracts"],
                "tests": record["tests"],
                "provenance": record["provenance"],
            }
            for name, record in collected.items()
        },
        "dependencies.json": {
            name: {
                "repository": record["repository"],
                "sha": record["sha"],
                "dependencies": dependencies(workspace / name, args.ref, tree(workspace / name, args.ref)),
                "provenance": provenance(args.ref, "pyproject.toml/package.json/git tree", "git show REF:FILE; git ls-tree"),
            }
            for name, record in collected.items()
        },
        "workflows.json": {
            name: {
                "repository": record["repository"],
                "sha": record["sha"],
                "workflows": record["workflows"],
                "provenance": record["provenance"]["workflows"],
            }
            for name, record in collected.items()
        },
    }
    for filename, content in views.items():
        (output / filename).write_text(
            json.dumps(
                {"schema_version": "1.0", "generated_at": generated, "ref": args.ref, "data": content},
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
    (output / "_raw.json").write_text(
        json.dumps(envelope, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps({"repositories": len(collected), "output": str(output), "ref": args.ref}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
