"""The Forge full-screen TUI — entries bound to the real providers in home.py."""

from __future__ import annotations

from theforge.ui.app import ActionData, Entry, ForgeApp, TableData, TextData
from theforge.ui.kit import UIContext
from theforge.ui.screen import Column


def _specialists() -> TableData:
    from theforge.ui.home import _specialist_rows
    rows = _specialist_rows()
    return TableData(
        columns=[Column(key="name", title="specialist", width=28),
                 Column(key="detail", title="detail")],
        rows=[{"name": n, "detail": d} for n, d in rows])


def _hosts() -> TableData:
    from theforge.ui.home import _host_rows
    return TableData(
        columns=[Column(key="host", title="host", width=18),
                 Column(key="detail", title="state")],
        rows=[{"host": h, "detail": s} for h, s in _host_rows()])


def _recent() -> TableData:
    from theforge.ui.home import _recent_rows
    return TableData(
        columns=[Column(key="run", title="run", width=34),
                 Column(key="detail", title="detail")],
        rows=[{"run": r, "detail": d} for r, d in _recent_rows(12)])


def _capabilities() -> TableData:
    from pathlib import Path

    from theforge.capability_graph import Registry
    from theforge.cli.commands import _capability_rows
    from theforge.paths import find_forge_dir
    registry = Registry(find_forge_dir(Path.cwd()))
    rows = _capability_rows(registry.records())
    return TableData(
        columns=[Column(key="id", title="capability", width=30),
                 Column(key="provider", title="provider", width=22),
                 Column(key="desc", title="description")],
        rows=[{"id": r.get("id", ""), "provider": r.get("provider", ""),
               "desc": r.get("description", "")} for r in rows])


def _mcp() -> TextData:
    from theforge.install import service
    health = service.doctor(scope="project")
    lines = []
    for c in (health.get("checks") or []):
        if "mcp" in str(c.get("id", "")).lower() or "host" in str(c.get("id", "")).lower():
            lines.append(f"[{c.get('status', '?')}] {c.get('id')}: {c.get('detail', '')}")
    return TextData(lines=lines or ["no MCP checks in doctor output",
                                    "run `forge doctor` for full diagnostics"])


def _workspace() -> TextData:
    import io
    from contextlib import redirect_stdout

    from theforge.cli.main import main as cli_main
    sink = io.StringIO()
    with redirect_stdout(sink):
        rc = cli_main(["status"])
    out = sink.getvalue().rstrip().splitlines()
    return TextData(lines=out + ["", f"exit: {rc}"])


def _health() -> TextData:
    import io
    from contextlib import redirect_stdout

    from theforge.ui.home import _act_health
    sink = io.StringIO()
    with redirect_stdout(sink):
        _act_health(UIContext.detect(force_plain=True))
    return TextData(lines=sink.getvalue().rstrip().splitlines())


def _graph() -> ActionData:
    from theforge.ui.home import _act_graph
    ctx = UIContext.detect(force_plain=True)
    return ActionData(callable=lambda: _act_graph(ctx),
                      title="graph studio (browser)", suspend=True)


def _install() -> ActionData:
    from theforge.ui.home import _act_install
    ctx = UIContext.detect(force_plain=True)
    return ActionData(callable=lambda: _act_install(ctx),
                      title="install wizard", suspend=True)


def _task() -> ActionData:
    from theforge.ui.home import _run_task
    ctx = UIContext.detect(force_plain=True)
    return ActionData(callable=lambda: _run_task(ctx),
                      title="run a task", suspend=True)


def entries() -> list[Entry]:
    return [
        Entry(label="workspace status", provider=_workspace),
        Entry(label="specialists", provider=_specialists),
        Entry(label="capabilities", provider=_capabilities),
        Entry(label="run a task", provider=_task),
        Entry(label="hosts", provider=_hosts),
        Entry(label="mcp status", provider=_mcp),
        Entry(label="graph studio", provider=_graph),
        Entry(label="install wizard", provider=_install),
        Entry(label="health check", provider=_health),
        Entry(label="recent tasks", provider=_recent),
    ]


def run_tui(*, ctx: UIContext | None = None, version: str = "") -> int:
    ctx = ctx or UIContext.detect()
    return ForgeApp(ctx, forge_id="the-forge", title="command center",
                    entries=entries(), version=version).run()
