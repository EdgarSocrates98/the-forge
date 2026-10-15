"""Portal adapter for The Forge — the command center. Maps
forge/PortalApi/1 operations onto the real install/service, hostflow,
specialists, agents, knowledge and graphview federation services.

Nothing here fabricates state: every field comes from a real service
call; unverifiable values stay ``unverified``. Federation views come
from ``specialists.collect`` + ``kit.installed_forges`` — the same
evidence ``theforge specialists`` and ``theforge install auto`` use.
"""

from __future__ import annotations

import argparse
import json
import sys
from importlib import metadata as importlib_metadata
from pathlib import Path
from typing import Any

from theforge import _forge_portal as fp
from theforge import _installkit as kit
from theforge.install import service

_PACKAGE_ROOT = Path(__file__).resolve().parent
_REPO_ROOT = _PACKAGE_ROOT.parent.parent
# Clone layout: portal/assets na raiz. Wheel layout: force-include copia
# para theforge/portal_assets/ (mesmo padrão do _installkit vendored).
_ASSETS_CANDIDATES = (
    _PACKAGE_ROOT / "portal_assets",
    _REPO_ROOT / "portal" / "assets",
)
_ASSETS_DIR = next((d for d in _ASSETS_CANDIDATES if (d / "index.html").is_file()), None)
_SKILLS_CANDIDATES = (
    _REPO_ROOT / ".agents" / "skills",
    _PACKAGE_ROOT / "host_assets" / "skills",
)
_SKILLS_DIR = next((d for d in _SKILLS_CANDIDATES if d.is_dir()), None)
_DOCS_DIR = _REPO_ROOT / "docs"
_HOSTS: tuple[str, ...] = ("claude", "devin", "codex", "copilot")
_SCOPES = ("project", "workspace", "user")
_PROFILE_MAP = {"economy": "minimal", "balanced": "recommended", "full": "full"}


def _version() -> str:
    try:
        return importlib_metadata.version("theforge")
    except importlib_metadata.PackageNotFoundError:
        return "0.0.0+local"


def _health_state(status: dict[str, Any], doctor: dict[str, Any] | None) -> str:
    """Map the real lifecycle vocabulary — healthy|degraded|unverified —
    onto the contract InstallState. `status` is the ledger truth: an
    unverified ledger means "never installed", even when `doctor` reports
    `degraded` (its checks fail on missing artifacts)."""
    ledger = str(status.get("status") or "unverified").lower()
    if ledger == "unverified":
        return "NOT_INSTALLED"
    st = str((doctor or status).get("status") or "unverified").lower()
    if st == "unverified":
        return "NOT_INSTALLED"
    if st in ("degraded", "broken"):
        return "DEGRADED"
    if st == "healthy":
        checks = {c.get("id"): c.get("status") for c in (doctor or {}).get("checks", [])}
        mcp = checks.get("mcp-handshake")
        if mcp == "PASS":
            return "VERIFIED"
        if mcp in ("UNVERIFIED", "NOT_APPLICABLE", "BLOCKED"):
            return "ACTIVE"
        return "INSTALLED"
    return "NOT_INSTALLED"


