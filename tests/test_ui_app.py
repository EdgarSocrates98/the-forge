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
    return UIContext(interactive=False, color=False, unicode=False, width=w, height=h, ansi=False)


def _table_app() -> ForgeApp:
    return ForgeApp(
        ctx(),
        forge_id="the-forge",
        title="t",
        entries=[
            Entry(
                label="items",
                provider=lambda: TableData(
                    columns=[Column(key="n", title="n", width=10)],
                    rows=[{"n": f"r{i}"} for i in range(5)],
                ),
            ),
            Entry(label="notes", provider=lambda: TextData(lines=["a", "b"])),
            Entry(label="bad", provider=lambda: 1 / 0),
            Entry(
                label="go", provider=lambda: ActionData(callable=lambda: print("ran"), title="run")
            ),
        ],
    )


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


def test_filter_accepts_text_and_backspace():
    app = _table_app()
    app.on_key("/")
    app.on_key("n")
    assert app.filter == "n"
    assert app.nav_idx == 1
    app.on_key("backspace")
    assert app.filter == ""
    app.on_key("esc")
    assert not app.filter_active


def test_command_palette_finds_and_opens_action():
    app = _table_app()
    app.on_key("ctrl-k")
    app.on_key("n")
    app.on_key("o")
    app.on_key("t")
    app.on_key("e")
    app.on_key("s")
    app.on_key("enter")
    assert app.nav_idx == 1
    assert isinstance(app.pane.data, TextData)
    assert app.focus == "content"
    assert not app.palette_active


def test_text_content_supports_page_scroll():
    app = _table_app()
    app.nav_idx = 1
    app._load()
    app.on_key("enter")
    app.on_key("pagedown")
    assert app.pane.scroll == 1
    app.on_key("home")
    assert app.pane.scroll == 0


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


def test_navigation_keeps_selected_entry_visible_on_long_menu():
    entries = [Entry(label=f"item-{i}", provider=lambda: TextData(lines=["ok"])) for i in range(30)]
    app = ForgeApp(ctx(60, 16), forge_id="the-forge", title="t", entries=entries)
    for _ in range(25):
        app.on_key("down")
    buf = Buffer(ctx(60, 16), 60, 16)
    app.render(buf)
    assert "item-25" in "\n".join(buf.render())


def test_suspended_action_does_not_capture_attached_output():
    seen = []
    app = ForgeApp(
        ctx(),
        forge_id="the-forge",
        title="t",
        entries=[
            Entry(
                label="go",
                provider=lambda: ActionData(
                    callable=lambda: seen.append("ran"), title="run", suspend=True
                ),
            )
        ],
    )
    data = app.pane.data
    assert isinstance(data, ActionData)
    app._execute(data, capture=False)
    assert seen == ["ran"]
    assert "attached terminal" in "\n".join(app.pane.log)


def test_empty_menu_renders_empty_state():
    app = ForgeApp(ctx(60, 16), forge_id="the-forge", title="t", entries=[])
    buf = Buffer(ctx(60, 16), 60, 16)
    app.render(buf)
    assert "no menu entries" in "\n".join(buf.render())


def test_tui_entries_load():
    from theforge.ui import tui

    entries = tui.entries()
    assert {e.label for e in entries} >= {
        "specialists",
        "hosts",
        "guided setup",
        "install wizard",
        "graph studio",
    }
