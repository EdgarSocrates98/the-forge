"""Capability table of the Spark Forge adapter: capability -> actions -> native tools, routing
signals, argument bindings and the reasons a native tool is not exposed.

Origin: audit of the ``sparkforge-aws`` 0.5 tool surface (2026-10-03). An action is the tool
name without ``sparkforge_``/``analyze_`` and with ``_`` -> ``-``. ``derive`` crosses the table
with the recorded snapshot (``native_catalog.json``): an action is declared only when its tool
is in the snapshot with ``readOnlyHint = true`` and ``openWorldHint = false`` and a binding fills
every required native argument from workspace files. A capability without declared actions is
not declared. Everything not exposed (catalogued actions and the rest of the native surface)
goes to the manifest ``limitations`` with the reason.

Bindings name the native argument and the globs a staged workspace path must match (full path
or file name). They follow the native file conventions (the ``.sparkforge/artifacts/<kind>/``
directories written by the collectors, ``*.tf``, ``*.asl.json``, ``workload.yaml``...): a binding
never accepts any file, and none accepts Markdown. A tool whose input has no such convention, or
that needs a value no ``ExecuteRequest`` v1 field carries, has no binding and is not declared.
"""

from __future__ import annotations

import fnmatch
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SNAPSHOT_PATH = Path(__file__).with_name("native_catalog.json")
STATE = "supported"
OPERATION_CLASS = "read_only"
TOOL_PREFIX = "sparkforge_"
ANALYZE_PREFIX = "analyze_"
UNMAPPED_REASON = "not mapped to a capability by this adapter version"

# Why a catalogued tool has no binding.
FACTS_INPUT = "consumes facts produced by another Spark Forge analyzer, not a workspace file"
NO_CONVENTION = ("reads a dump with no native file name or directory convention, so no "
                 "workspace file can be bound to it")
DISCRIMINATOR = ("requires the dump vocabulary in 'artifact', which workspace files do not "
                 "identify")


@dataclass(frozen=True)
class SignalsSpec:
    """Routing signals of a capability (from the domain of its native tools)."""

    keywords: tuple[str, ...] = ()
    file_globs: tuple[str, ...] = ()
    dependencies: tuple[str, ...] = ()


@dataclass(frozen=True)
class ArgBinding:
    """How a native argument is filled from ``stage/``: the staged paths matching ``globs``.

    ``directory``: the native argument also accepts a directory (the staged directory that
    holds the matches) instead of a single file.
    """

    arg: str
    globs: tuple[str, ...]
    directory: bool = False


@dataclass(frozen=True)
class CapabilitySpec:
    """One capability: its actions ``(action, native tool)`` in declaration order."""

    id: str
    description: str
    actions: tuple[tuple[str, str], ...]
    signals: SignalsSpec
    bindings: Mapping[str, ArgBinding] = field(default_factory=dict)  # tool -> binding
    unbound: Mapping[str, str] = field(default_factory=dict)  # tool -> why no binding


def action_name(tool: str) -> str:
    """The action of a native tool: no ``sparkforge_``/``analyze_`` prefix, ``_`` -> ``-``."""
    name = tool[len(TOOL_PREFIX):] if tool.startswith(TOOL_PREFIX) else tool
    if name.startswith(ANALYZE_PREFIX):
        name = name[len(ANALYZE_PREFIX):]
    return name.replace("_", "-")


def _actions(*tools: str, renamed: Mapping[str, str] | None = None
             ) -> tuple[tuple[str, str], ...]:
    names = renamed or {}
    return tuple((names.get(tool, action_name(tool)), tool) for tool in tools)


def _tool(name: str) -> str:
    return f"{TOOL_PREFIX}{name}"


def _analyze(name: str) -> str:
    return f"{TOOL_PREFIX}{ANALYZE_PREFIX}{name}"


def _artifacts(kind: str) -> tuple[str, ...]:
    """The collector artifact directory ``.sparkforge/artifacts/<kind>/``."""
    return (f"*artifacts/{kind}/*.json",)


EVENT_LOG_GLOBS = ("*artifacts/eventlog/*.jsonl", "*eventlog*.jsonl", "*event-log*.jsonl",
                   "*event_log*.jsonl")
