"""Argument parsing, governed error messages and exit-code mapping for `theforge` / `forge`.

Every error line keeps its historical prefix (`theforge: error:`, `theforge: persistence
error:`, `theforge: internal error:`, `theforge: interrupted`) and, except for the
interruption, ends with `[<code> · <family>]` (13.4). A traceback is never printed: with
`--debug` the redacted ``Diagnostic`` is printed as `theforge: debug:` lines instead (13.5,
13.6). The exits are the per-outcome values of ``EXIT_BY_STATUS`` plus ``FIXED_EXITS`` (13.7).
"""

import argparse
import contextlib
import sys
from collections.abc import Sequence
from typing import Final

from theforge import __version__
from theforge.cli import commands, render
from theforge.contracts import to_dict
from theforge.contracts.codes import Codes, hint_of
from theforge.diagnostics import build_diagnostic
from theforge.errors import ForgeError, PersistenceError, ReplayRefused
from theforge.security.redact import redact_text

EXIT_FAILURE: Final = 1  # unhealthy doctor/health, broken pipe
EXIT_USAGE: Final = 2
EXIT_REFUSED: Final = 4  # a refused replay, same exit as a refused outcome
EXIT_PERSISTENCE: Final = 5
EXIT_INTEGRITY: Final = commands.EXIT_INTEGRITY  # explain, replay --mode verify|render
EXIT_INTERNAL: Final = 70
EXIT_INTERRUPTED: Final = 130
FIXED_EXITS: Final = frozenset({EXIT_FAILURE, EXIT_USAGE, EXIT_PERSISTENCE, EXIT_INTEGRITY,
                                EXIT_INTERNAL, EXIT_INTERRUPTED})


