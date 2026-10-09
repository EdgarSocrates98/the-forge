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