PLAN_GLOBS = ("*explain*.txt", "*.plan.txt", "*physical-plan*.txt")
PYSPARK_GLOBS = ("*.py",)
AIRFLOW_GLOBS = ("*dags/*.py",)
ASL_GLOBS = ("*.asl.json",)
DBT_GLOBS = ("*target/manifest.json",)
CONSUMERS_GLOBS = ("consumers.yaml",)
WORKLOAD_GLOBS = ("workload.yaml",)


def _path(globs: tuple[str, ...], *, directory: bool = True) -> ArgBinding:
    return ArgBinding(arg="path", globs=globs, directory=directory)


CAPABILITIES: tuple[CapabilitySpec, ...] = (
    CapabilitySpec(
        id="pyspark.static-analysis",
        description=("Static analysis of PySpark code by AST (never imported nor executed): "
                     "partitioning, joins, UDFs, cache, driver actions and GraphFrames usage."),
        actions=_actions(_analyze("pyspark"), _analyze("graph"), _analyze("call_graph")),
        signals=SignalsSpec(keywords=("pyspark", "spark"), file_globs=PYSPARK_GLOBS,
                            dependencies=("pyspark",)),
        bindings={_analyze("pyspark"): _path(PYSPARK_GLOBS),
                  _analyze("graph"): _path(PYSPARK_GLOBS)},
        unbound={_analyze("call_graph"): FACTS_INPUT},
    ),
    CapabilitySpec(
        id="spark.runtime-analysis",
        description=("Spark runtime evidence already on disk: event logs (stage duration and "
                     "skew, spill, GC, per-plan-node SQL metrics) and saved physical plans."),
        actions=_actions(_analyze("event_log"), _analyze("sql_metrics"), _analyze("plan")),
        signals=SignalsSpec(keywords=("event log", "spark ui", "explain plan", "physical plan",
                                      "spill", "skew"),
                            file_globs=EVENT_LOG_GLOBS + PLAN_GLOBS),
        bindings={_analyze("event_log"): _path(EVENT_LOG_GLOBS, directory=False),
                  _analyze("sql_metrics"): _path(EVENT_LOG_GLOBS, directory=False),
                  _analyze("plan"): _path(PLAN_GLOBS, directory=False)},
    ),
    CapabilitySpec(
        id="streaming.analysis",
        description=("Saved streaming evidence: schema registry dumps and Structured Streaming "
                     "checkpoint, Kafka Connect, Kafka Streams and OpenLineage dumps."),
        actions=_actions(_analyze("streaming"), _analyze("transport"), _analyze("flink"),
                         _analyze("cdc"), _analyze("schema_registry"),
                         _analyze("event_driven"), _analyze("streaming_ops"),
                         _analyze("streaming_integrations"),
                         _analyze("streaming_composition"), _analyze("glue_streaming")),
        signals=SignalsSpec(keywords=("streaming", "structured streaming", "schema registry",
                                      "kafka connect", "openlineage"),
                            file_globs=(_artifacts("schema_registry")
                                        + _artifacts("streaming_integrations"))),
        bindings={_analyze("schema_registry"): _path(_artifacts("schema_registry")),
                  _analyze("streaming_integrations"):
                      _path(_artifacts("streaming_integrations"))},
        unbound={_analyze("streaming"): DISCRIMINATOR,
                 _analyze("transport"): DISCRIMINATOR,
                 _analyze("flink"): DISCRIMINATOR,
                 _analyze("cdc"): DISCRIMINATOR,
                 _analyze("event_driven"): NO_CONVENTION,
                 _analyze("streaming_ops"): NO_CONVENTION,
                 _analyze("streaming_composition"): FACTS_INPUT,
                 _analyze("glue_streaming"): NO_CONVENTION},
    ),
    CapabilitySpec(
        id="glue.analysis",
        description=("Saved AWS Glue evidence: Data Catalog resource-link topology collected "
                     "by the Spark Forge."),
        actions=_actions(_analyze("glue_job_runs"), _analyze("catalog_schema"),
                         _analyze("glue_resource_link"), _tool("glue_dependency_audit")),
        signals=SignalsSpec(keywords=("glue", "resource link", "glue catalog", "data catalog"),
                            file_globs=_artifacts("glue_resource_link")),
        bindings={_analyze("glue_resource_link"): _path(_artifacts("glue_resource_link"))},
        unbound={_analyze("glue_job_runs"): ("requires 'job_name', which no ExecuteRequest v1 "
                                             "field carries"),
                 _analyze("catalog_schema"): NO_CONVENTION,
                 _tool("glue_dependency_audit"): ("requires the Glue version in 'glue', which "
                                                  "no ExecuteRequest v1 field carries")},
    ),
    CapabilitySpec(
        id="emr.analysis",
        description=("Saved Amazon EMR dumps (on EC2, Serverless, on EKS): release, "
                     "applications, capacity and configuration."),
        actions=_actions(_analyze("emr_cluster"), _analyze("emr_serverless"),
                         _analyze("emr_eks")),
        signals=SignalsSpec(keywords=("emr", "emr serverless", "emr on eks"),
                            file_globs=(_artifacts("emr") + _artifacts("emr_serverless")
                                        + _artifacts("emr_eks"))),
        bindings={_analyze("emr_cluster"): _path(_artifacts("emr")),
                  _analyze("emr_serverless"): _path(_artifacts("emr_serverless")),
                  _analyze("emr_eks"): _path(_artifacts("emr_eks"))},
    ),
    CapabilitySpec(
        id="athena.analysis",
        description=("SQL text (projection, predicates, LIMIT) and saved Athena workgroup "
                     "dumps."),
        actions=_actions(_analyze("sql"), _analyze("athena_workgroup")),
        signals=SignalsSpec(keywords=("athena", "sql", "workgroup"),
                            file_globs=("*.sql", *_artifacts("athena"))),
        bindings={_analyze("sql"): _path(("*.sql",), directory=False),
                  _analyze("athena_workgroup"): _path(_artifacts("athena"))},
    ),
    CapabilitySpec(
        id="iceberg.analysis",
        description=("Saved Iceberg metadata-table dumps: small files, delete files, snapshot "
                     "cadence, manifest size and partition skew."),
        actions=_actions(_analyze("iceberg"), _tool("iceberg_assess_upgrade")),
        signals=SignalsSpec(keywords=("iceberg",), file_globs=_artifacts("iceberg")),
        bindings={_analyze("iceberg"): _path(_artifacts("iceberg"))},
        unbound={_tool("iceberg_assess_upgrade"): ("requires the source and target format "
                                                   "versions, which no ExecuteRequest v1 "
                                                   "field carries")},
    ),
    CapabilitySpec(
        id="parquet.footer-analysis",
        description=("Saved Parquet footer artifacts: row groups, column statistics, "
                     "dictionaries, page index, bloom filters and codecs."),
        actions=_actions(_analyze("parquet_footer")),
        signals=SignalsSpec(keywords=("parquet", "parquet footer", "row group"),
                            file_globs=_artifacts("parquet_footer")),
        bindings={_analyze("parquet_footer"): _path(_artifacts("parquet_footer"))},
    ),
    CapabilitySpec(
        id="terraform.analysis",
        description=("Terraform HCL of AWS Glue jobs: Glue version, workers, default "
                     "arguments and Spark UI observability."),
        actions=_actions(_analyze("terraform"), _analyze("terraform_diff")),
        signals=SignalsSpec(keywords=("terraform",), file_globs=("*.tf",)),
        bindings={_analyze("terraform"): _path(("*.tf",))},
        unbound={_analyze("terraform_diff"): ("compares two module directories ('before' and "
                                              "'after'); one workspace holds only one state")},
    ),
    CapabilitySpec(
        id="orchestration.analysis",
        description=("Orchestration definitions: Step Functions ASL and Airflow DAG files "
                     "(read by AST, never executed)."),
        actions=_actions(_analyze("controlm_jobs"), _analyze("step_functions"),
                         _analyze("sfn_history"), _analyze("airflow_dag"),
                         _analyze("orchestration")),
        signals=SignalsSpec(keywords=("airflow", "step functions", "control-m",
                                      "orchestration"),
                            file_globs=ASL_GLOBS + AIRFLOW_GLOBS,
                            dependencies=("apache-airflow",)),
        bindings={_analyze("step_functions"): _path(ASL_GLOBS),
                  _analyze("airflow_dag"): _path(AIRFLOW_GLOBS)},
        unbound={_analyze("controlm_jobs"): NO_CONVENTION,
                 _analyze("sfn_history"): NO_CONVENTION,
                 _analyze("orchestration"): NO_CONVENTION},
    ),
    CapabilitySpec(
        id="data-quality.analysis",
        description=("Data validation found in PySpark code: where each check runs, what it "
                     "costs and whether it has a consequence."),
        actions=_actions(_analyze("data_quality"), _analyze("dq_ai"), _tool("dq_ai_assess"),
                         _analyze("data_observability")),
        # *.py: the data-quality action reads PySpark sources, and the core sends only files
        # matching file_globs (one signal type, below the pyspark.static-analysis evidence).
        signals=SignalsSpec(keywords=("data quality", "deequ", "great expectations", "dqdl"),
                            file_globs=PYSPARK_GLOBS,
                            dependencies=("pydeequ", "great-expectations")),
        bindings={_analyze("data_quality"): _path(PYSPARK_GLOBS)},
        unbound={_analyze("dq_ai"): NO_CONVENTION,
                 _tool("dq_ai_assess"): FACTS_INPUT,
                 _analyze("data_observability"): NO_CONVENTION},
    ),
    CapabilitySpec(
        id="lakeformation.access-analysis",
        description=("Collected Lake Formation grants and simulated IAM decisions, with the "
                     "layer that decided."),
        actions=_actions(_analyze("lakeformation_grants"), _analyze("iam_access"),
                         _tool("lakeformation_access_graph"), _tool("lakeformation_matrix"),
                         _tool("lakeformation_architect")),
        signals=SignalsSpec(keywords=("lake formation", "lakeformation", "iam", "fgac"),
                            file_globs=_artifacts("lakeformation") + _artifacts("iam_access")),
        bindings={_analyze("lakeformation_grants"): _path(_artifacts("lakeformation")),
                  _analyze("iam_access"): _path(_artifacts("iam_access"))},
        unbound={_tool("lakeformation_access_graph"): FACTS_INPUT,
                 _tool("lakeformation_matrix"): ("answers from the Spark Forge's own version "
                                                 "matrix; it takes no workspace file"),
                 _tool("lakeformation_architect"): ("takes the architecture declaration as a "
                                                    "JSON argument, not a workspace file")},
    ),
    CapabilitySpec(
        id="cloudwatch.analysis",
        description="Collected CloudWatch metrics and job run logs (already redacted).",
        actions=_actions(_analyze("cloudwatch"), _analyze("cloudwatch_logs"),
                         _analyze("error_signatures")),
        signals=SignalsSpec(keywords=("cloudwatch", "cloudwatch logs"),
                            file_globs=_artifacts("cloudwatch") + _artifacts("cloudwatch_logs")),
        bindings={_analyze("cloudwatch"): _path(_artifacts("cloudwatch")),
                  _analyze("cloudwatch_logs"): _path(_artifacts("cloudwatch_logs"))},
        unbound={_analyze("error_signatures"): FACTS_INPUT},
    ),
    CapabilitySpec(
        id="platform.graph-analysis",
        description=("Declared platform inventories: dbt artifacts and the table consumers "
                     "inventory."),
        actions=_actions(_analyze("platform_graph"), _analyze("platform_ecosystem"),
                         _analyze("lakehouse_catalog"), _analyze("dbt_artifacts"),
                         _analyze("duckdb_microscope"), _analyze("forge_lab"),
                         _analyze("s3_listing"), _analyze("consumers")),
        signals=SignalsSpec(keywords=("dbt", "lineage", "consumers", "metadata graph"),
                            file_globs=DBT_GLOBS + CONSUMERS_GLOBS,
                            dependencies=("dbt-core",)),
        bindings={_analyze("dbt_artifacts"): _path(DBT_GLOBS),
                  _analyze("consumers"): _path(CONSUMERS_GLOBS)},
        unbound={_analyze("platform_graph"): NO_CONVENTION,
                 _analyze("platform_ecosystem"): NO_CONVENTION,
                 _analyze("lakehouse_catalog"): NO_CONVENTION,
                 _analyze("duckdb_microscope"): NO_CONVENTION,
                 _analyze("forge_lab"): NO_CONVENTION,
                 _analyze("s3_listing"): NO_CONVENTION},
    ),
    CapabilitySpec(
        id="migration.assessment",
        description="Release and migration assessment from the Spark Forge's version matrices.",
        actions=_actions(_tool("migration_assess"), _tool("release_describe"),
                         _tool("release_diff"), _tool("controlm_describe")),
        signals=SignalsSpec(keywords=("migration", "release", "upgrade")),
        unbound={_tool("migration_assess"): ("requires the source and target releases, which "
                                             "no ExecuteRequest v1 field carries"),
                 _tool("release_describe"): ("requires the platform and release, which no "
                                             "ExecuteRequest v1 field carries"),
                 _tool("release_diff"): ("requires two platform/release pairs, which no "
                                         "ExecuteRequest v1 field carries"),
                 _tool("controlm_describe"): ("requires the Control-M version, which no "
                                              "ExecuteRequest v1 field carries")},
    ),
    CapabilitySpec(
        id="finops.performance-analysis",
        description="Declared workload inventory: SLA and primary source of each job.",
        actions=_actions(_tool("benchmark"), _tool("workload"), _analyze("workload"),
                         _tool("capacity"), _tool("finops"), _tool("tune"), _tool("gain"),
                         _tool("simulate"), _tool("economy_report"),
                         renamed={_tool("workload"): "workload-profile"}),
        signals=SignalsSpec(keywords=("finops", "workload", "sla", "capacity"),
                            file_globs=WORKLOAD_GLOBS),
        bindings={_analyze("workload"): _path(WORKLOAD_GLOBS, directory=False)},
        unbound={_tool("benchmark"): ("compares the facts of two runs ('before_path' and "
                                      "'after_path'); one workspace holds only one state"),
                 _tool("workload"): FACTS_INPUT,
                 _tool("capacity"): FACTS_INPUT, _tool("finops"): FACTS_INPUT,
                 _tool("tune"): FACTS_INPUT, _tool("gain"): FACTS_INPUT,
                 _tool("simulate"): FACTS_INPUT,
                 _tool("economy_report"): ("reads the Spark Forge run ledger by 'run_id', not "
                                           "workspace files")},
    ),
)

