"""Experience-program tests: UI kit, wizard, home, non-interactive contract."""

from __future__ import annotations

import pytest

from theforge.ui import i18n
from theforge.ui.kit import (
    NonInteractive,
    UIContext,
    _ellipsize,
    dashboard,
    status_table,
)
from theforge.ui.wizard import env_check_rows

# -- capability detection ----------------------------------------------------


def test_context_detect_non_tty():
    ctx = UIContext.detect(force_plain=True)
    assert not ctx.interactive
    assert not ctx.color


def test_context_ascii_fallback():
    ctx = UIContext(interactive=False, color=False, unicode=False, width=80)
    assert ctx.cursor == ">" and ctx.checked == "x"


def test_ellipsize_never_loses_signal_silently():
    ctx = UIContext(interactive=True, color=False, unicode=False, width=20)
    assert _ellipsize(ctx, "x" * 50) == "x" * 17 + "."


def test_ellipsize_unicode_terminal():
    ctx = UIContext(interactive=True, color=False, unicode=True, width=20)
    assert _ellipsize(ctx, "x" * 50).endswith("…")


# -- i18n ---------------------------------------------------------------------


def test_i18n_pt_and_en():
    assert i18n.t("cancel", "en") == "Cancel"
    assert i18n.t("cancel", "pt") == "Cancelar"


def test_i18n_missing_key_falls_back():
    assert i18n.t("nonexistent-key", "en") == "nonexistent-key"


# -- non-interactive contract -------------------------------------------------


def test_select_raises_off_tty():
    from theforge.ui.kit import select

    ctx = UIContext(interactive=False, color=False, unicode=False, width=80)
    with pytest.raises(NonInteractive):
        select("x", ["a"], ctx=ctx)


def test_confirm_raises_off_tty():
    from theforge.ui.kit import confirm

    ctx = UIContext(interactive=False, color=False, unicode=False, width=80)
    with pytest.raises(NonInteractive):
        confirm("ok?", ctx=ctx)


def test_wizard_raises_off_tty():
    from theforge.ui.wizard import run_wizard

    ctx = UIContext(interactive=False, color=False, unicode=False, width=80)
    with pytest.raises(NonInteractive):
        run_wizard(forge_name="x", install_fn=lambda **kw: {}, ctx=ctx)


def test_home_raises_off_tty():
    from theforge.ui import home

    ctx = UIContext(interactive=False, color=False, unicode=False, width=80)
    with pytest.raises(NonInteractive):
        home.run_home(ctx=ctx)


# -- key reading (Windows msvcrt simulated) ------------------------------------


def test_read_key_windows_arrows(monkeypatch):
    import theforge.ui.kit as kit

    keys = iter(["\xe0", "H", "\xe0", "P", "\r"])
    monkeypatch.setattr(kit, "IS_WINDOWS", True)
    monkeypatch.setattr("msvcrt.getwch", lambda: next(keys))
    assert kit._read_key() == "up"
    assert kit._read_key() == "down"
    assert kit._read_key() == "enter"


def test_read_key_windows_chars(monkeypatch):
    import theforge.ui.kit as kit

    keys = iter([" ", "q", "\x1b"])
    monkeypatch.setattr(kit, "IS_WINDOWS", True)
    monkeypatch.setattr("msvcrt.getwch", lambda: next(keys))
    assert kit._read_key() == "space"
    assert kit._read_key() == "char:q"
    assert kit._read_key() == "esc"


# -- select loop with scripted keys --------------------------------------------


def test_select_navigates_and_returns(monkeypatch, capsys):
    import theforge.ui.kit as kit

    keys = iter(["\xe0", "P", "\r"])  # down, enter → index 1
    monkeypatch.setattr(kit, "IS_WINDOWS", True)
    monkeypatch.setattr("msvcrt.getwch", lambda: next(keys))
    ctx = UIContext(interactive=True, color=False, unicode=False, width=80)
    assert kit.select("pick", ["a", "b", "c"], ctx=ctx) == 1
    out = capsys.readouterr().out
    assert "pick" in out and "> b" in out


def test_select_esc_cancels(monkeypatch):
    import theforge.ui.kit as kit

    keys = iter(["\x1b"])
    monkeypatch.setattr(kit, "IS_WINDOWS", True)
    monkeypatch.setattr("msvcrt.getwch", lambda: next(keys))
    ctx = UIContext(interactive=True, color=False, unicode=False, width=80)
    assert kit.select("pick", ["a"], ctx=ctx) is None


def test_multi_select_toggles(monkeypatch, capsys):
    import theforge.ui.kit as kit

    keys = iter([" ", "\xe0", "P", " ", "\r"])  # toggle 0, down, toggle 1, enter
    monkeypatch.setattr(kit, "IS_WINDOWS", True)
    monkeypatch.setattr("msvcrt.getwch", lambda: next(keys))
    ctx = UIContext(interactive=True, color=False, unicode=False, width=80)
    assert kit.multi_select("pick", ["a", "b", "c"], ctx=ctx) == {0, 1}


