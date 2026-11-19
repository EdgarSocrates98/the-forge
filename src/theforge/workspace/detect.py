"""Bounded, evidence-based technology detection (cycle 16.1, §6.1–§6.2).

A local, deterministic, economical scan — no provider process, no network,
no file contents beyond the dependency manifests ``routing.signals``
already parses. Members come from the installkit's ``discover_projects``
(``.git`` or a project manifest, never assumed to be a monorepo); each
member is walked with hard bounds (``MAX_MEMBER_DEPTH`` levels,
``MAX_FILES_PER_MEMBER`` entries, vendor/ignored dirs skipped, symlinks
never followed).

Confidence vocabulary (closed):

- ``high``   — explicit markers: manifest files, project files, dependency
               entries, IaC file extensions.
- ``medium`` — structural evidence: source trees without a manifest.
- ``low``    — limited inference: a member whose only signal is its file
               population, or no evidence at all.

Every entry carries ``provenance`` (``observed`` | ``derived`` |
``inferred``) and the path/dependency that backs it — the summary never
invents technologies.
"""

from __future__ import annotations

import os
from pathlib import Path, PurePosixPath
from typing import Any, Final

from theforge._installkit import discover_projects
from theforge.routing.signals import dependencies_by_file
from theforge.security.paths import IGNORED_DIRS, is_secret_name

WORKSPACE_DETECTION_SCHEMA: Final = "forge/WorkspaceDetection/v1"

MAX_MEMBERS: Final = 64
MAX_MEMBER_DEPTH: Final = 3
MAX_FILES_PER_MEMBER: Final = 200
MAX_EVIDENCE_PER_MEMBER: Final = 8
MAX_EVIDENCE_PER_TECH: Final = 2

#: Vendor/tool dirs skipped inside a member on top of ``IGNORED_DIRS``.
_SKIP_DIRS: Final = frozenset(
    set(IGNORED_DIRS)
    | {
        ".terraform",
        ".next",
        ".nuxt",
        ".svelte-kit",
        "vendor",
        "site-packages",
        "target",
        "bin",
        "obj",
        "coverage",
        "out",
    }
)

#: Exact filename → tech (``high`` confidence, ``observed``).
_FILE_TECH: Final[dict[str, str]] = {
    "pyproject.toml": "python",
    "setup.py": "python",
    "setup.cfg": "python",
    "pipfile": "python",
    "poetry.lock": "python",
    "package.json": "node",
    "tsconfig.json": "typescript",
    "jsconfig.json": "node",
    "pom.xml": "java",
    "build.gradle": "java",
    "build.gradle.kts": "java",
    "settings.gradle": "java",
    "global.json": "dotnet",
    "databricks.yml": "databricks",
    "databricks.yaml": "databricks",
    "cdk.json": "aws",
    "amplify.yml": "aws",
    "serverless.yml": "serverless",
    "serverless.yaml": "serverless",
    "openapi.yaml": "openapi",
    "openapi.yml": "openapi",
    "openapi.json": "openapi",
    "swagger.yaml": "openapi",
    "swagger.json": "openapi",
    ".terraform.lock.hcl": "terraform",
}

#: Filename prefixes/globs → tech (``high``).
_GLOB_TECH: Final[tuple[tuple[str, str], ...]] = (
    ("requirements*.txt", "python"),
    ("*.csproj", "dotnet"),
    ("*.fsproj", "dotnet"),
    ("*.vbproj", "dotnet"),
    ("*.sln", "dotnet"),
    ("*.tf", "terraform"),
    ("*.tfvars", "terraform"),
    ("*.bicep", "bicep"),
    ("*.proto", "api"),
    ("*.openapi.yaml", "openapi"),
    ("*.openapi.json", "openapi"),
    ("*.controller.ts", "api"),
    ("*.graphql", "api"),
    ("*.gql", "api"),
)

#: Source extensions → tech (``medium`` — structural, never alone → high).
_EXT_TECH: Final[dict[str, str]] = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".jsx": "react",
    ".vue": "vue",
    ".svelte": "svelte",
    ".java": "java",
    ".kt": "java",
    ".cs": "dotnet",
    ".fs": "dotnet",
    ".go": "go",
    ".rs": "rust",
    ".scala": "java",
    ".sh": "shell",
}