PLAN_DESCRIPTION = """\
Plan a task across providers, one node per specialist, executed locally in sequence.

Without --from FILE the nodes are ordered by declared capability relations first (rule
`capability-graph`: requires and produces→consumes among qualified providers) and then by
the textual order of their keywords in the intent (rule `intent-order`): proxies of the
data flow that can infer a wrong dependency (e.g. "an API that consumes the Spark pipeline
data" puts the API first). Review the plan without --execute; --from FILE fixes the order
explicitly. An ambiguous decomposition may be resolved by a `proposes_plans` provider
(semantic tier), revalidated by the deterministic plan checks.
"""


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--root", default=".", help="workspace root (default: current dir)")
    common.add_argument("--json", action="store_true", help="machine-readable JSON output")
    common.add_argument("--debug", action="store_true",
                        help="on error, print the redacted diagnostic (never a traceback)")

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
    registry.add_parser("sources", parents=[common],
                        help="configured registry sources (untrusted metadata; "
                             "the local installed registry stays authoritative)") \
        .set_defaults(handler=commands.cmd_registry_sources)

    economy = sub.add_parser("economy", help="measured execution economy") \
        .add_subparsers(dest="economy_command", required=True)
    economy.add_parser("report", parents=[common],
                       help="aggregate recorded execution observations into a "
                            "global economy receipt (read-only, offline)") \
        .set_defaults(handler=commands.cmd_economy_report)
    economy_experiment = economy.add_parser(
        "experiment", parents=[common],
        help="evaluate a StrategyExperiment/v1 against local observations "
             "(read-only, advisory; never promotes)")
    economy_experiment.add_argument(
        "--spec", required=True, metavar="EXPERIMENT_JSON",
        help="a theforge/StrategyExperiment/v1 JSON document")
    economy_experiment.set_defaults(handler=commands.cmd_economy_experiment)
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
    cap_negotiate = caps.add_parser(
        "negotiate", parents=[common],
        help="negotiate a CapabilityRequirement against the registered manifests "
             "(offline, deterministic, machine-readable with --json)")
    cap_negotiate.add_argument("--requirement", required=True, metavar="REQ_JSON",
                               help="a theforge/CapabilityRequirement/v1 JSON document")
    cap_negotiate.set_defaults(handler=commands.cmd_capabilities_negotiate)
    cap_discover = caps.add_parser(
        "discover", parents=[common],
        help="remote discovery by requirement: negotiates installed providers "
             "first, then consults enabled registry sources — reports "
             "RemoteProviderCandidate metadata, never installs (§22-26)")
    discover_req = cap_discover.add_mutually_exclusive_group(required=True)
    discover_req.add_argument("--requirement", metavar="REQ_JSON",
                              help="a theforge/CapabilityRequirement/v1 JSON document")
    discover_req.add_argument("--capability", metavar="CAP",
                              help="shortcut: minimal requirement for a capability id")
    cap_discover.add_argument("--remote", action="store_true",
                              help="consult remote sources even when a local "
                                   "provider fully satisfies the requirement")
    cap_discover.add_argument(
        "--profile", choices=["economy", "balanced", "max"], default="balanced",
        help="how eagerly remote sources are consulted: economy only when no "
             "local capability exists, balanced when nothing fully satisfies "
             "the requirement (default), max always compares remote claims")
    cap_discover.set_defaults(handler=commands.cmd_capabilities_discover)

    install = sub.add_parser("install", help="governed provider installation") \
        .add_subparsers(dest="install_command", required=True)
    install_plan = install.add_parser(
        "plan", parents=[common],
        help="build a deterministic InstallationPlan/v2 for a remote candidate "
             "(plan-only: nothing is downloaded or installed)")
    install_plan.add_argument("--provider", required=True)
    install_plan.add_argument("--version", required=True,
                              help="pinned SemVer — never 'latest'")
    install_plan.add_argument("--source", required=True,
                              help="registry source id from registries.toml")
    install_plan.add_argument("--approve", action="store_true",
                              help="record the approval gate as granted "
                                   "(plan still does not execute)")
    install_plan.set_defaults(handler=commands.cmd_install_plan)

    graph = sub.add_parser(
        "graph", parents=[common],
        help="the capability graph: declared+observed relations of the registry "
             "and workspace (cached manifests only, no provider process)")
    graph.add_argument("--ref", metavar="CAPABILITY",
                       help="only the edges touching this capability "
                            "('provider/capability' or a bare capability id)")
    graph.add_argument("--mesh", action="store_true",
                       help="the domain mesh projection: per domain, the "
                            "observe/engineer/verify capabilities derived from "
                            "declared produces/consumes/can_verify relations")
    graph.set_defaults(handler=commands.cmd_graph)

    providers = sub.add_parser("providers", help="provider operations") \
        .add_subparsers(dest="providers_command", required=True)
    providers.add_parser("health", parents=[common]) \
        .set_defaults(handler=commands.cmd_providers_health)

    provider = sub.add_parser(
        "provider", help="provider authoring: scaffold and conformance") \
        .add_subparsers(dest="provider_command", required=True)
    provider_init = provider.add_parser(
        "init", parents=[common],
        help="write a stdlib-only provider skeleton into an empty directory")
    provider_init.add_argument("directory", help="target directory (new or empty)")
    provider_init.add_argument("--id", required=True, metavar="PROVIDER_ID",
                               help="the provider id the manifest will declare")
    provider_init.add_argument("--capability", metavar="CAPABILITY_ID",
                               help="first capability id (default: <id-prefix>.describe)")
    provider_init.set_defaults(handler=commands.cmd_provider_init)
    provider_check = provider.add_parser(
        "check", parents=[common],
        help="run the Forge Protocol conformance battery against an argv")
    provider_check.add_argument(
        "argv", nargs=argparse.REMAINDER, metavar="ARGV",
        help="the provider argv (prefix with -- when it starts with a dash)")
    provider_check.set_defaults(handler=commands.cmd_provider_check)

    ask = sub.add_parser("ask", parents=[common], help="route a task to a specialist")
    ask.add_argument("intent")
    ask.add_argument("--capability")
    ask.add_argument("--action")
    ask.add_argument("--requirement", metavar="REQ_JSON",
                     help="CapabilityRequirement/v1 JSON: negotiate provider fit "
                          "(see docs/capability-negotiation.md)")
    ask.add_argument("--use", metavar="PROVIDER", dest="use",
                     help="pin a provider (policy/protocol gates still apply)")
    ask.add_argument("--profile", choices=["auto", "economy", "balanced", "max"],
                     default="auto",
                     help="budget profile; auto lets the complexity engine decide")
    ask.add_argument("--target", dest="targets", action="append")
    ask.add_argument("--allow-unverified", action="store_true")
    ask.add_argument("--approve", dest="approvals", action="append", metavar="CAPABILITY",
                     help="approve a capability the policy would ask about (repeatable)")
    ask.set_defaults(handler=commands.cmd_ask)

    plan = sub.add_parser(
        "plan", parents=[common], help="plan (and optionally execute) a multi-provider task",
        description=PLAN_DESCRIPTION, formatter_class=argparse.RawDescriptionHelpFormatter)
    plan.add_argument("intent")
    plan.add_argument("--profile", choices=["auto", "economy", "balanced", "max"],
                      default="auto",
                      help="budget profile; auto lets the complexity engine decide")
    plan.add_argument("--target", dest="targets", action="append")
    plan.add_argument("--requirement", metavar="REQ_JSON",
                      help="CapabilityRequirement/v1 JSON: negotiate provider fit "
                           "for the demanded capability")
    plan.add_argument("--from", dest="plan_file", metavar="FILE",
                      help="explicit plan file (fixes the node order); default: decompose "
                           "the intent")
    plan.add_argument("--execute", action="store_true",
                      help="execute the nodes (default: plan only, outcome `planned`)")
    plan.add_argument("--allow-unverified", action="store_true")
    plan.add_argument("--approve", dest="approvals", action="append", metavar="CAPABILITY",
                      help="approve a capability for the nodes that use it (repeatable)")
    plan.set_defaults(handler=commands.cmd_plan)

    workspace = sub.add_parser("workspace", help="workspace description") \
        .add_subparsers(dest="workspace_command", required=True)
    workspace.add_parser("show", parents=[common],
                         help="describe the workspace (cached manifests only, no provider)") \
        .set_defaults(handler=commands.cmd_workspace_show)

    explain = sub.add_parser("explain", parents=[common], help="explain a past run")
    explain.add_argument("run_id")
    explain.set_defaults(handler=commands.cmd_explain)

    replay = sub.add_parser("replay", parents=[common],
                            help="re-render, re-verify or re-execute a past run")
    replay.add_argument("run_id")
    replay.add_argument("--mode", choices=["render", "verify", "execute"], required=True)
    replay.add_argument("--allow-unverified", action="store_true")
    replay.add_argument("--approve", dest="approvals", action="append", metavar="CAPABILITY",
                        help="approve a capability for the re-execution (repeatable)")
    replay.set_defaults(handler=commands.cmd_replay)

    resume = sub.add_parser(
        "resume", parents=[common],
        help="resume a plan run: nodes whose recorded inputs still verify are "
             "reused, the rest re-execute")
    resume.add_argument("run_id", help="the plan run to resume")
    resume.add_argument("--allow-unverified", action="store_true")
    resume.add_argument("--approve", dest="approvals", action="append", metavar="CAPABILITY",
                        help="approve a capability for the nodes that use it (repeatable)")
    resume.set_defaults(handler=commands.cmd_resume)

    decisions = sub.add_parser("decisions", parents=[common],
                             help="the project's reusable-decision memory "
                                  "(.forge/intel/decisions.json)")
    decisions.set_defaults(handler=commands.cmd_decisions)

    trace = sub.add_parser("trace", parents=[common],
                           help="the run's local trace: what happened, span by span "
                                "(explain answers why)")
    trace.add_argument("run_id")
    trace.set_defaults(handler=commands.cmd_trace)
    return parser


