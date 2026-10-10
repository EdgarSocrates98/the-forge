"""ForgeApp full-screen app tests — render + key dispatch, no PTY."""

from __future__ import annotations

import pytest

from theforge.ui.app import (
    ActionData,
    Entry,
    ForgeApp,
    TableData,
    TextData,
)
from theforge.ui.kit import NonInteractive, UIContext
from theforge.ui.screen import Buffer, Column, StateSpec


def ctx(w: int = 80, h: int = 24) -> UIContext:
    return UIContext(interactive=False, color=False, unicode=False,
                     width=w, height=h, ansi=False)


def _table_app() -> ForgeApp:
    return ForgeApp(ctx(), forge_id="the-forge", title="t", entries=[
        Entry(label="items", provider=lambda: TableData(
            columns=[Column(key="n", title="n", width=10)],
            rows=[{"n": f"r{i}"} for i in range(5)])),
        Entry(label="notes", provider=lambda: TextData(lines=["a", "b"])),
        Entry(label="bad", provider=lambda: 1 / 0),
        Entry(label="go", provider=lambda: ActionData(
            callable=lambda: print("ran"), title="run")),
    ])


def test_render_two_panes():
    app = _table_app()
    buf = Buffer(ctx(), 80, 24)
    app.render(buf)
    out = "\n".join(buf.render())
    assert "menu" in out and "items" in out and "THE-FORGE" in out


def test_provider_error_renders_state():
    app = _table_app()
    app.nav_idx = 2
    app._load()
    assert isinstance(app.pane.data, StateSpec)
    assert app.pane.data.kind == "error"
    buf = Buffer(ctx(), 80, 24)
    app.render(buf)
    assert "provider failed" in "\n".join(buf.render())


def test_nav_keys_move_and_load():
    app = _table_app()
    app.on_key("down")
    assert app.nav_idx == 1 and isinstance(app.pane.data, TextData)
    app.on_key("up")
    assert app.nav_idx == 0


def test_quit_and_focus():
    app = _table_app()
    assert app.on_key("q") == "quit"
    app.on_key("enter")  # nav → content
    assert app.focus == "content"
    app.on_key("esc")
    assert app.focus == "nav"


def test_table_selection_moves():
    app = _table_app()
    app.on_key("enter")
    app.on_key("down")
    assert app.pane.selected == 1


def test_action_executes_real_callable():
    app = _table_app()
    app.nav_idx = 3
    app._load()
    assert isinstance(app.pane.data, ActionData)
    assert app.on_key("enter") is None  # focus nav→content first
    assert app.on_key("enter") == "exec"
    app._execute(app.pane.data)
    assert any("ran" in line for line in app.pane.log)


def test_run_refuses_non_tty():
    with pytest.raises(NonInteractive):
        _table_app().run()


def test_tui_entries_load():
    from theforge.ui import tui
    entries = tui.entries()
    assert {e.label for e in entries} >= {
        "specialists", "hosts", "install wizard", "graph studio"}