#: Normalized dependency name → (tech, confidence).
_DEP_TECH: Final[dict[str, tuple[str, str]]] = {
    # Python / Spark
    "pyspark": ("pyspark", "high"),
    "boto3": ("aws", "high"),
    "botocore": ("aws", "medium"),
    "aws-lambda-powertools": ("aws", "high"),
    "aws-cdk-lib": ("aws", "high"),
    "awswrangler": ("aws", "high"),
    "moto": ("aws", "medium"),
    "databricks": ("databricks", "high"),
    "databricks-connect": ("databricks", "high"),
    "databricks-cli": ("databricks", "high"),
    "databricks-sdk": ("databricks", "high"),
    "delta-spark": ("delta", "high"),
    "azure-storage-blob": ("azure", "high"),
    "azure-identity": ("azure", "high"),
    "azureml-core": ("azure", "high"),
    "azure-functions": ("azure", "high"),
    # APIs
    "fastapi": ("fastapi", "high"),
    "starlette": ("fastapi", "medium"),
    "flask": ("flask", "high"),
    "django": ("django", "high"),
    "uvicorn": ("api", "medium"),
    "aiohttp": ("api", "medium"),
    "pydantic": ("api", "low"),
    "graphql-core": ("api", "medium"),
    # Node / frontend
    "react": ("react", "high"),
    "react-dom": ("react", "high"),
    "next": ("nextjs", "high"),
    "typescript": ("typescript", "high"),
    "vue": ("vue", "high"),
    "nuxt": ("vue", "high"),
    "svelte": ("svelte", "high"),
    "express": ("api", "high"),
    "fastify": ("api", "high"),
    "nestjs": ("api", "high"),
    "angular": ("angular", "high"),
    "vite": ("node", "low"),
    "webpack": ("node", "low"),
    # Infra-as-code via dependencies
    "cdktf": ("cdktf", "high"),
    "pulumi": ("pulumi", "high"),
    # Data
    "dbt": ("dbt", "high"),
    "dbt-core": ("dbt", "high"),
    "great-expectations": ("data-quality", "high"),
    "soda-core": ("data-quality", "high"),
}

#: Dependency prefix → tech (``high``), for families like ``azure-*``.
_DEP_PREFIX_TECH: Final[tuple[tuple[str, str], ...]] = (
    ("azure-", "azure"),
    ("databricks-", "databricks"),
    ("aws-cdk", "aws"),
    ("@aws-cdk", "aws"),
    ("@nestjs", "api"),
    ("@pulumi", "pulumi"),
    ("@angular", "angular"),
    ("@cdktf", "cdktf"),
    ("@types", "typescript"),
    ("glue-", "aws-glue"),
)

_CONFIDENCE_RANK: Final = {"low": 0, "medium": 1, "high": 2}
_PROVENANCE: Final = {"high": "observed", "medium": "inferred", "low": "inferred"}


#: Filenames that mark a directory as evidence-bearing even without
#: ``.git``/manifest markers (gitless members, terraform-only dirs — §6.1
#: never assumes "many subdirs" means workspace; evidence decides).
_MEMBER_EVIDENCE_FILES: Final = frozenset(_FILE_TECH) | {
    "requirements.txt",
}


def _has_member_evidence(directory: Path) -> bool:
    """One scandir: does this dir carry a tech-evidence file at depth 0?"""
    try:
        with os.scandir(directory) as it:
            for entry in it:
                if not entry.is_file(follow_symlinks=False):
                    continue
                lower = entry.name.lower()
                if lower in _MEMBER_EVIDENCE_FILES or lower.startswith("requirements"):
                    return True
                if any(PurePosixPath(lower).match(g) for g, _ in _GLOB_TECH):
                    return True
    except OSError:
        return False
    return False


