"""Argument parsing and exit-code mapping for `theforge` / `forge`."""

import argparse
import contextlib
import sys
from collections.abc import Sequence

from theforge import __version__
from theforge.cli import commands
from theforge.errors import PersistenceError, UsageError


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--root", default=".", help="workspace root (default: current dir)")
    common.add_argument("--json", action="store_true", help="machine-readable JSON output")

    parser = argparse.ArgumentParser(
        prog="theforge", description="The Forge: one entry point, many specialists.")
    parser.add_argument("--version", action="version", version=f"theforge {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", parents=[common], help="create .forge/ in the workspace") \
        .set_defaults(handler=commands.cmd_init)
    sub.add_parser("doctor", parents=[common], help="inspect host, workspace and providers") \
        .set_defaults(handler=commands.cmd_doctor)
    sub.add_parser("status", parents=[common], help="summarize workspace state") \
        .set_defaults(handler=commands.cmd_status)

    registry = sub.add_parser("registry", help="provider registry") \
        .add_subparsers(dest="registry_command", required=True)
    registry.add_parser("list", parents=[common]) \
        .set_defaults(handler=commands.cmd_registry_list)
    registry.add_parser("refresh", parents=[common]) \
        .set_defaults(handler=commands.cmd_registry_refresh)
    show = registry.add_parser("show", parents=[common])
    show.add_argument("provider_id")
    show.set_defaults(handler=commands.cmd_registry_show)

    caps = sub.add_parser("capabilities", help="declared capabilities") \
        .add_subparsers(dest="capabilities_command", required=True)
    cap_list = caps.add_parser("list", parents=[common])
    cap_list.add_argument("--provider")
    cap_list.set_defaults(handler=commands.cmd_capabilities_list)
    cap_search = caps.add_parser("search", parents=[common])
    cap_search.add_argument("query")
    cap_search.set_defaults(handler=commands.cmd_capabilities_search)

    providers = sub.add_parser("providers", help="provider operations") \
        .add_subparsers(dest="providers_command", required=True)
    providers.add_parser("health", parents=[common]) \
        .set_defaults(handler=commands.cmd_providers_health)

    ask = sub.add_parser("ask", parents=[common], help="route a task to a specialist")
    ask.add_argument("intent")
    ask.add_argument("--capability")
    ask.add_argument("--action")
    ask.add_argument("--profile", choices=["economy", "balanced", "max"], default="balanced")
    ask.add_argument("--target", dest="targets", action="append")
    ask.add_argument("--allow-unverified", action="store_true")
    ask.set_defaults(handler=commands.cmd_ask)

    explain = sub.add_parser("explain", parents=[common], help="explain a past run")
    explain.add_argument("run_id")
    explain.set_defaults(handler=commands.cmd_explain)
    return parser


def _tolerate_unencodable_output() -> None:
    for stream in (sys.stdout, sys.stderr):
        with contextlib.suppress(AttributeError, ValueError, OSError):
            stream.reconfigure(errors="replace")  # type: ignore[union-attr]


def main(argv: Sequence[str] | None = None) -> int:
    _tolerate_unencodable_output()
    args = build_parser().parse_args(argv)
    try:
        return int(args.handler(args))
    except UsageError as exc:
        print(f"theforge: error: {exc}", file=sys.stderr)
        return 2
    except PersistenceError as exc:
        print(f"theforge: persistence error: {exc}", file=sys.stderr)
        return 5
    except KeyboardInterrupt:
        print("theforge: interrupted", file=sys.stderr)
        return 130
    except BrokenPipeError:
        return 1
    except Exception as exc:
        print(f"theforge: internal error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 70