def _tolerate_unencodable_output() -> None:
    for stream in (sys.stdout, sys.stderr):
        with contextlib.suppress(AttributeError, ValueError, OSError):
            stream.reconfigure(errors="replace")  # type: ignore[union-attr]


def _stage(args: argparse.Namespace) -> str:
    sub = next((getattr(args, name) for name in vars(args)
                if name.endswith("_command") and isinstance(getattr(args, name), str)), None)
    return f"cli:{args.command}" + (f":{sub}" if sub else "")


def _text(exc: BaseException) -> str:
    try:
        return str(exc)
    except Exception:  # noqa: BLE001 - a broken __str__ must not escape as a traceback
        return "<unprintable message>"


def _fail(args: argparse.Namespace, prefix: str, message: str, exc: BaseException,
          code: str) -> None:
    print(f"theforge: {prefix}: {redact_text(render.clean(message))} "
          f"{render.code_suffix(code, commands.error_family(code))}", file=sys.stderr)
    hint = hint_of(code)
    if hint:
        print(f"theforge: hint: {hint}", file=sys.stderr)
    if getattr(args, "debug", False):
        diagnostic = build_diagnostic(exc, stage=_stage(args), code=code)
        commands.print_debug(to_dict(diagnostic))


def main(argv: Sequence[str] | None = None) -> int:
    _tolerate_unencodable_output()
    args = build_parser().parse_args(argv)
    try:
        return int(args.handler(args))
    except PersistenceError as exc:
        _fail(args, "persistence error", _text(exc), exc, exc.code)
        return EXIT_PERSISTENCE
    except ReplayRefused as exc:
        _fail(args, "error", _text(exc), exc, exc.code)
        return EXIT_REFUSED
    except ForgeError as exc:
        _fail(args, "error", _text(exc), exc, exc.code)
        return EXIT_USAGE
    except KeyboardInterrupt:
        print("theforge: interrupted", file=sys.stderr)
        return EXIT_INTERRUPTED
    except BrokenPipeError:
        return EXIT_FAILURE
    except Exception as exc:  # noqa: BLE001 - never a traceback: governed message, exit 70
        _fail(args, "internal error", f"{type(exc).__name__}: {_text(exc)}", exc,
              Codes.INTERNAL)
        return EXIT_INTERNAL
