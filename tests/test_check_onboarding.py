"""Regression tests for scripts/check_onboarding.py command scanning.

The gate must validate ``theforge <verb> <sub>`` written in code spans
against the real argparse grammar without false-failing on prose or on an
option's ``choices`` group rendered under ``options:``.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _load():
    spec = importlib.util.spec_from_file_location(
        "check_onboarding", REPO / "scripts" / "check_onboarding.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


co = _load()


def _sub_findings(text: str) -> list[str]:
    out = []
    for line in co._code_spans(text):
        for verb, sub in co._THEFORGE_CMD.findall(line):
            subs = co._subcommands(verb)
            if subs and sub not in subs:
                out.append(f"{verb} {sub}")
    return sorted(set(out))


class TestSubcommandParsing:
    def test_subparser_verbs_return_their_set(self) -> None:
        subs = co._subcommands("install")
        assert subs is not None
        assert {"plan", "apply", "auto"} <= subs

    def test_option_choices_are_not_subcommands(self) -> None:
        # ``setup --scope {project,workspace,user}`` has no subparsers; the
        # choices group under ``options:`` must not be read as one.
        assert co._subcommands("setup") is None
        assert co._subcommands("status") is None


class TestCodeSpanScoping:
    def test_prose_does_not_trigger_subcommand_check(self) -> None:
        assert _sub_findings("depois rode theforge setup normalmente") == []
        assert _sub_findings("use theforge install the forges first") == []

    def test_inline_code_is_checked(self) -> None:
        assert _sub_findings("rode `theforge install bogus` aqui") == ["install bogus"]

    def test_fenced_code_is_checked(self) -> None:
        text = "exemplo:\n\n```bash\ntheforge install bogus\n```\n"
        assert _sub_findings(text) == ["install bogus"]

    def test_valid_subcommand_in_code_passes(self) -> None:
        text = "```bash\ntheforge install auto --forge api-forge\n```\n"
        assert _sub_findings(text) == []
