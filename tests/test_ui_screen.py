"""Full-screen engine tests — pure-render assertions, no PTY needed."""

from __future__ import annotations

import pytest

from theforge.ui import screen
from theforge.ui.kit import NonInteractive, UIContext
from theforge.ui.screen import (
    MIN_HEIGHT,
    MIN_WIDTH,
    Buffer,
    Column,
    StateSpec,
    Theme,
    header,
    key_bar,
    panel,
    state_view,
    table,
    too_small,
)


def ctx(w: int = 80, h: int = 24, *, color: bool = False,
        unicode: bool = False, interactive: bool = False,
        ansi: bool = False) -> UIContext:
    return UIContext(interactive=interactive, color=color, unicode=unicode,
                     width=w, height=h, ansi=ansi)


def test_buffer_clips_and_renders():
    buf = Buffer(ctx(), 80, 24)
    buf.draw(0, 0, "x" * 200)
    lines = buf.render()
    assert len(lines) == 24
    assert lines[0].strip("x ") == "" and len(lines[0]) <= 80 * 4


def test_header_renders_brand_and_rule():
    buf = Buffer(ctx(), 80, 24)
    header(buf, "the-forge", "home", theme=Theme.for_forge("the-forge"))
    out = buf.render()
    assert "THE-FORGE" in out[0]
    assert set(out[1].strip()) == {"-"}


def test_panel_returns_inner_region():
    buf = Buffer(ctx(), 80, 24)
    ix, iy, iw, ih = panel(buf, 0, 0, 40, 10, title="t", theme=Theme())
    assert (ix, iy, iw, ih) == (2, 1, 36, 8)
    out = buf.render()
    assert out[0].startswith("+") and out[9].startswith("+")


def test_state_view_centers_and_colorless_text():
    buf = Buffer(ctx(), 80, 24)
    state_view(buf, StateSpec(kind="error", title="boom",
                              detail="traceback", hint="press r"),
               theme=Theme())
    text = "\n".join(buf.render())
    assert "boom" in text and "traceback" in text and "press r" in text
    assert "x boom" in text  # ASCII icon present without color


def test_too_small_state():
    buf = Buffer(ctx(50, 10), 50, 10)
    too_small(buf, theme=Theme())
    text = "\n".join(buf.render())
    assert "too small" in text and "60x16" in text


def test_table_selection_marker_and_scroll():
    buf = Buffer(ctx(), 80, 24)
    cols = [Column(key="name", title="name", width=20),
            Column(key="state", title="state", width=8),
            Column(key="detail", title="detail")]
    rows = [{"name": f"n{i}", "state": "ok", "detail": "d"} for i in range(50)]
    table(buf, 2, 2, 76, 20, columns=cols, rows=rows, selected=30,
          theme=Theme())
    out = "\n".join(buf.render())
    assert "NAME" in out and ">" in out
    assert "n30" in out  # selected row scrolled into view


def test_theme_per_forge_accents():
    a = Theme.for_forge("forge-alpha")
    assert a.accent in {"33", "34", "35", "36", "32", "37"}
    assert Theme.for_forge("forge-alpha") == a  # deterministic across calls
    accents = {Theme.for_forge(f"f-{i}").accent for i in range(12)}
    assert len(accents) >= 3  # hash spreads across the cycle


def test_min_layout_60x16():
    buf = Buffer(ctx(MIN_WIDTH, MIN_HEIGHT), MIN_WIDTH, MIN_HEIGHT)
    header(buf, "f", "s", theme=Theme())
    key_bar(buf, [("up", "nav"), ("enter", "ok"), ("q", "quit")], theme=Theme())
    out = buf.render()
    assert len(out) == 16
    assert "nav" in out[-1] and "quit" in out[-1]


def test_color_mode_wraps_ansi():
    buf = Buffer(ctx(color=True, unicode=True), 80, 24)
    buf.draw(0, 0, "hi", style="31")
    assert "\x1b[31m" in buf.render()[0]


def test_screen_refuses_non_tty():
    with pytest.raises(NonInteractive), screen.Screen(ctx(interactive=False)):
        pass


def test_run_loop_refuses_non_tty():
    with pytest.raises(NonInteractive):
        screen.run_loop(ctx(interactive=False), lambda b: None)
