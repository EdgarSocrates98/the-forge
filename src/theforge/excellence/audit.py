"""Offline audit of federated Forge capabilities.

Audit reads filesystem markers and local Git metadata only. It does not import
specialists, execute project code, access network, or alter repositories. Local
registries remain authoritative; this module emits evidence projection only.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class CapabilitySpec:
    """Capability evidence definition for one repository."""

    name: str
    markers: tuple[str, ...]


@dataclass(frozen=True)
class RepositorySpec:
    """Repository identity and evidence markers used by the audit."""

    repo: str
    directory: str
    capabilities: tuple[CapabilitySpec, ...]


def load_repository_specs(root: Path) -> tuple[RepositorySpec, ...]:
    """Load workspace catalog from docs; no specialist identity is hardcoded."""

    candidates = (
        root / "docs/engineering-excellence/repositories.json",
        root / "the-forge/docs/engineering-excellence/repositories.json",
    )
    catalog = next((path for path in candidates if path.is_file()), None)
    if catalog is None:
        return ()
    document = json.loads(catalog.read_text(encoding="utf-8"))
    return tuple(
        RepositorySpec(
            repo=item["repo"],
            directory=item["directory"],
            capabilities=tuple(
                CapabilitySpec(name=capability["name"], markers=tuple(capability["markers"]))
                for capability in item["capabilities"]
            ),
        )
        for item in document["repositories"]
    )


def _git(path: Path, *args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(path), *args],
            capture_output=True,
            check=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    value = result.stdout.strip()
    return value or None


def _metadata(path: Path) -> dict[str, Any]:
    branch = _git(path, "branch", "--show-current")
    commit = _git(path, "rev-parse", "--short=12", "HEAD")
    dirty = _git(path, "status", "--porcelain=v1")
    return {
        "branch": branch or "unknown",
        "commit": commit or "unknown",
        "dirty": bool(dirty),
        "git": branch is not None and commit is not None,
    }


def _evidence(path: Path, markers: Iterable[str]) -> list[str]:
    evidence: list[str] = []
    for marker in markers:
        candidate = (path / marker).resolve()
        try:
            candidate.relative_to(path)
        except ValueError:
            continue
        if candidate.exists():
            evidence.append(marker)
    return sorted(evidence)


def _repo_report(root: Path, spec: RepositorySpec) -> dict[str, Any]:
    path = root / spec.directory
    try:
        path = path.resolve()
        path.relative_to(root)
    except ValueError:
        return {
            "repo": spec.repo,
            "path": spec.directory,
            "state": "invalid",
            "branch": "unknown",
            "commit": "unknown",
            "dirty": False,
            "git": False,
            "checks": [
                {
                    "repo": spec.repo,
                    "capability": capability.name,
                    "state": "invalid",
                    "evidence": [],
                    "confidence": 0.0,
                    "cost": "offline",
                    "next_action": "reject repository path outside workspace",
                }
                for capability in spec.capabilities
            ],
        }
    if not path.is_dir():
        return {
            "repo": spec.repo,
            "path": spec.directory,
            "state": "unavailable",
            "branch": "unknown",
            "commit": "unknown",
            "dirty": False,
            "git": False,
            "checks": [
                {
                    "repo": spec.repo,
                    "capability": capability.name,
                    "state": "unavailable",
                    "evidence": [],
                    "confidence": 0.0,
                    "cost": "offline",
                    "next_action": f"restore repository at {spec.directory}",
                }
                for capability in spec.capabilities
            ],
        }

    metadata = _metadata(path)
    checks = []
    for capability in spec.capabilities:
        evidence = _evidence(path, capability.markers)
        checks.append(
            {
                "repo": spec.repo,
                "capability": capability.name,
                "state": "observed" if evidence else "unknown",
                "evidence": evidence,
                "confidence": 1.0 if evidence else 0.0,
                "cost": "offline",
                "next_action": "inspect local contract and tests" if evidence else "investigate",
            }
        )
    return {
        "repo": spec.repo,
        "path": spec.directory,
        "state": "observed",
        **metadata,
        "checks": checks,
    }


def audit_workspace(root: Path, specs: Iterable[RepositorySpec] | None = None) -> dict[str, Any]:
    """Return stable, local-only evidence for configured Forge repositories."""

    resolved = root.expanduser().resolve()
    specs = tuple(load_repository_specs(resolved) if specs is None else specs)
    repositories = [_repo_report(resolved, spec) for spec in specs]
    checks = [check for repository in repositories for check in repository["checks"]]
    summary = {
        "repositories": len(repositories),
        "observed": sum(repository["state"] == "observed" for repository in repositories),
        "unavailable": sum(repository["state"] == "unavailable" for repository in repositories),
        "invalid": sum(repository["state"] == "invalid" for repository in repositories),
        "capabilities": len(checks),
        "capabilities_observed": sum(check["state"] == "observed" for check in checks),
        "capabilities_unknown": sum(check["state"] == "unknown" for check in checks),
    }
    return {
        "schema": "theforge/EngineeringAudit/v1",
        "mode": "offline",
        "root": str(resolved),
        "summary": summary,
        "repositories": repositories,
        "limitations": [
            "filesystem markers prove presence, not runtime quality",
            "local registries remain authoritative",
            "network, credentials and project code execution excluded",
        ],
        "spec": [asdict(spec) for spec in specs],
    }