# -- rendering ----------------------------------------------------------------


def test_dashboard_renders_sections(capsys):
    ctx = UIContext(interactive=False, color=False, unicode=False, width=80)
    dashboard("test", [("Sec", [("a", "1"), ("b", "2")])], ctx=ctx)
    out = capsys.readouterr().out
    assert "TEST" in out and "a" in out and "Sec" in out


def test_status_table_state_icons(capsys):
    ctx = UIContext(interactive=False, color=False, unicode=False, width=80)
    status_table([("forge-x", "HEALTHY", "ok"), ("forge-y", "DEGRADED", "bad")], ctx=ctx)
    out = capsys.readouterr().out
    assert "OK" in out and "FAIL" in out


# -- wizard evidence -----------------------------------------------------------


def test_env_check_rows_real_evidence():
    rows = dict(env_check_rows())
    assert "Python" in rows
    assert rows["Python"].count(".") == 2


# -- bare CLI routing ----------------------------------------------------------


def test_bare_main_non_tty_summary(capsys):
    """Off-TTY bare invocation keeps the classic summary (§6)."""
    from theforge.cli.main import main

    rc = main([])
    out = capsys.readouterr().out
    assert rc == 0 and out  # the product summary prints


def test_install_bare_non_tty_is_usage_error(capsys):
    from theforge.cli.main import main

    rc = main(["install"])
    assert rc != 0
    assert "install apply" in capsys.readouterr().err


# -- kit quality fixes ---------------------------------------------------------


def test_cell_width_wide_and_combining():
    from theforge.ui.kit import cell_width

    assert cell_width("abc") == 3
    assert cell_width("あいう") == 6  # CJK wide
    assert cell_width("éx") == 2   # combining accent
    assert cell_width("\x1b[32mOK\x1b[0m") == 2  # escapes don't count


def test_ellipsize_counts_cells_not_chars():
    from theforge.ui.kit import _ellipsize

    ctx = UIContext(interactive=False, color=False, unicode=True, width=10)
    # budget 8 cells: 3 CJK chars (6) + ellipsis (1) = 7; a 4th would be 9
    assert _ellipsize(ctx, "あいうえおか") == "あいう…"


def test_status_table_columns_align_with_color(capsys):
    """ANSI-colored icons must not shift the detail column."""
    import re

    from theforge.ui.kit import status_table

    ctx = UIContext(interactive=False, color=True, unicode=False, width=80)
    status_table([("a", "HEALTHY", "x"), ("bb", "FAIL", "y")], ctx=ctx)
    lines = [ln for ln in capsys.readouterr().out.splitlines() if ln.strip()]
    stripped = [re.sub(r"\x1b\[[0-9;]*m", "", ln) for ln in lines]
    # detail column starts at the same offset on both rows
    offs = [stripped[0].index("x"), stripped[1].index("y")]
    assert offs[0] == offs[1]


def test_select_windows_long_lists(monkeypatch, capsys):
    """20 options on an 8-line terminal must not draw past the screen."""
    import theforge.ui.kit as kit

    keys = iter(["\xe0", "P"] * 18 + ["\r"])  # to the bottom, then enter
    monkeypatch.setattr(kit, "IS_WINDOWS", True)
    monkeypatch.setattr("msvcrt.getwch", lambda: next(keys))
    ctx = UIContext(
        interactive=True, color=False, unicode=False, width=80, height=8,
    )
    picked = kit.select(
        "pick", [f"opt-{i}" for i in range(20)], ctx=ctx)
    assert picked == 18
    frames = capsys.readouterr().out.split("pick")  # each frame opens with title
    last = frames[-1]
    assert last.count("opt-") == 3  # avail = height-5 windowed
    assert "more" in last  # scroll markers present


def test_select_jk_aliases(monkeypatch):
    import theforge.ui.kit as kit

    keys = iter(["j", "k", "j", "\r"])  # down, up, down, enter → 1
    monkeypatch.setattr(kit, "IS_WINDOWS", True)
    monkeypatch.setattr("msvcrt.getwch", lambda: next(keys))
    ctx = UIContext(interactive=True, color=False, unicode=False, width=80)
    assert kit.select("pick", ["a", "b", "c"], ctx=ctx) == 1


def test_dumb_terminal_no_cursor_escapes(monkeypatch, capsys):
    """ansi=False ctx must not emit cursor-addressing escapes."""
    import theforge.ui.kit as kit

    keys = iter(["\r"])
    monkeypatch.setattr(kit, "IS_WINDOWS", True)
    monkeypatch.setattr("msvcrt.getwch", lambda: next(keys))
    ctx = UIContext(
        interactive=True, color=False, unicode=False, width=80, ansi=False,
    )
    assert kit.select("pick", ["a", "b"], ctx=ctx) == 0
    out = capsys.readouterr().out
    assert "\x1b[" not in out  # full re-print, no moves
    assert out.count("pick") == 1  # single frame printed once