def _member_dirs(root: Path, limitations: list[str]) -> list[Path]:
    """Discovered members ∪ evidence-bearing dirs, deduped, deterministic.

    A directory nested inside a discovered member is never re-counted —
    ``discover_projects`` already isolates member contents.
    """
    try:
        found = {p.resolve() for p in discover_projects(root, max_depth=MAX_MEMBER_DEPTH - 1)}
    except OSError:  # pragma: no cover — discover_projects swallows OSError
        found = set()
        limitations.append("member discovery failed (OSError)")

    def _inside_member(directory: Path) -> bool:
        return any(directory != m and directory.is_relative_to(m) for m in found)

    supplemental: list[Path] = []
    try:
        with os.scandir(root) as it:
            top = sorted(
                (e for e in it if e.is_dir(follow_symlinks=False) and not e.is_symlink()),
                key=lambda e: e.name,
            )
    except OSError as exc:
        limitations.append(f"cannot list root ({type(exc).__name__})")
        top = []
    for entry in top[:MAX_MEMBERS]:
        name = entry.name
        if name.startswith(".") or name in _SKIP_DIRS:
            continue
        child = Path(entry.path).resolve()
        if child in found or _inside_member(child):
            continue
        if _has_member_evidence(child):
            supplemental.append(child)
            continue
        # one extra level for grouped layouts (members/<repo>)
        try:
            with os.scandir(child) as it:
                subs = sorted(
                    (e for e in it if e.is_dir(follow_symlinks=False) and not e.is_symlink()),
                    key=lambda e: e.name,
                )
        except OSError:
            continue
        for sub in subs[:MAX_MEMBERS]:
            if sub.name.startswith(".") or sub.name in _SKIP_DIRS:
                continue
            candidate = Path(sub.path).resolve()
            if candidate not in found and _has_member_evidence(candidate):
                supplemental.append(candidate)
    members = sorted(
        found | set(supplemental[:MAX_MEMBERS]),
        key=lambda p: () if p == root else tuple(p.relative_to(root).as_posix().split("/")),
    )
    return members


def detect_workspace(root: Path) -> dict[str, Any]:
    """Per-member technology summary for the workspace under ``root``.

    Returns a ``forge/WorkspaceDetection/v1`` dict: ``members`` with
    ``techs`` (sorted names), per-member ``confidence`` and bounded
    ``evidence`` entries ``{tech, kind, confidence, detail}``;
    ``workspace_techs`` aggregates the union. ``limitations`` records
    every place the bounded scan could not look.
    """
    root = Path(root).resolve()
    limitations: list[str] = []
    members: list[dict[str, Any]] = []
    union: set[str] = set()
    if not root.is_dir():
        return _doc(str(root), members, union, [f"{root}: not a directory — nothing scanned"])

    member_dirs = _member_dirs(root, limitations)
    if not member_dirs:
        member_dirs = [root]
        limitations.append("no member markers found — scanned the root as the only member")
    if len(member_dirs) > MAX_MEMBERS:
        member_dirs = member_dirs[:MAX_MEMBERS]
        limitations.append(f"members truncated at {MAX_MEMBERS}")

    for member_dir in member_dirs:
        rel = "." if member_dir == root else member_dir.relative_to(root).as_posix()
        members.append(_scan_member(member_dir, rel, limitations))
        union.update(members[-1]["techs"])

    return _doc(str(root), members, union, limitations)


def _doc(
    root: str, members: list[dict[str, Any]], union: set[str], limitations: list[str]
) -> dict[str, Any]:
    return {
        "schema": WORKSPACE_DETECTION_SCHEMA,
        "root": root,
        "members": members,
        "workspace_techs": sorted(union),
        "confidence": {
            "high": "explicit markers (manifests, project files, dependency entries)",
            "medium": "structural evidence (source trees without a manifest)",
            "low": "limited inference",
        },
        "limitations": limitations,
    }


