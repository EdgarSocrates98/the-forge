"""Provider entries from builtin, user and project sources (builtin > user > project)."""

import os
import sys
import tomllib
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal

from theforge.contracts import ContractError, from_dict
from theforge.contracts.manifest import PROVIDER_ID
from theforge.contracts.types import TrustLevel
from theforge.errors import UsageError

Source = Literal["builtin", "user", "project"]
PROVIDERS_FILE = "providers.toml"
PYTHON_PLACEHOLDER = "{python}"


@dataclass(frozen=True, kw_only=True)
class ProviderEntry:
    id: str
    argv: list[str]
    trust: TrustLevel = "unverified"
    source: Source = "project"

    def __post_init__(self) -> None:
        if not PROVIDER_ID.match(self.id):
            raise ContractError(f"invalid provider id {self.id!r}")
        if not self.argv:
            raise ContractError(f"provider {self.id}: argv must not be empty")


def builtin_entries() -> list[ProviderEntry]:
    return [ProviderEntry(id="echo-forge", argv=[sys.executable, "-m", "theforge.providers.echo"],
                          trust="builtin", source="builtin")]


def user_config_dir() -> Path:
    override = os.environ.get("THEFORGE_CONFIG_DIR")
    if override:
        return Path(override)
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        base = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
        return base / "theforge"
    xdg = os.environ.get("XDG_CONFIG_HOME")
    return (Path(xdg) if xdg else Path.home() / ".config") / "theforge"


def load_entries(
    path: Path, source: Source, warnings: list[str] | None = None
) -> list[ProviderEntry]:
    if not path.is_file():
        return []
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise UsageError(f"{path}: cannot read providers file ({exc})") from exc
    items = data.get("providers", [])
    if not isinstance(items, list):
        raise UsageError(f"{path}: 'providers' must be an array of tables")
    entries: list[ProviderEntry] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise UsageError(f"{path}: providers[{index}] must be a table")
        if item.get("trust") == "builtin":
            raise UsageError(f"{path}: providers[{index}]: trust 'builtin' is reserved")
        raw = {**item, "source": source}
        if isinstance(raw.get("argv"), list):
            raw["argv"] = [sys.executable if a == PYTHON_PLACEHOLDER else a for a in raw["argv"]]
        try:
            entry = from_dict(ProviderEntry, raw, f"{path.name}.providers[{index}]")
        except ContractError as exc:
            raise UsageError(str(exc)) from exc
        if source == "project" and entry.trust != "unverified":
            if warnings is not None:
                warnings.append(
                    f"{path}: providers[{index}] ({entry.id}): trust {entry.trust!r} ignored; "
                    "project providers are always 'unverified' "
                    "(trust them in your user providers.toml)")
            entry = replace(entry, trust="unverified")
        entries.append(entry)
    return entries


def resolve_entries(
    forge_dir: Path | None,
    user_dir: Path | None = None,
    warnings: list[str] | None = None,
) -> list[ProviderEntry]:
    """Precedence by id: builtin > user > project. Builtin ids are reserved."""
    merged: dict[str, ProviderEntry] = {e.id: e for e in builtin_entries()}
    reserved = set(merged)
    user_path = (user_dir or user_config_dir()) / PROVIDERS_FILE
    sources: list[tuple[Path, Source]] = [(user_path, "user")]
    if forge_dir is not None:
        sources.append((forge_dir / "config" / PROVIDERS_FILE, "project"))
    for path, source in sources:
        for entry in load_entries(path, source, warnings):
            if entry.id in reserved:
                raise UsageError(
                    f"{path}: provider id {entry.id!r} is reserved for a builtin provider")
            if entry.id in merged:
                if warnings is not None:
                    warnings.append(
                        f"{path}: provider {entry.id!r} ignored; "
                        "already defined in user providers.toml")
                continue
            merged[entry.id] = entry
    return sorted(merged.values(), key=lambda e: e.id)