class TheForgePortal(fp.PortalAdapter):
    forge_id = "the-forge"
    forge_name = "The Forge"
    forge_version = _version()
    cli = "theforge"
    theme = "the-forge"
    federated = True

    def __init__(self, workspace: Path | None = None) -> None:
        self.workspace = str((workspace or Path.cwd()).resolve())
        self._root = Path(self.workspace)
        self.assets_dir = _ASSETS_DIR
        self._tasks: list[dict[str, Any]] = []
        self._task_seq = 0
        self.ops = [
            *fp.default_operations(self),
            fp.Operation("GET", "/federation", lambda ctx: self._federation()),
            fp.Operation("GET", "/profiles", lambda ctx: self._profiles()),
            fp.Operation("GET", "/hosts", lambda ctx: self._hosts()),
            fp.Operation("GET", "/mcp/servers", lambda ctx: self._mcp_servers()),
            fp.Operation("GET", "/skills", lambda ctx: self._skills()),
            fp.Operation("GET", "/agents", lambda ctx: self._agents()),
            fp.Operation("GET", "/tasks", lambda ctx: list(self._tasks)),
            fp.Operation("GET", "/graphs", lambda ctx: self._graphs()),
            fp.Operation("GET", "/docs/search", lambda ctx: self._docs_search(ctx)),
            fp.Operation("GET", "/versions", lambda ctx: self._versions()),
            fp.Operation("GET", "/lab", lambda ctx: self._lab()),
            fp.Operation("POST", "/installation/plan", self._install_plan, mutating=True),
            fp.Operation(
                "POST",
                "/installation/apply",
                self._install_apply,
                mutating=True,
                confirm="apply",
                needs_plan_token=True,
            ),
            fp.Operation(
                "POST",
                "/installation/repair",
                self._install_repair,
                mutating=True,
                confirm="repair",
            ),
            fp.Operation(
                "POST",
                "/installation/uninstall",
                self._install_uninstall,
                mutating=True,
                confirm="uninstall",
            ),
            fp.Operation(
                "POST",
                "/federation/plan",
                self._federation_plan,
                mutating=True,
            ),
            fp.Operation(
                "POST",
                "/federation/install-auto",
                self._federation_install_auto,
                mutating=True,
                confirm="install",
                needs_plan_token=True,
            ),
            fp.Operation(
                "POST",
                "/profiles/apply",
                self._profiles_apply,
                mutating=True,
                confirm="apply",
            ),
            fp.Operation("POST", "/hosts/launch", self._hosts_launch, mutating=False),
            fp.Operation("POST", "/mcp/verify", self._mcp_verify, mutating=True, confirm="verify"),
            fp.Operation("POST", "/tasks/plan", self._tasks_plan, mutating=True),
            fp.Operation(
                "POST",
                "/tasks/execute",
                self._tasks_execute,
                mutating=True,
                confirm="execute",
                needs_plan_token=True,
                timeout=120,
            ),
        ]

    # ------------------------------------------------------------------
    # descriptor / health / capabilities
    # ------------------------------------------------------------------
    def capabilities(self) -> list[dict[str, Any]]:
        fed = self._specialists_rows()
        return [
            {"id": "install", "state": "supported"},
            {"id": "hosts", "state": "supported"},
            {"id": "mcp", "state": "supported"},
            {"id": "skills", "state": "supported" if _SKILLS_DIR else "unverified"},
            {"id": "agents", "state": "supported"},
            {"id": "tasks", "state": "supported"},
            {
                "id": "federation",
                "state": "supported" if fed else "unverified",
            },
            {"id": "docs", "state": "supported" if _DOCS_DIR.is_dir() else "unverified"},
            {
                "id": "graph",
                "state": "supported" if self._graph_view() is not None else "unverified",
            },
        ]

    def nav(self) -> list[dict[str, Any]]:
        return [
            {
                "id": "federation",
                "label_key": "nav.federation",
                "route": "/federation",
                "requires_capability": "federation",
            },
            {
                "id": "tasks",
                "label_key": "nav.tasks",
                "route": "/tasks",
                "requires_capability": "tasks",
            },
            {
                "id": "graph",
                "label_key": "nav.graph",
                "route": "/graph",
                "requires_capability": "graph",
            },
        ]

    def health(self) -> dict[str, Any]:
        status = self._status_doc()
        doctor = None
        doctor_error: str | None = None
        try:
            doctor = service.doctor(scope="project", root=self._root)
        except Exception as e:  # noqa: BLE001 — doctor failure degrades, never crashes bootstrap
            doctor_error = f"{type(e).__name__}: {e}"
        checks = [
            {
                "id": c.get("id", "check"),
                "state": c.get("status", "UNVERIFIED"),
                "detail": c.get("detail"),
            }
            for c in (doctor or {}).get("checks", [])
        ]
        if doctor_error:
            checks.append({"id": "doctor", "state": "UNVERIFIED", "detail": doctor_error})
        return {
            "state": _health_state(status, doctor),
            "checks": checks,
            "workspace": self.workspace,
            "profile": status.get("profile") if status.get("profile") else None,
            "updated_at": status.get("checked_at"),
        }

    def installation_status(self, ctx: fp.RequestContext | None = None) -> dict[str, Any]:
        return self.health()

    def _status_doc(self) -> dict[str, Any]:
        try:
            return service.status(scope="project", root=self._root)
        except Exception:  # noqa: BLE001
            return {"drift": {}, "status": "unverified"}

    # ------------------------------------------------------------------
    # versions / release management (spec §8.6, cyc8-06)
    #
    # Everything here is read from real local state — dist metadata, the
    # committed ecosystem manifest, CHANGELOG.md and install receipts.
    # Absent data is reported as null/UNVERIFIED, never fabricated.
    # ------------------------------------------------------------------
    def _versions(self) -> dict[str, Any]:
        import hashlib

        version = _version()
        origin: str | None = None
        try:
            dist = importlib_metadata.distribution("theforge")
            origin = "site-packages"
            direct = dist.read_text("direct_url.json")
            if direct and json.loads(direct).get("dir_info", {}).get("editable"):
                origin = "editable-checkout"
        except importlib_metadata.PackageNotFoundError:
            origin = None  # no dist metadata — origin unverifiable, never guessed
        except Exception:  # noqa: BLE001 — unreadable metadata stays honest
            origin = None
        repo_root = _REPO_ROOT

        manifest_path = repo_root / "ecosystem-compatibility.json"
        manifest_sha: str | None = None
        compat = "unverified — ecosystem manifest not found"
        release: str | None = None
        if manifest_path.is_file():
            raw = manifest_path.read_bytes()
            manifest_sha = hashlib.sha256(raw).hexdigest()
            try:
                from theforge.install.compatibility import load_manifest

                manifest = load_manifest(manifest_path)
                release = manifest.release
                verdict = manifest.check("the-forge", version) if version else "unknown"
                compat = (
                    f"forge/EcosystemCompatibility/v1 · release {manifest.release} "
                    f"· the-forge@{version or '?'} → {verdict}"
                )
            except Exception as exc:  # noqa: BLE001 — report, never guess
                compat = f"unverified — manifest invalid ({exc})"

        changelog = None
        changelog_path = repo_root / "CHANGELOG.md"
        if changelog_path.is_file():
            changelog = changelog_path.read_text(encoding="utf-8")[:20000]

        history: list[dict[str, Any]] = []
        receipts: list[dict[str, Any]] = []
        receipts_dir = self._root / ".forge" / "install" / kit.RECEIPTS_DIR
        if receipts_dir.is_dir():
            for f in sorted(receipts_dir.glob("*.json")):
                doc = kit._load_json(f, {})
                if not isinstance(doc, dict):
                    doc = {}
                receipts.append(
                    {
                        "file": f.name,
                        "operation": doc.get("operation") or None,
                        "status": doc.get("status") or None,
                    }
                )
                history.append(
                    {
                        # receipts carry no version-transition field — null
                        # stays honest (created_by is the installer's version,
                        # not the installed component's).
                        "version": doc.get("version") or None,
                        "at": doc.get("created_at") or None,
                        "detail": f"{doc.get('operation', '?')} — {doc.get('status', '?')}",
                    }
                )

        return {
            "installed": {
                "version": version,
                "origin": origin,
                "channel": None,
            },
            "available": {"version": None, "source": "offline — remote lookups disabled"},
            "compat": compat,
            "integrity": {
                "manifest_sha256": manifest_sha,
                "manifest_release": release,
                "manifest_path": str(manifest_path) if manifest_path.is_file() else None,
            },
            "changelog": changelog,
            "history": history,
            "receipts": receipts,
            "pending": None,
            "upgrade_plan": None,
            "rollback": {
                "supported": True,
                "hint": "theforge install repair --root <root> / install uninstall --root <root>",
            },
        }

    # ------------------------------------------------------------------
    # installation lifecycle — the-forge's own install on the workspace
    # ------------------------------------------------------------------
    def _lab(self) -> dict[str, Any]:
        """Forge Lab data (cyc9-10) — real receipts + reports emitted by
        `theforge lab collect` under benchmarks/. Nothing is synthesized:
        absent artifacts render as empty lists, malformed lines as notes."""
        bench = _REPO_ROOT / "docs" / "programs" / "ecosystem-2026" / "benchmarks"
        runs: list[dict[str, Any]] = []
        reports: list[dict[str, Any]] = []
        notes: list[str] = []
        if bench.is_dir():
            for f in sorted(bench.glob("results-*.jsonl")):
                forges: list[dict[str, Any]] = []
                for i, line in enumerate(f.read_text(encoding="utf-8").splitlines()):
                    if not line.strip():
                        continue
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        notes.append(f"{f.name}:{i + 1} unparsed line skipped")
                        continue
                    forges.append(
                        {
                            "forge": rec.get("forge"),
                            "status": rec.get("status"),
                            "suite": rec.get("suite"),
                            "mode": rec.get("mode"),
                            "results": rec.get("results") or [],
                        }
                    )
                runs.append({"file": f.name, "forges": forges})
            for f in sorted(bench.glob("*.md")):
                if f.name == "methodology.md":
                    continue
                reports.append(
                    {
                        "file": f.name,
                        "content": f.read_text(encoding="utf-8")[:60000],
                    }
                )
        return {
            "dir": str(bench.relative_to(_REPO_ROOT)) if bench.is_dir() else None,
            "runs": runs,
            "reports": reports,
            "notes": notes,
        }

    def _install_plan(self, ctx: fp.RequestContext) -> dict[str, Any]:
        scope = (ctx.body or {}).get("scope", "project")
        if scope not in _SCOPES:
            raise fp.PortalError(
                "PORTAL-BAD-FIELD",
                f"scope must be one of {_SCOPES}",
                details={"field": "scope", "got": scope},
            )
        host = (ctx.body or {}).get("host", "all")
        if host not in (*_HOSTS, "all", "none") and not all(
            h.strip() in _HOSTS for h in str(host).split(",")
        ):
            raise fp.PortalError(
                "PORTAL-BAD-FIELD",
                f"host must be one of {_HOSTS}",
                details={"field": "host", "got": host},
            )
        profile = (ctx.body or {}).get("profile", "recommended")
        plan_input = {"scope": scope, "profile": profile, "host": host}
        receipt = service.install(
            scope=scope,
            root=self._root,
            host=host,
            profile=profile,
            dry_run=True,
        )
        return {
            "status": receipt.get("status", "planned"),
            "plan": plan_input,
            "plan_token": ctx.handler.server.sign_plan(plan_input),
            "receipt": receipt,
            "actions": [
                {"kind": "file", "path": p, "status": "planned"}
                for p in receipt.get("planned_files", [])
            ],
        }

    def _install_apply(self, ctx: fp.RequestContext) -> dict[str, Any]:
        plan = (ctx.body or {}).get("plan") or {}
        if not ctx.handler.server.check_plan((ctx.body or {})["plan_token"], plan):
            raise fp.PortalError(
                "PORTAL-PLAN-STALE",
                "plan token does not match this plan or expired — regenerate the plan",
                http=409,
                retryable=True,
                action="regenerate_plan",
            )
        return service.install(
            scope=plan.get("scope", "project"),
            root=self._root,
            host=plan.get("host", "all"),
            profile=plan.get("profile", "recommended"),
            dry_run=False,
            yes=True,
        )

    def _install_repair(self, ctx: fp.RequestContext) -> dict[str, Any]:
        return service.repair(scope="project", root=self._root)

    def _install_uninstall(self, ctx: fp.RequestContext) -> dict[str, Any]:
        return service.uninstall(scope="project", root=self._root)

    # ------------------------------------------------------------------
    # federation — the command center: specialists lifecycle + registry +
    # delegated install_auto. Every row is evidence, never assumed state.
    # ------------------------------------------------------------------
    def _specialists_rows(self) -> list[dict[str, Any]]:
        try:
            from theforge import specialists
        except Exception:  # noqa: BLE001
            return []
        try:
            registered: set[str] = set()
            try:
                from theforge.registry import Registry
                from theforge.state import find_forge_dir

                registry = Registry(find_forge_dir(self._root))
                registered = {
                    r.entry.id for r in registry.records() if r.state in ("ok", "degraded")
                }
            except Exception:  # noqa: BLE001 — no .forge dir is a valid state
                registered = set()
            views = specialists.collect(
                workspace_root=self._root, registered=registered, probe_cli=True
            )
            return specialists.to_rows(views)
        except Exception:  # noqa: BLE001 — collect failure is unverified, not a crash
            return []

    def _federation(self) -> dict[str, Any]:
        rows = self._specialists_rows()
        try:
            installed = kit.installed_forges()
        except Exception:  # noqa: BLE001
            installed = []
        installed_ids = {m.get("forge_id") for m in installed if m.get("forge_id")}
        return {
            "specialists": rows,
            "installed_forges": sorted(installed_ids),
            "registry": {
                "count": len(installed),
                "path": str(kit.installations_dir()),
            },
            "summary": {
                "catalog": len(rows),
                "installed": len(installed_ids),
                "with_mcp": sum(1 for r in rows if r.get("mcp")),
                "with_checkout": sum(1 for r in rows if r.get("checkout")),
            },
        }

    def _federation_plan(self, ctx: fp.RequestContext) -> dict[str, Any]:
        body = ctx.body or {}
        scope = body.get("scope", "project")
        if scope not in _SCOPES:
            raise fp.PortalError(
                "PORTAL-BAD-FIELD",
                f"scope must be one of {_SCOPES}",
                details={"field": "scope", "got": scope},
            )
        forge = body.get("forge")
        host = body.get("host", "all")
        profile = body.get("profile", "recommended")
        gateway_profile = body.get("gateway_profile")
        raw_components = body.get("components")
        if isinstance(raw_components, dict):
            components = tuple(str(key) for key, enabled in raw_components.items() if enabled)
        elif isinstance(raw_components, list):
            components = tuple(str(item) for item in raw_components)
        elif raw_components is None:
            components = None
        else:
            raise fp.PortalError(
                "PORTAL-BAD-FIELD",
                "components must be an object or array",
                details={"field": "components"},
            )
        plan_input = {
            "scope": scope,
            "forge": forge,
            "host": host,
            "profile": profile,
            "gateway_profile": gateway_profile,
            "components": list(components) if components is not None else None,
        }
        try:
            receipt = service.install_auto(
                scope=scope,
                root=self._root,
                forge=forge,
                host=host,
                profile=profile,
                components=components,
                gateway_profile=gateway_profile,
                dry_run=True,
            )
        except kit.InstallError as e:
            raise fp.PortalError(
                "TF-PORTAL-NOT-REGISTERED",
                str(e),
                severity="warning",
                action="register the forge via the bootstrap setup first",
            ) from e
        return {
            "status": receipt.get("status", "planned"),
            "plan": plan_input,
            "plan_token": ctx.handler.server.sign_plan(plan_input),
            "receipt": receipt,
            "actions": [
                {"kind": "forge", "path": f.get("forge_id", "?"), "status": "planned"}
                for f in receipt.get("forges", [])
            ],
        }

    def _federation_install_auto(self, ctx: fp.RequestContext) -> dict[str, Any]:
        plan = (ctx.body or {}).get("plan") or {}
        if not ctx.handler.server.check_plan((ctx.body or {})["plan_token"], plan):
            raise fp.PortalError(
                "PORTAL-PLAN-STALE",
                "plan token does not match this plan or expired — regenerate the plan",
                http=409,
                retryable=True,
                action="regenerate_plan",
            )
        try:
            return service.install_auto(
                scope=plan.get("scope", "project"),
                root=self._root,
                forge=plan.get("forge"),
                host=plan.get("host", "all"),
                profile=plan.get("profile", "recommended"),
                components=tuple(plan.get("components") or ()) or None,
                gateway_profile=plan.get("gateway_profile"),
                dry_run=False,
                yes=True,
            )
        except kit.InstallError as e:
            raise fp.PortalError(
                "TF-PORTAL-NOT-REGISTERED",
                str(e),
                severity="warning",
                action="register the forge via the bootstrap setup first",
            ) from e

    # ------------------------------------------------------------------
    # profiles — same three profiles every forge exposes
    # ------------------------------------------------------------------
    def _profiles(self) -> list[dict[str, Any]]:
        current = self._installed_profile()
        return [
            {
                "id": pid,
                "label_key": f"profiles.{pid}",
                "description_key": f"profiles.{pid}.desc",
                "current": current == pid,
                "components": components,
            }
            for pid, components in (
                (
                    "economy",
                    {
                        "skills": False,
                        "agents": False,
                        "mcp": True,
                        "tui": False,
                        "graph_studio": False,
                    },
                ),
                (
                    "balanced",
                    {
                        "skills": True,
                        "agents": True,
                        "mcp": True,
                        "tui": True,
                        "graph_studio": False,
                    },
                ),
                (
                    "full",
                    {
                        "skills": True,
                        "agents": True,
                        "mcp": True,
                        "tui": True,
                        "graph_studio": True,
                    },
                ),
            )
        ]

    def _installed_profile(self) -> str:
        comp = self._root / ".forge" / "install" / "components.json"
        if not comp.is_file():
            return ""
        try:
            doc = json.loads(comp.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return ""
        if not isinstance(doc, dict) or not doc:
            return ""
        selected = {k for k, v in doc.items() if v}
        if selected >= {"skills", "agents", "mcp", "tui", "graph_studio"}:
            return "full"
        return ""

    def _profiles_apply(self, ctx: fp.RequestContext) -> dict[str, Any]:
        profile = (ctx.body or {}).get("profile", "balanced")
        real = _PROFILE_MAP.get(profile)
        if real is None:
            raise fp.PortalError(
                "PORTAL-BAD-FIELD",
                f"profile must be one of {sorted(_PROFILE_MAP)}",
                details={"field": "profile", "got": profile},
            )
        return service.install(
            scope="project",
            root=self._root,
            host="all",
            profile=real,
            dry_run=False,
            yes=True,
        )

    # ------------------------------------------------------------------
    # hosts — observe-only; launch returns the command to copy
    # ------------------------------------------------------------------
    def _hosts(self) -> list[dict[str, Any]]:
        from theforge import hostflow

        try:
            flow = hostflow.hosts_flow("all", repo=self._root, launch=False)
        except Exception as e:  # noqa: BLE001 — host probe degrades honestly
            return [
                {
                    "host": h,
                    "detected": False,
                    "version": None,
                    "supported": False,
                    "logged_in": None,
                    "integration": "unverified",
                    "launchable": False,
                    "detail": f"probe failed: {type(e).__name__}",
                }
                for h in _HOSTS
            ]
        out: list[dict[str, Any]] = []
        for h in flow.get("hosts", []):
            integration = h.get("integration") or {}
            detected = h.get("binary_path") is not None
            out.append(
                {
                    "host": h.get("host", "?"),
                    "detected": detected,
                    "version": h.get("version"),
                    "supported": h.get("state") in ("READY", "SUPPORTED"),
                    "logged_in": h.get("logged_in"),
                    "integration": integration.get("state", "unverified"),
                    "launchable": detected,
                    "command_hint": h.get("launch_command") if detected else None,
                    "detail": h.get("detail") or h.get("login_hint"),
                }
            )
        return out

    def _hosts_launch(self, ctx: fp.RequestContext) -> dict[str, Any]:
        host = (ctx.body or {}).get("host")
        if host not in _HOSTS:
            raise fp.PortalError(
                "PORTAL-BAD-FIELD",
                f"host must be one of {_HOSTS}",
                details={"field": "host", "got": host},
            )
        from theforge import hostflow

        flow = hostflow.hosts_flow(host, repo=self._root, launch=False)
        for h in flow.get("hosts", []):
            if h.get("binary_path") is None:
                return {
                    "command": None,
                    "refusal": "PORTAL-HOST-ABSENT",
                    "detail": f"{host} not detected on this system",
                }
            # A portal has no real TTY — return the command to copy.
            return {
                "command": h.get("launch_command"),
                "detail": f"run `{h.get('launch_command')}` in your terminal to open {host}",
                "host": h.get("host"),
            }
        return {"command": None, "refusal": "PORTAL-HOST-ABSENT", "detail": f"{host} not detected"}

    # ------------------------------------------------------------------
    # mcp — federation view: the-forge has no own MCP server by design
    # (mcp_command=() in its ForgeSpec); the MCP page shows each
    # specialist's real handshake state.
    # ------------------------------------------------------------------
    def _mcp_servers(self) -> list[dict[str, Any]]:
        try:
            from theforge import specialists

            views = specialists.collect(workspace_root=self._root, probe_cli=False)
        except Exception as e:  # noqa: BLE001
            return [
                {
                    "id": "the-forge",
                    "state": "DEGRADED",
                    "host": None,
                    "tools_count": None,
                    "last_verify": None,
                    "detail": f"specialists collect failed: {type(e).__name__}",
                }
            ]
        out: list[dict[str, Any]] = []
        for v in views:
            mcp = v.mcp or {}
            if not mcp.get("command"):
                out.append(
                    {
                        "id": v.lifecycle.provider,
                        "state": "NOT_APPLICABLE",
                        "host": None,
                        "tools_count": None,
                        "last_verify": None,
                        "detail": "no MCP server declared by this forge",
                    }
                )
                continue
            verified = getattr(v.lifecycle, "installation_state", "") in (
                "HEALTHY",
                "REGISTERED",
                "READY",
            )
            out.append(
                {
                    "id": v.lifecycle.provider,
                    "state": "CONFIGURED" if verified else "UNVERIFIED",
                    "host": None,
                    "tools_count": mcp.get("tools_count"),
                    "last_verify": None,
                    "detail": " ".join(mcp.get("command") or []),
                }
            )
        return out

    def _mcp_verify(self, ctx: fp.RequestContext) -> dict[str, Any]:
        forge = (ctx.body or {}).get("forge")
        try:
            from theforge import specialists

            views = specialists.collect(workspace_root=self._root, probe_cli=False)
        except Exception as e:  # noqa: BLE001
            raise fp.PortalError(
                "TF-PORTAL-MCP-UNVERIFIED",
                f"specialists collect failed: {type(e).__name__}",
                http=503,
                retryable=True,
            ) from e
        results: list[dict[str, Any]] = []
        for v in views:
            if forge and v.lifecycle.provider != forge:
                continue
            mcp = v.mcp or {}
            cmd = mcp.get("command")
            if not cmd:
                results.append(
                    {
                        "forge": v.lifecycle.provider,
                        "status": "NOT_APPLICABLE",
                        "detail": "no MCP server declared",
                    }
                )
                continue
            spec = kit.ForgeSpec(
                forge_id=v.lifecycle.provider,
                package=v.lifecycle.provider.replace("-", "_"),
                distribution=v.lifecycle.provider,
                cli_name=(v.cli or cmd[0]),
                python_spec=">=3.10",
                state_dir="",
                mcp_command=tuple(cmd),
                mcp_server_name=mcp.get("server_name"),
                mcp_verify_tool=mcp.get("verify_tool"),
            )
            outcome = kit.mcp_verify(spec)
            results.append(
                {
                    "forge": v.lifecycle.provider,
                    "status": outcome.get("status", "FAIL"),
                    "detail": outcome.get("detail"),
                }
            )
        if not results:
            raise fp.PortalError(
                "TF-PORTAL-MCP-NONE",
                "no MCP-declaring specialists found",
                severity="warning",
            )
        worst = "PASS" if all(r["status"] == "PASS" for r in results) else "FAIL"
        if any(r["status"] == "NOT_APPLICABLE" for r in results) and all(
            r["status"] == "NOT_APPLICABLE" for r in results
        ):
            worst = "NOT_APPLICABLE"
        return {
            "status": worst,
            "detail": (
                f"{sum(1 for r in results if r['status'] == 'PASS')}"
                f"/{len(results)} handshakes passed"
            ),
            "servers": results,
            "actions": [
                {
                    "kind": "handshake",
                    "path": f"mcp://{r['forge']}",
                    "status": r["status"],
                }
                for r in results
            ],
        }

    # ------------------------------------------------------------------
    # skills / agents — canonical sources: .agents/skills + agentic/agents
    # ------------------------------------------------------------------
    def _skills(self) -> list[dict[str, Any]]:
        if _SKILLS_DIR is None:
            raise fp.PortalError(
                "TF-PORTAL-NO-SKILLS",
                "skills dir not found in clone or installed bundle",
                http=503,
                retryable=True,
            )
        out: list[dict[str, Any]] = []
        for path in sorted(_SKILLS_DIR.iterdir()):
            skill_md = (
                path / "SKILL.md" if path.is_dir() else (path if path.name == "SKILL.md" else None)
            )
            if skill_md is None or not skill_md.is_file():
                continue
            try:
                head = skill_md.read_text(encoding="utf-8")[:2000]
            except OSError:
                continue
            name = path.name if path.is_dir() else path.parent.name
            desc = ""
            for line in head.splitlines():
                line = line.strip()
                if line and not line.startswith(("#", "---", "name:", "description:")):
                    desc = line[:200]
                    break
                if line.startswith("description:"):
                    desc = line.split(":", 1)[1].strip()[:200]
                    break
            out.append(
                {
                    "id": name,
                    "name": name,
                    "domain": "ecosystem",
                    "description": desc,
                    "state": "available",
                    "hosts": [],
                    "source": "catalog",
                }
            )
        return out

    def _agents(self) -> list[dict[str, Any]]:
        from theforge import agents as agents_mod

        specs = agents_mod.load_all()
        out: list[dict[str, Any]] = []
        for aid, spec in sorted(specs.items()):
            out.append(
                {
                    "id": aid,
                    "name": getattr(spec, "name", aid) or aid,
                    "role": getattr(spec, "authority", "agent"),
                    "description": (
                        getattr(spec, "purpose", "") or getattr(spec, "description", "") or ""
                    ),
                    "authority": getattr(spec, "authority", None),
                    "domains": list(getattr(spec, "domains", ()) or []),
                    "skills": list(getattr(spec, "skills", ()) or []),
                    "hosts": [],
                    "state": "available",
                }
            )
        return out

    # ------------------------------------------------------------------
    # tasks — safe read-only diagnostics + federation ops, real receipts
    # ------------------------------------------------------------------
    # Order matters — first needle hit wins. `federation`/`fleet` precede
    # `doctor` so "doctor dos especialistas" routes to specialists; `mcp`
    # precedes `verif` so "verificar handshake mcp" picks mcp_verify.
    _SAFE_TASKS: tuple[tuple[tuple[str, ...], str, str], ...] = (
        (("mcp", "handshake"), "mcp_verify", "federation MCP handshake verification"),
        (
            ("federation", "federac", "fleet", "especialista", "specialist"),
            "federation",
            "federation lifecycle view",
        ),
        (("doctor", "saúde", "saude", "verifica", "verif"), "doctor", "installation doctor"),
        (("status", "estado", "instala"), "status", "installation status"),
        (("grafo", "graph"), "graph", "federated graph view"),
        (("skill",), "skills", "skill catalog summary"),
        (("agent",), "agents", "agent roster summary"),
    )

    def _intent_to_task(self, intent: str) -> tuple[str, str] | None:
        low = intent.lower()
        for needles, verb, label in self._SAFE_TASKS:
            if any(n in low for n in needles):
                return verb, label
        return None

    def _tasks_plan(self, ctx: fp.RequestContext) -> dict[str, Any]:
        intent = ((ctx.body or {}).get("intent") or "").strip()
        if not intent:
            raise fp.PortalError(
                "PORTAL-MISSING-FIELD",
                "field 'intent' is required",
                details={"field": "intent"},
            )
        mapped = self._intent_to_task(intent)
        if mapped is None:
            verbs = sorted({v for _n, v, _l in self._SAFE_TASKS})
            raise fp.PortalError(
                "TF-PORTAL-AMBIGUOUS",
                "intent does not map to a safe portal task",
                severity="warning",
                action="use one of the safe tasks",
                details={"safe_verbs": verbs, "intent": intent},
            )
        verb, label = mapped
        plan = {"verb": verb, "label": label, "intent": intent}
        return {
            "plan": plan,
            "plan_token": ctx.handler.server.sign_plan(plan),
            "status": "planned",
        }

    def _tasks_execute(self, ctx: fp.RequestContext) -> dict[str, Any]:
        plan = (ctx.body or {}).get("plan") or {}
        verb = plan.get("verb", "")
        if not ctx.handler.server.check_plan((ctx.body or {})["plan_token"], plan):
            raise fp.PortalError(
                "PORTAL-PLAN-STALE",
                "plan token does not match — regenerate the plan",
                http=409,
                retryable=True,
                action="regenerate_plan",
            )
        self._task_seq += 1
        task_id = f"task-{self._task_seq}"
        record: dict[str, Any] = {
            "id": task_id,
            "verb": verb,
            "label": plan.get("label", verb),
            "stage": "running",
            "started_at": _now(),
            "finished_at": None,
            "exit_code": None,
        }
        try:
            result = self._run_safe_task(verb)
            record["stage"] = "completed"
            record["exit_code"] = 0
            record["receipt"] = result
        except fp.PortalError as e:
            record["stage"] = "refused"
            record["exit_code"] = 2
            record["refusal"] = e.code
            record["receipt"] = {"detail": str(e)}
        except Exception as e:  # noqa: BLE001 — task failure is data, not a crash
            record["stage"] = "failed"
            record["exit_code"] = 1
            record["receipt"] = {"error": f"{type(e).__name__}: {e}"}
        record["finished_at"] = _now()
        self._tasks.append(record)
        return {
            "status": record["stage"],
            "task": record,
            "actions": [{"kind": "task", "path": verb, "status": record["stage"]}],
        }

    def _run_safe_task(self, verb: str) -> dict[str, Any]:
        if verb == "status":
            return self._status_doc()
        if verb == "doctor":
            return service.doctor(scope="project", root=self._root)
        if verb == "federation":
            return self._federation()
        if verb == "mcp_verify":
            return self._mcp_verify(type("C", (), {"body": {}})())
        if verb == "graph":
            view = self._graph_view()
            if view is None:
                raise fp.PortalError(
                    "TF-PORTAL-NO-GRAPH",
                    "no graph evidence in this workspace",
                    action="run `theforge graph` against a workspace with providers",
                )
            return view
        if verb == "skills":
            return {"skills": len(self._skills())}
        if verb == "agents":
            return {"agents": len(self._agents())}
        raise fp.PortalError("PORTAL-UNSAFE-TASK", f"task '{verb}' is not in the safe set")

    # ------------------------------------------------------------------
    # graph — real federation: capability_view + per-specialist CLI views
    # merged with provider namespacing (graphview.federated_merge).
    # ------------------------------------------------------------------
    def _graph_view(self) -> dict[str, Any] | None:
        try:
            from theforge import graphview
        except Exception:  # noqa: BLE001
            return None
        try:
            views, notes = graphview.federated_views(workspace_root=self._root)
        except Exception:  # noqa: BLE001 — federation failure degrades, never crashes
            return None
        if not views:
            return None
        merged = graphview.federated_merge(views)
        doc = (
            merged.to_dict()
            if hasattr(merged, "to_dict")
            else json.loads(json.dumps(merged, default=str))
        )
        if notes:
            doc = {**doc, "federation_notes": notes}
        return doc

    def _graphs(self) -> dict[str, Any]:
        view = self._graph_view()
        if view is None:
            return {
                "availability": {
                    "state": "no_graph",
                    "detail": "no graph evidence — no specialist checkout produced a view",
                    "unlock": "run `theforge graph` in a workspace with registered providers",
                },
                "views": [],
                "studio_url": None,
            }
        return {
            "availability": {"state": "available"},
            "views": [view],
            "studio_url": None,
        }

    # ------------------------------------------------------------------
    # docs search — title-scan over docs/*.md, offline
    # ------------------------------------------------------------------
    def _docs_search(self, ctx: fp.RequestContext) -> list[dict[str, Any]]:
        query = (ctx.query.get("q") or [""])[0].strip().lower()
        limit = int((ctx.query.get("limit") or ["20"])[0])
        if not query or not _DOCS_DIR.is_dir():
            return []
        terms = query.split()
        hits: list[dict[str, Any]] = []
        for path in sorted(_DOCS_DIR.rglob("*.md")):
            try:
                head = path.read_text(encoding="utf-8", errors="replace")[:3000]
            except OSError:
                continue
            title = path.stem
            for line in head.splitlines():
                if line.startswith("# "):
                    title = line[2:].strip()
                    break
            rel = path.relative_to(_REPO_ROOT).as_posix()
            hay = f"{title} {rel}".lower()
            if not all(t in hay for t in terms):
                continue
            hits.append(
                {
                    "path": rel,
                    "title": title,
                    "excerpt": "",
                    "category": path.parent.name or "doc",
                }
            )
            if len(hits) >= limit:
                break
        return hits


def _now() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def build_server(workspace: Path | None = None, *, quiet: bool = True) -> fp.PortalServer:
    return fp.PortalServer(TheForgePortal(workspace), quiet=quiet)


def _portal(args: argparse.Namespace) -> dict[str, Any]:
    import webbrowser

    root = Path(args.root) if args.root else Path.cwd()
    adapter = TheForgePortal(root)
    if adapter.assets_dir is None:
        return {
            "refusal": "TF-PORTAL-NO-ASSETS",
            "status": "refused",
            "detail": (
                "portal assets not vendored — run `theforge portal` "
                "after `python scripts/vendor.py` in forge-portal"
            ),
        }
    server = fp.PortalServer(adapter, port=args.port, quiet=True)
    url = server.url
    print(
        json.dumps(
            {
                "url": url,
                "note": "portal is optional — CLI/MCP keep working without it",
            }
        ),
        flush=True,
    )
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        server.server_close()
    return {"status": "completed"}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="theforge portal",
        description="Serve The Forge command-center portal locally (127.0.0.1).",
    )
    ap.add_argument(
        "--no-browser",
        action="store_true",
        help="print the URL without opening the browser",
    )
    ap.add_argument("--port", type=int, default=0, help="port (0 = free port)")
    ap.add_argument("--root", default=None, help="workspace root (default: cwd)")
    args = ap.parse_args(argv)
    doc = _portal(args)
    return 0 if doc.get("status") == "completed" else 1


if __name__ == "__main__":
    sys.exit(main())
