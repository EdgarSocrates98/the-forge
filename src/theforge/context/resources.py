"""Resource resolver & retrieval over the typed resource catalog (Onda 04).

Pipeline per §10.2: discovery roots → catalog refs → policy validation →
selective retrieval. Three source classes per §9.5:

- ``checkout``   — workspace checkouts carrying ``forge.json``
  (``kit.discover_projects``).
- ``installed``  — wheel-embedded ``forge.agentic.json`` located via
  ``importlib.metadata`` (resource root = the manifest's directory).
- ``explicit``   — caller-authorized roots (bundles, projects, authorized
  user directories) passed to :func:`discover_roots`.

Retrieval is bounded, contained and redacted: paths may not escape the
declaring root, denied suffixes are refused, content passes through
``security.redact``, and every failure is typed — an absent resource is
never disguised as an empty list (§10.7 gate).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from importlib import metadata as importlib_metadata
from pathlib import Path

from theforge.contracts.base import from_dict
from theforge.contracts.specialist import AgenticManifest, ResourceEntry
from theforge.security.redact import redact_text
from theforge.specialists import catalog_resources

DEFAULT_MAX_BYTES = 262_144
"""Default read window for ``get`` — bounded retrieval per §10.5."""

MAX_LISTING = 500
"""Max entries when a declared location resolves to a directory."""

_INTEGRITY_CAP = 4_194_304
"""Full-file hashing is refused above this size — the window hash of the
served bytes is reported instead and flagged as partial."""

DENY_SUFFIXES = frozenset(
    {
        ".exe", ".dll", ".so", ".dylib", ".bin", ".com", ".bat", ".ps1",
        ".pyc", ".pyo", ".whl", ".zip", ".tar", ".gz", ".7z", ".jar",
        ".sqlite", ".sqlite3", ".db", ".pem", ".key", ".pfx", ".p12",
    }
)
"""Executables, archives and key material are never served as resources
(§10.6 — unexpected executables, secret reads)."""


class ResourceErrorKind(StrEnum):
    """Typed failure states per §10.7 — never masked as empty results."""

    NOT_INSTALLED = "resource_not_installed"
    NOT_INDEXED = "resource_not_indexed"
    UNAVAILABLE = "resource_unavailable"
    BLOCKED_BY_POLICY = "resource_blocked_by_policy"
    INVALID = "resource_invalid"
    CORRUPTED = "resource_corrupted"
    UNSUPPORTED_RUNTIME = "unsupported_runtime"
    UNSUPPORTED_HOST = "unsupported_host"
    PERMISSION_DENIED = "permission_denied"


class ResourceFailure(Exception):
    """Typed retrieval failure — ``kind`` + human-readable detail."""

    def __init__(self, kind: ResourceErrorKind, detail: str) -> None:
        super().__init__(detail)
        self.kind = kind
        self.detail = detail


@dataclass(frozen=True, kw_only=True)
class ForgeResourceRoot:
    """One discovered catalog root: where a forge's manifest lives."""

    forge_id: str
    root: Path
    origin: str  # checkout | installed | explicit
    manifest: AgenticManifest

    def __post_init__(self) -> None:
        object.__setattr__(self, "root", Path(self.root))


@dataclass(frozen=True, kw_only=True)
class ResourceRef:
    """Catalog reference — identity + declaring root. Never file content."""

    forge_id: str
    entry: ResourceEntry
    origin: str
    root: Path

    @property
    def identity(self) -> str:
        """Stable federated identity ``<forge-id>:<resource-id>`` (§9.4)."""
        return f"{self.forge_id}:{self.entry.id}"

    @property
    def effective_location(self) -> str | None:
        """Layout-aware location: wheels resolve ``packaged_location``."""
        if self.origin == "installed" and self.entry.packaged_location:
            return self.entry.packaged_location
        return self.entry.location

    @property
    def path(self) -> Path | None:
        if self.effective_location is None:
            return None
        return self.root / self.effective_location