# Read-only, offline native tools outside the capability table: (patterns, reason).
UNCATALOGUED: tuple[tuple[tuple[str, ...], str], ...] = (
    ((_tool("doctor"),), "probes the AWS credential chain and the host environment"),
    ((_tool("collect_verify"),),
     "operates on AWS collection artifacts registered in the local collection manifest"),
    ((_tool("judge"), _tool("fuse"), _tool("rules_lookup"), _tool("validate_output"),
      _tool("root_cause")),
     "consumed internally by the analysis actions or takes no workspace file input"),
    ((_tool("case_*"), _tool("change_*"), _tool("debate_*"), _tool("decision_*"),
      _tool("next_step"), _tool("playbook"), _tool("proof"), _tool("receipt_*"),
      _tool("report_*"), _tool("resume"), _tool("runtime_detect"), _tool("sdd_*")),
     "works on Spark Forge case, report or session state, not on workspace inputs"),
    ((_tool("context_*"), _tool("knowledge_*"), _tool("pack_list"), _tool("policy_explain"),
      _tool("telemetry_export")),
     "host and agent plumbing (context gateway, knowledge, packs, policy, telemetry), not an "
     "analysis"),
)
OPEN_WORLD_REASON = ("call AWS APIs over the network and write collection artifacts "
                     "(openWorldHint)")
