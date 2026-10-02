"""Provider entries from builtin, user and project sources (later wins by id)."""

import os
import sys
import tomllib
from dataclasses import dataclass
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


def load_entries(path: Path, source: Source) -> list[ProviderEntry]:
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
            entries.append(from_dict(ProviderEntry, raw, f"{path.name}.providers[{index}]"))
        except ContractError as exc:
            raise UsageError(str(exc)) from exc
    return entries


def resolve_entries(forge_dir: Path | None, user_dir: Path | None = None) -> list[ProviderEntry]:
    merged: dict[str, ProviderEntry] = {e.id: e for e in builtin_entries()}
    for entry in load_entries((user_dir or user_config_dir()) / PROVIDERS_FILE, "user"):
        merged[entry.id] = entry
    if forge_dir is not None:
        for entry in load_entries(forge_dir / "config" / PROVIDERS_FILE, "project"):
            merged[entry.id] = entry
    return sorted(merged.values(), key=lambda e: e.id)