@dataclass(frozen=True, kw_only=True)
class ResourceContent:
    """Served payload — bounded text, integrity and provenance (§10.5)."""

    identity: str
    origin: str
    location: str
    content_type: str  # text | listing
    text: str | None = None
    entries: list[str] | None = None
    encoding: str | None = None
    served_bytes: int = 0
    file_bytes: int | None = None
    truncated: bool = False
    redacted: bool = False
    sha256: str | None = None
    sha256_scope: str | None = None  # "window" | "file"
    listing_truncated: bool = False


def _load_manifest_at(path: Path) -> AgenticManifest | None:
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return from_dict(AgenticManifest, doc)
    except (OSError, json.JSONDecodeError, ValueError):
        return None


def _manifest_forge_id(path: Path) -> str | None:
    """``forge_id`` from sibling ``forge.json`` or the manifest itself."""
    forge_json = path.parent / "forge.json"
    try:
        doc = json.loads(forge_json.read_text(encoding="utf-8"))
        fid = doc.get("forge_id") or doc.get("id")
        if isinstance(fid, str) and fid:
            return fid
    except (OSError, json.JSONDecodeError):
        pass
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        fid = doc.get("forge_id") or doc.get("id")
        return fid if isinstance(fid, str) and fid else None
    except (OSError, json.JSONDecodeError):
        return None


def _installed_manifest(dist: importlib_metadata.Distribution) -> Path | None:
    """First ``forge.agentic.json`` shipped inside an installed wheel."""
    try:
        files = dist.files or ()
    except (OSError, ValueError):
        return None
    for f in files:
        if str(f).endswith("forge.agentic.json"):
            try:
                located = Path(str(dist.locate_file(f)))
            except (OSError, ValueError):
                continue
            if located.is_file():
                return located
    return None


def discover_roots(
    workspace_root: Path | None = None,
    *,
    explicit: Iterable[tuple[str, Path]] = (),
    package_map: dict[str, str] | None = None,
    scan_installed: bool = True,
) -> list[ForgeResourceRoot]:
    """Discover catalog roots — checkouts, installed dists, explicit dirs.

    ``package_map`` maps ``forge_id → distribution name`` for the
    ``installed`` source class; ``explicit`` pairs a ``forge_id`` with an
    authorized directory (bundle, project, user dir). ``scan_installed``
    (default on) additionally scans every installed distribution for a
    wheel-embedded ``forge.agentic.json`` — installed Forges need no map.
    """
    roots: list[ForgeResourceRoot] = []
    seen: set[tuple[str, str]] = set()

    def _add(fid: str, root: Path, origin: str, manifest_path: Path | None = None) -> None:
        mp = manifest_path or (root / "forge.agentic.json")
        manifest = _load_manifest_at(mp)
        if manifest is None:
            return
        key = (fid, str(root.resolve()))
        if key in seen:
            return
        seen.add(key)
        roots.append(
            ForgeResourceRoot(forge_id=fid, root=root, origin=origin, manifest=manifest)
        )

    if workspace_root is not None:
        from theforge import _installkit as kit

        for member in kit.discover_projects(workspace_root):
            fid = _manifest_forge_id(member / "forge.agentic.json")
            if fid and (member / "forge.agentic.json").is_file():
                _add(fid, member, "checkout")

    def _add_installed(dist: importlib_metadata.Distribution) -> None:
        mp = _installed_manifest(dist)
        if mp is None:
            return
        # Wheel-embedded manifests sit in a meta-dir (``_data``, ``data``,
        # ``forge``); the resource root is the package dir itself.
        pkg_root = mp.parent.parent if mp.parent.name in {
            "_data", "data", "forge",
        } else mp.parent
        fid = _manifest_forge_id(mp)
        if fid:
            _add(fid, pkg_root, "installed", manifest_path=mp)

    for _fid, dist_name in (package_map or {}).items():
        try:
            dist = importlib_metadata.distribution(dist_name)
        except importlib_metadata.PackageNotFoundError:
            continue
        _add_installed(dist)

    if scan_installed:
        for dist in importlib_metadata.distributions():
            _add_installed(dist)

    for fid, root in explicit:
        _add(fid, root, "explicit")
    return roots


