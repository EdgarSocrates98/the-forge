"""Offline audit of federated Forge capabilities.

Audit reads filesystem markers and local Git metadata only. It does not import
specialists, execute project code, access network, or alter repositories. Local
registries remain authoritative; this module emits evidence projection only.
"""

from __future__ import annotations

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


def _capabilities(*groups: tuple[str, tuple[str, ...]]) -> tuple[CapabilitySpec, ...]:
    return tuple(CapabilitySpec(name, markers) for name, markers in groups)


REPOSITORIES: tuple[RepositorySpec, ...] = (
    RepositorySpec(
        "the-forge",
        "the-forge",
        _capabilities(
            ("routing", ("src/theforge/routing",)),
            ("registry", ("src/theforge/registry",)),
            ("context", ("src/theforge/context",)),
            ("economy", ("src/theforge/observations", "src/theforge/adaptive")),
            ("evals", ("tests/test_bench.py", "tests/test_adaptive_cycle41.py")),
            ("installation", ("src/theforge/install", "docs/portable-installation")),
            ("mcp", ("src/theforge/protocol",)),
            ("diagnostics", ("src/theforge/diagnostics",)),
            ("portal", ("portal", "src/theforge/portal")),
            ("tests", ("tests",)),
            ("docs", ("docs",)),
        ),
    ),
    RepositorySpec(
        "api-forge",
        "api-forge",
        _capabilities(
            ("routing", ("src/apiforge/runtime", "src/apiforge/agentops")),
            ("registry", ("src/apiforge/registry", "src/apiforge/contracts")),
            ("context", ("src/apiforge/context", "knowledge")),
            ("economy", ("src/apiforge/economy",)),
            ("evals", ("evals",)),
            ("installation", ("scripts", "docs/installation")),
            ("mcp", ("src/apiforge/mcp_protocol",)),
            ("diagnostics", ("src/apiforge/observability",)),
            ("portal", ("portal",)),
            ("tests", ("tests",)),
            ("docs", ("docs",)),
        ),
    ),
    RepositorySpec(
        "spark-forge-aws",
        "spark-forge-aws",
        _capabilities(
            ("routing", ("rules/catalog/routing.yaml", "sparkforge_aws")),
            ("registry", ("rules/catalog/schema_registry.yaml", "contracts")),
            ("context", ("knowledge",)),
            ("economy", ("sparkforge_aws/economy", "rules/catalog/benchmark.yaml")),
            ("evals", ("evals",)),
            ("installation", ("scripts",)),
            ("mcp", ("sparkforge_aws/mcp", "mcp")),
            ("diagnostics", ("sparkforge_aws/diagnostics",)),
            ("portal", ("portal",)),
            ("tests", ("tests",)),
            ("docs", ("docs",)),
        ),
    ),
    RepositorySpec(
        "spark-forge-azure",
        "spark-forge-azure",
        _capabilities(
            ("routing", ("sparkforge_azure/routing", "rules")),
            ("registry", ("sparkforge_azure/registry", "config")),
            ("context", ("sparkforge_azure/context", "knowledge")),
            ("economy", ("sparkforge_azure/economy",)),
            ("evals", ("evals",)),
            ("installation", ("scripts",)),
            ("mcp", ("sparkforge_azure/mcp",)),
            ("diagnostics", ("sparkforge_azure/diagnostics",)),
            ("portal", ("portal",)),
            ("tests", ("tests",)),
            ("docs", ("docs",)),
        ),
    ),
    RepositorySpec(
        "platform-forge",
        "platform-forge",
        _capabilities(
            ("routing", ("platformforge/routing", "rules")),
            ("registry", ("platformforge/registry", "contracts")),
            ("context", ("platformforge/context", "knowledge")),
            ("economy", ("platformforge/economy",)),
            ("evals", ("evals",)),
            ("installation", ("scripts",)),
            ("mcp", ("platformforge/mcp", "MCP.md")),
            ("diagnostics", ("platformforge/diagnostics",)),
            ("portal", ("portal",)),
            ("tests", ("tests",)),
            ("docs", ("docs",)),
        ),
    ),
    RepositorySpec(
        "forge-doctor-api",
        "forge-doctor-api",
        _capabilities(
            ("routing", ("src/forge_doctor_api/analyzers",)),
            ("registry", ("src/forge_doctor_api/contracts",)),
            ("context", ("src/forge_doctor_api/context",)),
            ("economy", ("src/forge_doctor_api/benchmarks",)),
            ("evals", ("tests", "labs")),
            ("installation", ("scripts",)),
            ("mcp", ("src/forge_doctor_api/mcp",)),
            ("diagnostics", ("src/forge_doctor_api/analyzers",)),
            ("portal", ("portal",)),
            ("tests", ("tests",)),
            ("docs", ("docs",)),
        ),
    ),
    RepositorySpec(
        "forge-doctor-data",
        "forge-doctor-data",
        _capabilities(
            ("routing", ("src/forge_doctor_data/analyzers",)),
            ("registry", ("src/forge_doctor_data/contracts",)),
            ("context", ("src/forge_doctor_data/context",)),
            ("economy", ("tools/benchmarks",)),
            ("evals", ("tests", "golden")),
            ("installation", ("scripts",)),
            ("mcp", ("src/forge_doctor_data/plugins",)),
            ("diagnostics", ("src/forge_doctor_data/core", "src/forge_doctor_data/analyzers")),
            ("portal", ("portal",)),
            ("tests", ("tests",)),
            ("docs", ("docs",)),
        ),
    ),
    RepositorySpec(
        "forge-portal",
        "forge-portal",
        _capabilities(
            ("routing", ("src/app",)),
            ("registry", ("src/app",)),
            ("context", ("src/app",)),
            ("economy", ("src/app",)),
            ("evals", ("e2e", "tests")),
            ("installation", ("scripts", "src/app")),
            ("mcp", ("src/app",)),
            ("diagnostics", ("src/app",)),
            ("portal", ("src/app",)),
            ("tests", ("tests", "e2e")),
            ("docs", ("docs",)),
        ),
    ),
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


def audit_workspace(root: Path, specs: Iterable[RepositorySpec] = REPOSITORIES) -> dict[str, Any]:
    """Return stable, local-only evidence for configured Forge repositories."""

    resolved = root.expanduser().resolve()
    specs = tuple(specs)
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