WRITER_REASON = ("write local Spark Forge state (case, debate, receipts, sandbox, code index) "
                 "into the repository (readOnlyHint false)")


@dataclass(frozen=True)
class Exposure:
    """What ``derive`` declares: manifest capabilities and the not-exposed limitations."""

    capabilities: list[dict[str, Any]]
    limitations: list[str]


def spec(capability_id: str) -> CapabilitySpec | None:
    """The table entry of a capability id."""
    return next((item for item in CAPABILITIES if item.id == capability_id), None)


def tool_for(capability_id: str, action: str) -> str | None:
    """The native tool behind ``capability_id``/``action``."""
    entry = spec(capability_id)
    if entry is None:
        return None
    return next((tool for name, tool in entry.actions if name == action), None)


def load_snapshot(path: Path = SNAPSHOT_PATH) -> dict[str, Any] | str:
    """The recorded snapshot, or why it cannot be used."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return f"tool snapshot {path.name} is missing or not valid JSON"
    tools = data.get("tools") if isinstance(data, dict) else None
    if (not isinstance(data, dict) or not isinstance(data.get("specialist_version"), str)
            or not isinstance(data.get("recorded_at"), str) or not isinstance(tools, dict)):
        return f"tool snapshot {path.name} lacks specialist_version, recorded_at or tools"
    for name, entry in tools.items():
        if (not isinstance(entry, dict) or not isinstance(entry.get("annotations"), dict)
                or not isinstance(entry.get("required"), list)
                or not all(isinstance(arg, str) for arg in entry["required"])):
            return f"tool snapshot {path.name}: malformed entry for {name!r}"
    return data


def _hint(entry: Mapping[str, Any], name: str) -> object:
    annotations = entry.get("annotations")
    return annotations.get(name) if isinstance(annotations, Mapping) else None


def exclusion(tool: str, binding: ArgBinding | None, unbound: str | None,
              snapshot: Mapping[str, Any]) -> str | None:
    """Why a catalogued tool cannot be declared, or None when it can."""
    tools: Mapping[str, Any] = snapshot["tools"]
    entry = tools.get(tool)
    if not isinstance(entry, Mapping):
        return (f"not in the recorded Spark Forge {snapshot['specialist_version']} tool "
                "surface")
    if _hint(entry, "readOnlyHint") is not True:
        return "writes local state (readOnlyHint is not true)"
    if _hint(entry, "openWorldHint") is not False:
        return "may reach the network or AWS (openWorldHint is not false)"
    if binding is None:
        return unbound or "no binding fills its arguments from workspace files"
    missing = [arg for arg in entry.get("required") or () if arg != binding.arg]
    if missing:
        names = ", ".join(repr(arg) for arg in missing)
        return f"required argument(s) {names} cannot be filled from workspace files"
    return None


def _capability(entry: CapabilitySpec, actions: Sequence[str]) -> dict[str, Any]:
    return {
        "id": entry.id,
        "actions": list(actions),
        "default_action": actions[0],
        "state": STATE,
        "operation_class": OPERATION_CLASS,
        "description": entry.description,
        "signals": {"keywords": list(entry.signals.keywords),
                    "file_globs": list(entry.signals.file_globs),
                    "dependencies": list(entry.signals.dependencies)},
    }


def _group(tools: Sequence[str], reason: str) -> str:
    return f"not exposed: {', '.join(tools)}: {reason}"


def _uncatalogued(tools: Mapping[str, Any], catalogued: set[str]) -> list[str]:
    """Limitations for the native tools outside the table, grouped by reason."""
    groups: dict[str, list[str]] = {}
    for tool in sorted(set(tools) - catalogued):
        entry = tools[tool]
        if _hint(entry, "openWorldHint") is not False:
            reason = OPEN_WORLD_REASON
        elif _hint(entry, "readOnlyHint") is not True:
            reason = WRITER_REASON
        else:
            reason = next((why for patterns, why in UNCATALOGUED
                           if any(fnmatch.fnmatchcase(tool, p) for p in patterns)),
                          UNMAPPED_REASON)
        groups.setdefault(reason, []).append(tool)
    order = [OPEN_WORLD_REASON, WRITER_REASON, *(why for _, why in UNCATALOGUED),
             UNMAPPED_REASON]
    return [_group(groups[reason], reason) for reason in order if reason in groups]


def derive(snapshot: Mapping[str, Any]) -> Exposure:
    """Manifest capabilities and limitations from the table and a recorded snapshot."""
    tools: Mapping[str, Any] = snapshot["tools"]
    capabilities: list[dict[str, Any]] = []
    limitations = [f"capabilities derived from the recorded Spark Forge "
                   f"{snapshot['specialist_version']} tool surface (native_catalog.json, "
                   f"recorded {snapshot['recorded_at']})"]
    catalogued: set[str] = set()
    for entry in CAPABILITIES:
        declared: list[str] = []
        for action, tool in entry.actions:
            catalogued.add(tool)
            reason = exclusion(tool, entry.bindings.get(tool), entry.unbound.get(tool),
                               snapshot)
            if reason is None:
                declared.append(action)
            else:
                limitations.append(f"action '{action}' of '{entry.id}' not exposed "
                                   f"({tool}): {reason}")
        if declared:
            capabilities.append(_capability(entry, declared))
        else:
            limitations.append(f"capability '{entry.id}' not exposed: no action is "
                               "read-only, offline and fillable from workspace files")
    limitations.extend(_uncatalogued(tools, catalogued))
    return Exposure(capabilities=capabilities, limitations=limitations)