Refs = list[ResourceRef]
"""Result alias — ``list`` is shadowed inside :class:`ResourceResolver`."""


def split_identity(identity: str) -> tuple[str, str]:
    """``<forge-id>:<resource-id>`` → parts; resource ids may nest ``kind:id``."""
    forge_id, sep, resource_id = identity.partition(":")
    if not sep or not forge_id or not resource_id:
        raise ResourceFailure(
            ResourceErrorKind.INVALID,
            f"identity must be <forge-id>:<resource-id>, got {identity!r}",
        )
    return forge_id, resource_id


class ResourceResolver:
    """Search, describe and retrieve cataloged resources across roots."""

    def __init__(self, roots: Iterable[ForgeResourceRoot]) -> None:
        self._roots: list[ForgeResourceRoot] = sorted(
            roots, key=lambda r: (r.forge_id, r.origin)
        )

    @property
    def roots(self) -> list[ForgeResourceRoot]:
        return list(self._roots)

    def _refs_for(self, root: ForgeResourceRoot) -> Iterable[ResourceRef]:
        for entry in catalog_resources(root.manifest):
            yield ResourceRef(
                forge_id=root.forge_id, entry=entry, origin=root.origin, root=root.root
            )

    def list(
        self,
        *,
        forge_id: str | None = None,
        kind: str | None = None,
        resource_class: str | None = None,
        availability: str | None = None,
    ) -> Refs:
        """Catalog refs matching the filters — metadata only (§10.4)."""
        out: list[ResourceRef] = []
        for root in self._roots:
            if forge_id is not None and root.forge_id != forge_id:
                continue
            for ref in self._refs_for(root):
                e = ref.entry
                if kind is not None and e.kind != kind:
                    continue
                if resource_class is not None and e.resource_class != resource_class:
                    continue
                if availability is not None and e.availability != availability:
                    continue
                out.append(ref)
        return out

    def search(
        self,
        term: str,
        *,
        forge_id: str | None = None,
        kind: str | None = None,
        limit: int = 50,
    ) -> Refs:
        """Deterministic substring match over id + tags + description.

        Lowercased containment scoring: id hit ranks above tag/description.
        No embeddings — catalogs are small (§10.4).
        """
        needle = term.casefold().strip()
        if not needle:
            return []
        scored: list[tuple[int, ResourceRef]] = []
        for ref in self.list(forge_id=forge_id, kind=kind):
            e = ref.entry
            hay_id = e.id.casefold()
            hay_tags = " ".join(t.casefold() for t in (e.tags or []))
            hay_desc = (e.description or "").casefold()
            if needle in hay_id:
                scored.append((0, ref))
            elif needle in hay_tags or needle in hay_desc:
                scored.append((1, ref))
        scored.sort(key=lambda t: (t[0], t[1].identity))
        return [ref for _rank, ref in scored[:limit]]

    def _root_of(self, forge_id: str) -> ForgeResourceRoot:
        for root in self._roots:
            if root.forge_id == forge_id:
                return root
        raise ResourceFailure(
            ResourceErrorKind.NOT_INSTALLED,
            f"forge {forge_id!r} has no discovered resource root",
        )

    def _ref_of(self, identity: str) -> ResourceRef:
        forge_id, resource_id = split_identity(identity)
        root = self._root_of(forge_id)
        for ref in self._refs_for(root):
            if ref.entry.id == resource_id:
                return ref
        raise ResourceFailure(
            ResourceErrorKind.NOT_INDEXED,
            f"{identity!r} is not in the {forge_id} resource catalog",
        )

    def describe(self, identity: str) -> ResourceRef:
        """Metadata + resolved path + liveness — still no content read."""
        ref = self._ref_of(identity)
        e = ref.entry
        if e.availability != "available":
            raise ResourceFailure(
                ResourceErrorKind.UNAVAILABLE,
                e.unavailable_reason or f"{identity!r} declared {e.availability}",
            )
        if e.location is None:
            raise ResourceFailure(
                ResourceErrorKind.UNAVAILABLE,
                f"{identity!r} declares no location",
            )
        return ref

    def _resolve_safe(self, ref: ResourceRef) -> Path:
        """Containment + symlink-escape gate (§10.6)."""
        try:
            root_real = ref.root.resolve()
        except OSError as exc:
            raise ResourceFailure(
                ResourceErrorKind.UNAVAILABLE, f"root does not resolve: {exc}"
            ) from exc
        assert ref.effective_location is not None  # describe() guarantees
        target = (root_real / ref.effective_location).resolve()
        try:
            target.relative_to(root_real)
        except ValueError as exc:
            raise ResourceFailure(
                ResourceErrorKind.BLOCKED_BY_POLICY,
                f"{ref.identity}: location escapes root {ref.effective_location!r}",
            ) from exc
        return target

    def get(
        self,
        identity: str,
        *,
        max_bytes: int = DEFAULT_MAX_BYTES,
        offset: int = 0,
        integrity: bool = False,
    ) -> ResourceContent:
        """Bounded, contained, redacted read of one resource (§10.5-10.6).

        Directory locations serve a bounded listing; files serve a text
        window. ``integrity=True`` hashes the whole file when it fits the
        integrity cap, else the served window (flagged ``sha256_scope``).
        """
        ref = self.describe(identity)
        target = self._resolve_safe(ref)
        if not target.exists():
            raise ResourceFailure(
                ResourceErrorKind.UNAVAILABLE,
                f"{identity}: declared location missing on disk",
            )
        if target.is_dir():
            try:
                names = sorted(p.name for p in target.iterdir())
            except PermissionError as exc:
                raise ResourceFailure(
                    ResourceErrorKind.PERMISSION_DENIED, f"{identity}: {exc}"
                ) from exc
            return ResourceContent(
                identity=identity,
                origin=ref.origin,
                location=ref.entry.location or "",
                content_type="listing",
                entries=names[:MAX_LISTING],
                listing_truncated=len(names) > MAX_LISTING,
            )
        if target.suffix.lower() in DENY_SUFFIXES:
            raise ResourceFailure(
                ResourceErrorKind.BLOCKED_BY_POLICY,
                f"{identity}: {target.suffix} content is not servable",
            )
        try:
            size = target.stat().st_size
            with target.open("rb") as fh:
                if offset:
                    fh.seek(offset)
                raw = fh.read(max_bytes + 1)
        except PermissionError as exc:
            raise ResourceFailure(
                ResourceErrorKind.PERMISSION_DENIED, f"{identity}: {exc}"
            ) from exc
        except OSError as exc:
            raise ResourceFailure(
                ResourceErrorKind.UNAVAILABLE, f"{identity}: {exc}"
            ) from exc
        truncated = len(raw) > max_bytes
        raw = raw[:max_bytes]
        try:
            text = raw.decode("utf-8")
            encoding = "utf-8"
        except UnicodeDecodeError as exc:
            raise ResourceFailure(
                ResourceErrorKind.CORRUPTED,
                f"{identity}: not decodable as utf-8 ({exc})",
            ) from exc
        redacted = redact_text(text)
        digest_scope = "window"
        if integrity and size <= _INTEGRITY_CAP and not truncated and not offset:
            digest_scope = "file"
            try:
                digest = hashlib.sha256(target.read_bytes()).hexdigest()
            except OSError:
                digest = hashlib.sha256(raw).hexdigest()
        else:
            digest = hashlib.sha256(raw).hexdigest()
        return ResourceContent(
            identity=identity,
            origin=ref.origin,
            location=ref.entry.location or "",
            content_type="text",
            text=redacted,
            entries=None,
            encoding=encoding,
            served_bytes=len(raw),
            file_bytes=size,
            truncated=truncated,
            redacted=(redacted != text),
            sha256=digest,
            sha256_scope=digest_scope,
        )


def build_resolver(
    workspace_root: Path | None = None,
    *,
    explicit: Iterable[tuple[str, Path]] = (),
    package_map: dict[str, str] | None = None,
) -> ResourceResolver:
    """One-call convenience: ``discover_roots`` → ``ResourceResolver``."""
    return ResourceResolver(
        discover_roots(workspace_root, explicit=explicit, package_map=package_map)
    )