def _scan_member(member: Path, rel: str, limitations: list[str]) -> dict[str, Any]:
    """Bounded scan of one member directory."""
    found: dict[str, list[tuple[str, str, str]]] = {}  # tech -> [(confidence, kind, detail)]
    scanned = 0
    truncated = False

    def _hit(tech: str, confidence: str, kind: str, detail: str) -> None:
        entries = found.setdefault(tech, [])
        if len(entries) < MAX_EVIDENCE_PER_TECH:
            entries.append((confidence, kind, detail))

    def _walk(directory: Path, depth: int, prefix: str) -> None:
        nonlocal scanned, truncated
        if depth > MAX_MEMBER_DEPTH:
            return
        try:
            with os.scandir(directory) as it:
                entries = sorted(it, key=lambda e: e.name)
        except OSError as exc:
            limitations.append(f"{rel}: cannot list {prefix or '.'} ({type(exc).__name__})")
            return
        for entry in entries:
            if scanned >= MAX_FILES_PER_MEMBER:
                truncated = True
                return
            name = entry.name
            try:
                if entry.is_symlink():
                    continue
                if entry.is_dir(follow_symlinks=False):
                    if name.startswith(".") or name in _SKIP_DIRS:
                        continue
                    _walk(Path(entry.path), depth + 1, f"{prefix}{name}/")
                    continue
                if not entry.is_file(follow_symlinks=False):
                    continue
            except OSError:
                continue
            if is_secret_name(name):
                continue  # never opened, never reported as tech evidence
            scanned += 1
            lower = name.lower()
            if lower in _FILE_TECH:
                _hit(_FILE_TECH[lower], "high", "file", f"{prefix}{name}")
                continue
            for glob, tech in _GLOB_TECH:
                if PurePosixPath(lower).match(glob):
                    _hit(tech, "high", "file", f"{prefix}{name}")
                    break
            else:
                ext_tech = _EXT_TECH.get(Path(lower).suffix)
                if ext_tech is not None:
                    _hit(ext_tech, "medium", "source", f"{prefix}{name}")

    _walk(member, 1, "")

    # Dependency manifests at the member root (the same parsers Wave A
    # routing uses) — ``derived`` evidence.
    for dep_file, names in sorted(dependencies_by_file(member).items()):
        dep_rel = dep_file.relative_to(member).as_posix()
        for dep in sorted(names):
            hit = _DEP_TECH.get(dep)
            prefix_hit = next((t for p, t in _DEP_PREFIX_TECH if dep.startswith(p)), None)
            if hit is not None:
                _hit(hit[0], hit[1], "dependency", f"{dep} in {dep_rel}")
            elif prefix_hit is not None:
                _hit(prefix_hit, "high", "dependency", f"{dep} in {dep_rel}")

    # Composite detections — only when the constituent evidence exists.
    if "pyspark" in found and "aws" in found:
        _hit("aws-glue", "high", "composite", "pyspark + aws dependencies")
    if "pyspark" in found and ("databricks" in found or "delta" in found):
        _hit("databricks", "high", "composite", "pyspark + databricks/delta")
    for api_tech in ("fastapi", "flask", "django"):
        if api_tech in found:
            _hit("api", "high", "composite", f"{api_tech} dependency")
            break
    if "openapi" in found:
        _hit("api", "high", "composite", "openapi contract file")
    if "react" in found or "angular" in found or "vue" in found or "svelte" in found:
        _hit("frontend", "medium", "composite", "frontend framework")
    if "typescript" in found and "node" not in found:
        _hit("node", "medium", "composite", "typescript implies a node runtime")
    if "serverless" in found:
        _hit("aws", "medium", "composite", "serverless framework (aws-leaning, unverified)")

    if truncated:
        limitations.append(
            f"{rel}: file scan truncated at {MAX_FILES_PER_MEMBER} entries — "
            "evidence may be partial"
        )

    techs = sorted(found)
    best = "low"
    evidence: list[dict[str, Any]] = []
    for tech in techs:
        for confidence, kind, detail in found[tech]:
            if _CONFIDENCE_RANK[confidence] > _CONFIDENCE_RANK[best]:
                best = confidence
            if len(evidence) < MAX_EVIDENCE_PER_MEMBER:
                evidence.append(
                    {
                        "tech": tech,
                        "kind": kind,
                        "confidence": confidence,
                        "provenance": _PROVENANCE[confidence] if kind != "composite" else "derived",
                        "detail": detail,
                    }
                )
    if not techs:
        limitations.append(f"{rel}: no technology evidence found")
    return {
        "path": rel,
        "techs": techs,
        "confidence": best if techs else "low",
        "evidence": evidence,
    }


__all__ = [
    "MAX_FILES_PER_MEMBER",
    "MAX_MEMBERS",
    "MAX_MEMBER_DEPTH",
    "WORKSPACE_DETECTION_SCHEMA",
    "detect_workspace",
]
