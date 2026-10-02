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
