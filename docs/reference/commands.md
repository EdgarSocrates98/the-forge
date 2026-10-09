# `theforge` command reference

Generated from the real CLI parser by `doc_inventory.py` + `doc_reference.py`. Do not hand-edit generated sections — write between `keep:start`/`keep:end` markers. Status vocabulary: `available` unless marked otherwise.

## Groups

- [`agents`](#agents) — 3 command(s)
- [`ask`](#ask) — 1 command(s)
- [`capabilities`](#capabilities) — 5 command(s)
- [`decisions`](#decisions) — 1 command(s)
- [`doctor`](#doctor) — 1 command(s)
- [`economy`](#economy) — 3 command(s)
- [`explain`](#explain) — 1 command(s)
- [`graph`](#graph) — 1 command(s)
- [`hosts`](#hosts) — 4 command(s)
- [`init`](#init) — 1 command(s)
- [`install`](#install) — 10 command(s)
- [`installations`](#installations) — 2 command(s)
- [`knowledge`](#knowledge) — 4 command(s)
- [`memory`](#memory) — 7 command(s)
- [`plan`](#plan) — 1 command(s)
- [`provider`](#provider) — 3 command(s)
- [`providers`](#providers) — 2 command(s)
- [`registry`](#registry) — 5 command(s)
- [`remote`](#remote) — 3 command(s)
- [`replay`](#replay) — 1 command(s)
- [`resume`](#resume) — 1 command(s)
- [`specialists`](#specialists) — 4 command(s)
- [`status`](#status) — 1 command(s)
- [`targets`](#targets) — 3 command(s)
- [`task`](#task) — 4 command(s)
- [`trace`](#trace) — 1 command(s)
- [`workspace`](#workspace) — 2 command(s)

## agents

### `agents`

**Syntax**

```text
theforge agents [help]
```

| argument/flag | required | default | description |
|---|---|---|---|
| `help` | no | — | show this help message and exit |

<!-- keep:start -->
_free notes — errors, examples, next steps (hand-written, preserved)_
<!-- keep:end -->

### `agents list`

**Syntax**

```text
theforge agents list [help] [root] [json] [debug]
```

| argument/flag | required | default | description |
|---|---|---|---|
| `help` | no | — | show this help message and exit |
| `root` | no | — | workspace root (default: current dir) |
| `json` | no | — | machine-readable JSON output |
| `debug` | no | — | on error, print the redacted diagnostic (never a traceback) |

<!-- keep:start -->
_free notes — errors, examples, next steps (hand-written, preserved)_
<!-- keep:end -->

### `agents show`

**Syntax**

```text
theforge agents show [help] [root] [json] [debug] <agent_id>
```

| argument/flag | required | default | description |
|---|---|---|---|
| `help` | no | — | show this help message and exit |
| `root` | no | — | workspace root (default: current dir) |
| `json` | no | — | machine-readable JSON output |
| `debug` | no | — | on error, print the redacted diagnostic (never a traceback) |
| `agent_id` | yes | — | — |

<!-- keep:start -->
_free notes — errors, examples, next steps (hand-written, preserved)_
<!-- keep:end -->

## ask

### `ask`

**Syntax**

```text
theforge ask [help] [root] [json] [debug] <intent> [capability] [action] [REQ_JSON] [PROVIDER] [profile] [targets] [allow_unverified] [CAPABILITY]
```

| argument/flag | required | default | description |
|---|---|---|---|
| `help` | no | — | show this help message and exit |
| `root` | no | — | workspace root (default: current dir) |
| `json` | no | — | machine-readable JSON output |
| `debug` | no | — | on error, print the redacted diagnostic (never a traceback) |
| `intent` | yes | — | — |
| `capability` | no | — | — |
| `action` | no | — | — |
| `REQ_JSON` | no | — | CapabilityRequirement/v1 JSON: negotiate provider fit (see docs/capability-negotiation.md) |
| `PROVIDER` | no | — | pin a provider (policy/protocol gates still apply) |
| `profile` | no | — | budget profile; auto lets the complexity engine decide |
| `targets` | no | — | — |
| `allow_unverified` | no | — | — |
| `CAPABILITY` | no | — | approve a capability the policy would ask about (repeatable) |

<!-- keep:start -->
_free notes — errors, examples, next steps (hand-written, preserved)_
<!-- keep:end -->

## capabilities

### `capabilities`

**Syntax**

```text
theforge capabilities [help]
```

| argument/flag | required | default | description |
|---|---|---|---|
| `help` | no | — | show this help message and exit |

<!-- keep:start -->
_free notes — errors, examples, next steps (hand-written, preserved)_
<!-- keep:end -->

### `capabilities discover`

**Syntax**

```text
theforge capabilities discover [help] [root] [json] [debug] [REQ_JSON] [CAP] [remote] [profile]
```

| argument/flag | required | default | description |
|---|---|---|---|
| `help` | no | — | show this help message and exit |
| `root` | no | — | workspace root (default: current dir) |
| `json` | no | — | machine-readable JSON output |
| `debug` | no | — | on error, print the redacted diagnostic (never a traceback) |
| `REQ_JSON` | no | — | a theforge/CapabilityRequirement/v1 JSON document |
| `CAP` | no | — | shortcut: minimal requirement for a capability id |
| `remote` | no | — | consult remote sources even when a local provider fully satisfies the requirement |
| `profile` | no | — | how eagerly remote sources are consulted: economy only when no local capability exists, balanced when nothing fully satisfies the requirement (default), max always compares remote claims |

<!-- keep:start -->
_free notes — errors, examples, next steps (hand-written, preserved)_
<!-- keep:end -->

### `capabilities list`

**Syntax**

```text
theforge capabilities list [help] [root] [json] [debug] [provider]
```

| argument/flag | required | default | description |
|---|---|---|---|
| `help` | no | — | show this help message and exit |
| `root` | no | — | workspace root (default: current dir) |
| `json` | no | — | machine-readable JSON output |
| `debug` | no | — | on error, print the redacted diagnostic (never a traceback) |
| `provider` | no | — | — |

<!-- keep:start -->
_free notes — errors, examples, next steps (hand-written, preserved)_
<!-- keep:end -->

### `capabilities negotiate`

**Syntax**

```text
theforge capabilities negotiate [help] [root] [json] [debug] <REQ_JSON>
```

| argument/flag | required | default | description |
|---|---|---|---|
| `help` | no | — | show this help message and exit |
| `root` | no | — | workspace root (default: current dir) |
| `json` | no | — | machine-readable JSON output |
| `debug` | no | — | on error, print the redacted diagnostic (never a traceback) |
| `REQ_JSON` | yes | — | a theforge/CapabilityRequirement/v1 JSON document |

<!-- keep:start -->
_free notes — errors, examples, next steps (hand-written, preserved)_
<!-- keep:end -->

### `capabilities search`

**Syntax**

```text
theforge capabilities search [help] [root] [json] [debug] <query>
```

| argument/flag | required | default | description |
|---|---|---|---|
| `help` | no | — | show this help message and exit |
| `root` | no | — | workspace root (default: current dir) |
| `json` | no | — | machine-readable JSON output |
| `debug` | no | — | on error, print the redacted diagnostic (never a traceback) |
| `query` | yes | — | — |

<!-- keep:start -->
_free notes — errors, examples, next steps (hand-written, preserved)_
<!-- keep:end -->

## decisions

### `decisions`

**Syntax**

```text
theforge decisions [help] [root] [json] [debug]
```

| argument/flag | required | default | description |
|---|---|---|---|
| `help` | no | — | show this help message and exit |
| `root` | no | — | workspace root (default: current dir) |
| `json` | no | — | machine-readable JSON output |
| `debug` | no | — | on error, print the redacted diagnostic (never a traceback) |

<!-- keep:start -->
_free notes — errors, examples, next steps (hand-written, preserved)_
<!-- keep:end -->

## doctor

### `doctor`

**Syntax**

```text
theforge doctor [help] [root] [json] [debug]
```

| argument/flag | required | default | description |
|---|---|---|---|
| `help` | no | — | show this help message and exit |
| `root` | no | — | workspace root (default: current dir) |
| `json` | no | — | machine-readable JSON output |
| `debug` | no | — | on error, print the redacted diagnostic (never a traceback) |

<!-- keep:start -->
_free notes — errors, examples, next steps (hand-written, preserved)_
<!-- keep:end -->

## economy

### `economy`

**Syntax**

```text
theforge economy [help]
```

| argument/flag | required | default | description |
|---|---|---|---|
| `help` | no | — | show this help message and exit |

<!-- keep:start -->
_free notes — errors, examples, next steps (hand-written, preserved)_
<!-- keep:end -->

### `economy experiment`

**Syntax**

```text
theforge economy experiment [help] [root] [json] [debug] <EXPERIMENT_JSON>
```

| argument/flag | required | default | description |
|---|---|---|---|
| `help` | no | — | show this help message and exit |
| `root` | no | — | workspace root (default: current dir) |
| `json` | no | — | machine-readable JSON output |
| `debug` | no | — | on error, print the redacted diagnostic (never a traceback) |
| `EXPERIMENT_JSON` | yes | — | a theforge/StrategyExperiment/v1 JSON document |

<!-- keep:start -->
_free notes — errors, examples, next steps (hand-written, preserved)_
<!-- keep:end -->

### `economy report`

**Syntax**

```text
theforge economy report [help] [root] [json] [debug]
```

| argument/flag | required | default | description |
|---|---|---|---|
| `help` | no | — | show this help message and exit |
| `root` | no | — | workspace root (default: current dir) |
| `json` | no | — | machine-readable JSON output |
| `debug` | no | — | on error, print the redacted diagnostic (never a traceback) |

<!-- keep:start -->
_free notes — errors, examples, next steps (hand-written, preserved)_
<!-- keep:end -->

## explain

### `explain`

**Syntax**

```text
theforge explain [help] [root] [json] [debug] <run_id>
```

| argument/flag | required | default | description |
|---|---|---|---|
| `help` | no | — | show this help message and exit |
| `root` | no | — | workspace root (default: current dir) |
| `json` | no | — | machine-readable JSON output |
| `debug` | no | — | on error, print the redacted diagnostic (never a traceback) |
| `run_id` | yes | — | — |

<!-- keep:start -->
_free notes — errors, examples, next steps (hand-written, preserved)_
<!-- keep:end -->

## graph

### `graph`

**Syntax**

```text
theforge graph [help] [root] [json] [debug] [CAPABILITY] [mesh]
```

| argument/flag | required | default | description |
|---|---|---|---|
| `help` | no | — | show this help message and exit |
| `root` | no | — | workspace root (default: current dir) |
| `json` | no | — | machine-readable JSON output |
| `debug` | no | — | on error, print the redacted diagnostic (never a traceback) |
| `CAPABILITY` | no | — | only the edges touching this capability ('provider/capability' or a bare capability id) |
| `mesh` | no | — | the domain mesh projection: per domain, the observe/engineer/verify capabilities derived from declared produces/consumes/can_verify relations |

<!-- keep:start -->
_free notes — errors, examples, next steps (hand-written, preserved)_
<!-- keep:end -->

## hosts

### `hosts`

**Syntax**

```text
theforge hosts [help]
```

| argument/flag | required | default | description |
|---|---|---|---|
| `help` | no | — | show this help message and exit |

<!-- keep:start -->
_free notes — errors, examples, next steps (hand-written, preserved)_
<!-- keep:end -->

### `hosts activate`

**Syntax**

```text
theforge hosts activate [help] [root] [json] [debug] <host> [scope]
```

| argument/flag | required | default | description |
|---|---|---|---|
| `help` | no | — | show this help message and exit |
| `root` | no | — | workspace root (default: current dir) |
| `json` | no | — | machine-readable JSON output |
| `debug` | no | — | on error, print the redacted diagnostic (never a traceback) |
| `host` | yes | — | — |
| `scope` | no | — | — |

<!-- keep:start -->
_free notes — errors, examples, next steps (hand-written, preserved)_
<!-- keep:end -->

### `hosts list`

**Syntax**

```text
theforge hosts list [help] [root] [json] [debug]
```

| argument/flag | required | default | description |
|---|---|---|---|
| `help` | no | — | show this help message and exit |
| `root` | no | — | workspace root (default: current dir) |
| `json` | no | — | machine-readable JSON output |
| `debug` | no | — | on error, print the redacted diagnostic (never a traceback) |

<!-- keep:start -->
_free notes — errors, examples, next steps (hand-written, preserved)_
<!-- keep:end -->

### `hosts status`

**Syntax**

```text
theforge hosts status [help] [root] [json] [debug]
```

| argument/flag | required | default | description |
|---|---|---|---|
| `help` | no | — | show this help message and exit |
| `root` | no | — | workspace root (default: current dir) |
| `json` | no | — | machine-readable JSON output |
| `debug` | no | — | on error, print the redacted diagnostic (never a traceback) |

<!-- keep:start -->
_free notes — errors, examples, next steps (hand-written, preserved)_
<!-- keep:end -->

## init

### `init`

**Syntax**

```text
theforge init [help] [root] [json] [debug]
```

| argument/flag | required | default | description |
|---|---|---|---|
| `help` | no | — | show this help message and exit |
| `root` | no | — | workspace root (default: current dir) |
| `json` | no | — | machine-readable JSON output |
| `debug` | no | — | on error, print the redacted diagnostic (never a traceback) |

<!-- keep:start -->
_free notes — errors, examples, next steps (hand-written, preserved)_
<!-- keep:end -->

## install

### `install`

**Syntax**

```text
theforge install [help]
```

| argument/flag | required | default | description |
|---|---|---|---|
| `help` | no | — | show this help message and exit |

<!-- keep:start -->
_free notes — errors, examples, next steps (hand-written, preserved)_
<!-- keep:end -->

### `install apply`

**Syntax**

```text
theforge install apply [help] [root] [json] [debug] [scope] [yes] [host] [profile] [dry_run]
```

| argument/flag | required | default | description |
|---|---|---|---|
| `help` | no | — | show this help message and exit |
| `root` | no | — | workspace root (default: current dir) |
| `json` | no | — | machine-readable JSON output |
| `debug` | no | — | on error, print the redacted diagnostic (never a traceback) |
| `scope` | no | — | — |
| `yes` | no | — | explicit approval — required for any write |
| `host` | no | — | — |
| `profile` | no | — | — |
| `dry_run` | no | — | — |

<!-- keep:start -->
_free notes — errors, examples, next steps (hand-written, preserved)_
<!-- keep:end -->

### `install auto`

**Syntax**

```text
theforge install auto [help] [root] [json] [debug] [scope] [yes] [forge] [RELPATH] [dry_run]
```

| argument/flag | required | default | description |
|---|---|---|---|
| `help` | no | — | show this help message and exit |
| `root` | no | — | workspace root (default: current dir) |
| `json` | no | — | machine-readable JSON output |
| `debug` | no | — | on error, print the redacted diagnostic (never a traceback) |
| `scope` | no | — | — |
| `yes` | no | — | explicit approval — required for any write |
| `forge` | no | — | limit delegation to one registered forge id |
| `RELPATH` | no | — | workspace scope: also delegate a project install into this member repo (repeatable) |
| `dry_run` | no | — | — |

<!-- keep:start -->
_free notes — errors, examples, next steps (hand-written, preserved)_
<!-- keep:end -->

### `install doctor`

**Syntax**

```text
theforge install doctor [help] [root] [json] [debug] [scope]
```

| argument/flag | required | default | description |
|---|---|---|---|
| `help` | no | — | show this help message and exit |
| `root` | no | — | workspace root (default: current dir) |
| `json` | no | — | machine-readable JSON output |
| `debug` | no | — | on error, print the redacted diagnostic (never a traceback) |
| `scope` | no | — | — |

<!-- keep:start -->
_free notes — errors, examples, next steps (hand-written, preserved)_
<!-- keep:end -->

### `install mcp-verify`

**Syntax**

```text
theforge install mcp-verify [help] [root] [json] [debug]
```

| argument/flag | required | default | description |
|---|---|---|---|
| `help` | no | — | show this help message and exit |
| `root` | no | — | workspace root (default: current dir) |
| `json` | no | — | machine-readable JSON output |
| `debug` | no | — | on error, print the redacted diagnostic (never a traceback) |

<!-- keep:start -->
_free notes — errors, examples, next steps (hand-written, preserved)_
<!-- keep:end -->

### `install plan`

**Syntax**

```text
theforge install plan [help] [root] [json] [debug] <provider> <version> <source> [approve]
```

| argument/flag | required | default | description |
|---|---|---|---|
| `help` | no | — | show this help message and exit |
| `root` | no | — | workspace root (default: current dir) |
| `json` | no | — | machine-readable JSON output |
| `debug` | no | — | on error, print the redacted diagnostic (never a traceback) |
| `provider` | yes | — | — |
| `version` | yes | — | pinned SemVer — never 'latest' |
| `source` | yes | — | registry source id from registries.toml |
| `approve` | no | — | record the approval gate as granted (plan still does not execute) |

<!-- keep:start -->
_free notes — errors, examples, next steps (hand-written, preserved)_
<!-- keep:end -->

### `install repair`

**Syntax**

```text
theforge install repair [help] [root] [json] [debug] [scope] [dry_run]
```

| argument/flag | required | default | description |
|---|---|---|---|
| `help` | no | — | show this help message and exit |
| `root` | no | — | workspace root (default: current dir) |
| `json` | no | — | machine-readable JSON output |
| `debug` | no | — | on error, print the redacted diagnostic (never a traceback) |
| `scope` | no | — | — |
| `dry_run` | no | — | — |

<!-- keep:start -->
_free notes — errors, examples, next steps (hand-written, preserved)_
<!-- keep:end -->

### `install status`

**Syntax**

```text
theforge install status [help] [root] [json] [debug] [scope]
```

| argument/flag | required | default | description |
|---|---|---|---|
| `help` | no | — | show this help message and exit |
| `root` | no | — | workspace root (default: current dir) |
| `json` | no | — | machine-readable JSON output |
| `debug` | no | — | on error, print the redacted diagnostic (never a traceback) |
| `scope` | no | — | — |

<!-- keep:start -->
_free notes — errors, examples, next steps (hand-written, preserved)_
<!-- keep:end -->

### `install uninstall`

**Syntax**

```text
theforge install uninstall [help] [root] [json] [debug] [scope] [dry_run] [purge]
```

| argument/flag | required | default | description |
|---|---|---|---|
| `help` | no | — | show this help message and exit |
| `root` | no | — | workspace root (default: current dir) |
| `json` | no | — | machine-readable JSON output |
| `debug` | no | — | on error, print the redacted diagnostic (never a traceback) |
| `scope` | no | — | — |
| `dry_run` | no | — | — |
| `purge` | no | — | also delete .forge/install state |

<!-- keep:start -->
_free notes — errors, examples, next steps (hand-written, preserved)_
<!-- keep:end -->

### `install update`

**Syntax**

```text
theforge install update [help] [root] [json] [debug] [dry_run] [to] [repo]
```

| argument/flag | required | default | description |
|---|---|---|---|
| `help` | no | — | show this help message and exit |
| `root` | no | — | workspace root (default: current dir) |
| `json` | no | — | machine-readable JSON output |
| `debug` | no | — | on error, print the redacted diagnostic (never a traceback) |
| `dry_run` | no | — | — |
| `to` | no | — | pinned version — never 'latest' |
| `repo` | no | — | — |

<!-- keep:start -->
_free notes — errors, examples, next steps (hand-written, preserved)_
<!-- keep:end -->

## installations

### `installations`

**Syntax**

```text
theforge installations [help]
```

| argument/flag | required | default | description |
|---|---|---|---|
| `help` | no | — | show this help message and exit |

<!-- keep:start -->
_free notes — errors, examples, next steps (hand-written, preserved)_
<!-- keep:end -->

### `installations list`

**Syntax**

```text
theforge installations list [help] [root] [json] [debug]
```

| argument/flag | required | default | description |
|---|---|---|---|
| `help` | no | — | show this help message and exit |
| `root` | no | — | workspace root (default: current dir) |
| `json` | no | — | machine-readable JSON output |
| `debug` | no | — | on error, print the redacted diagnostic (never a traceback) |

<!-- keep:start -->
_free notes — errors, examples, next steps (hand-written, preserved)_
<!-- keep:end -->

## knowledge

### `knowledge`

**Syntax**

```text
theforge knowledge [help]
```

| argument/flag | required | default | description |
|---|---|---|---|
| `help` | no | — | show this help message and exit |

<!-- keep:start -->
_free notes — errors, examples, next steps (hand-written, preserved)_
<!-- keep:end -->

### `knowledge check`

**Syntax**

```text
theforge knowledge check [help] [root] [json] [debug]
```

| argument/flag | required | default | description |
|---|---|---|---|
| `help` | no | — | show this help message and exit |
| `root` | no | — | workspace root (default: current dir) |
| `json` | no | — | machine-readable JSON output |
| `debug` | no | — | on error, print the redacted diagnostic (never a traceback) |

<!-- keep:start -->
_free notes — errors, examples, next steps (hand-written, preserved)_
<!-- keep:end -->

### `knowledge list`

**Syntax**

```text
theforge knowledge list [help] [root] [json] [debug]
```

| argument/flag | required | default | description |
|---|---|---|---|
| `help` | no | — | show this help message and exit |
| `root` | no | — | workspace root (default: current dir) |
| `json` | no | — | machine-readable JSON output |
| `debug` | no | — | on error, print the redacted diagnostic (never a traceback) |

<!-- keep:start -->
_free notes — errors, examples, next steps (hand-written, preserved)_
<!-- keep:end -->

### `knowledge show`

**Syntax**

```text
theforge knowledge show [help] [root] [json] [debug] <provider_id>
```

| argument/flag | required | default | description |
|---|---|---|---|
| `help` | no | — | show this help message and exit |
| `root` | no | — | workspace root (default: current dir) |
| `json` | no | — | machine-readable JSON output |
| `debug` | no | — | on error, print the redacted diagnostic (never a traceback) |
| `provider_id` | yes | — | — |

<!-- keep:start -->
_free notes — errors, examples, next steps (hand-written, preserved)_
<!-- keep:end -->

## memory

### `memory`

**Syntax**

```text
theforge memory [help]
```

| argument/flag | required | default | description |
|---|---|---|---|
| `help` | no | — | show this help message and exit |

<!-- keep:start -->
_free notes — errors, examples, next steps (hand-written, preserved)_
<!-- keep:end -->

### `memory export`

**Syntax**

```text
theforge memory export [help] [root] [json] [debug]
```

| argument/flag | required | default | description |
|---|---|---|---|
| `help` | no | — | show this help message and exit |
| `root` | no | — | workspace root (default: current dir) |
| `json` | no | — | machine-readable JSON output |
| `debug` | no | — | on error, print the redacted diagnostic (never a traceback) |

<!-- keep:start -->
_free notes — errors, examples, next steps (hand-written, preserved)_
<!-- keep:end -->

### `memory import`

**Syntax**

```text
theforge memory import [help] [root] [json] [debug] <file>
```

| argument/flag | required | default | description |
|---|---|---|---|
| `help` | no | — | show this help message and exit |
| `root` | no | — | workspace root (default: current dir) |
| `json` | no | — | machine-readable JSON output |
| `debug` | no | — | on error, print the redacted diagnostic (never a traceback) |
| `file` | yes | — | JSON entry list or memory pack ('-' reads stdin) |

<!-- keep:start -->
_free notes — errors, examples, next steps (hand-written, preserved)_
<!-- keep:end -->

### `memory learn`

**Syntax**

```text
theforge memory learn [help] [root] [json] [debug] <run_id>
```

| argument/flag | required | default | description |
|---|---|---|---|
| `help` | no | — | show this help message and exit |
| `root` | no | — | workspace root (default: current dir) |
| `json` | no | — | machine-readable JSON output |
| `debug` | no | — | on error, print the redacted diagnostic (never a traceback) |
| `run_id` | yes | — | — |

<!-- keep:start -->
_free notes — errors, examples, next steps (hand-written, preserved)_
<!-- keep:end -->

### `memory list`

**Syntax**

```text
theforge memory list [help] [root] [json] [debug] [kind] [provider] [capability] [task_family] [surface] [subject] [tag] [epistemic] [all] [max_entries] [max_bytes]
```

| argument/flag | required | default | description |
|---|---|---|---|
| `help` | no | — | show this help message and exit |
| `root` | no | — | workspace root (default: current dir) |
| `json` | no | — | machine-readable JSON output |
| `debug` | no | — | on error, print the redacted diagnostic (never a traceback) |
| `kind` | no | — | — |
| `provider` | no | — | — |
| `capability` | no | — | — |
| `task_family` | no | — | — |
| `surface` | no | — | — |
| `subject` | no | — | — |
| `tag` | no | — | — |
| `epistemic` | no | — | — |
| `all` | no | — | include stale/superseded entries |
| `max_entries` | no | — | — |
| `max_bytes` | no | — | — |

<!-- keep:start -->
_free notes — errors, examples, next steps (hand-written, preserved)_
<!-- keep:end -->

### `memory patterns`

**Syntax**

```text
theforge memory patterns [help] [root] [json] [debug]
```

| argument/flag | required | default | description |
|---|---|---|---|
| `help` | no | — | show this help message and exit |
| `root` | no | — | workspace root (default: current dir) |
| `json` | no | — | machine-readable JSON output |
| `debug` | no | — | on error, print the redacted diagnostic (never a traceback) |

<!-- keep:start -->
_free notes — errors, examples, next steps (hand-written, preserved)_
<!-- keep:end -->

### `memory summarize`

**Syntax**

```text
theforge memory summarize [help] [root] [json] [debug] <subject> <claim> <ENTRY_ID> [coverage]
```

| argument/flag | required | default | description |
|---|---|---|---|
| `help` | no | — | show this help message and exit |
| `root` | no | — | workspace root (default: current dir) |
| `json` | no | — | machine-readable JSON output |
| `debug` | no | — | on error, print the redacted diagnostic (never a traceback) |
| `subject` | yes | — | — |
| `claim` | yes | — | the distilled statement |
| `ENTRY_ID` | yes | — | source entry id (repeatable) |
| `coverage` | no | — | — |

<!-- keep:start -->
_free notes — errors, examples, next steps (hand-written, preserved)_
<!-- keep:end -->

## plan

### `plan`

Plan a task across providers, one node per specialist, executed locally in sequence.

Without --from FILE the nodes are ordered by declared capability relations first (rule
`capability-graph`: requires and produces→consumes among qualified providers) and then by
the textual order of their keywords in the intent (rule `intent-order`): proxies of the
data flow that can infer a wrong dependency (e.g. "an API that consumes the Spark pipeline
data" puts the API first). Review the plan without --execute; --from FILE fixes the order
explicitly. An ambiguous decomposition may be resolved by a `proposes_plans` provider
(semantic tier), revalidated by the deterministic plan checks.

**Syntax**

```text
theforge plan [help] [root] [json] [debug] <intent> [profile] [targets] [REQ_JSON] [FILE] [execute] [allow_unverified] [CAPABILITY]
```

| argument/flag | required | default | description |
|---|---|---|---|
| `help` | no | — | show this help message and exit |
| `root` | no | — | workspace root (default: current dir) |
| `json` | no | — | machine-readable JSON output |
| `debug` | no | — | on error, print the redacted diagnostic (never a traceback) |
| `intent` | yes | — | — |
| `profile` | no | — | budget profile; auto lets the complexity engine decide |
| `targets` | no | — | — |
| `REQ_JSON` | no | — | CapabilityRequirement/v1 JSON: negotiate provider fit for the demanded capability |
| `FILE` | no | — | explicit plan file (fixes the node order); default: decompose the intent |
| `execute` | no | — | execute the nodes (default: plan only, outcome `planned`) |
| `allow_unverified` | no | — | — |
| `CAPABILITY` | no | — | approve a capability for the nodes that use it (repeatable) |

<!-- keep:start -->
_free notes — errors, examples, next steps (hand-written, preserved)_
<!-- keep:end -->

## provider

### `provider`

**Syntax**

```text
theforge provider [help]
```

| argument/flag | required | default | description |
|---|---|---|---|
| `help` | no | — | show this help message and exit |

<!-- keep:start -->
_free notes — errors, examples, next steps (hand-written, preserved)_
<!-- keep:end -->

### `provider check`

**Syntax**

```text
theforge provider check [help] [root] [json] [debug] [ARGV]
```

| argument/flag | required | default | description |
|---|---|---|---|
| `help` | no | — | show this help message and exit |
| `root` | no | — | workspace root (default: current dir) |
| `json` | no | — | machine-readable JSON output |
| `debug` | no | — | on error, print the redacted diagnostic (never a traceback) |
| `ARGV` | no | — | the provider argv (prefix with -- when it starts with a dash) |

<!-- keep:start -->
_free notes — errors, examples, next steps (hand-written, preserved)_
<!-- keep:end -->

### `provider init`

**Syntax**

```text
theforge provider init [help] [root] [json] [debug] <directory> <PROVIDER_ID> [CAPABILITY_ID]
```

| argument/flag | required | default | description |
|---|---|---|---|
| `help` | no | — | show this help message and exit |
| `root` | no | — | workspace root (default: current dir) |
| `json` | no | — | machine-readable JSON output |
| `debug` | no | — | on error, print the redacted diagnostic (never a traceback) |
| `directory` | yes | — | target directory (new or empty) |
| `PROVIDER_ID` | yes | — | the provider id the manifest will declare |
| `CAPABILITY_ID` | no | — | first capability id (default: <id-prefix>.describe) |

<!-- keep:start -->
_free notes — errors, examples, next steps (hand-written, preserved)_
<!-- keep:end -->

## providers

### `providers`

**Syntax**

```text
theforge providers [help]
```

| argument/flag | required | default | description |
|---|---|---|---|
| `help` | no | — | show this help message and exit |

<!-- keep:start -->
_free notes — errors, examples, next steps (hand-written, preserved)_
<!-- keep:end -->

### `providers health`

**Syntax**

```text
theforge providers health [help] [root] [json] [debug]
```

| argument/flag | required | default | description |
|---|---|---|---|
| `help` | no | — | show this help message and exit |
| `root` | no | — | workspace root (default: current dir) |
| `json` | no | — | machine-readable JSON output |
| `debug` | no | — | on error, print the redacted diagnostic (never a traceback) |

<!-- keep:start -->
_free notes — errors, examples, next steps (hand-written, preserved)_
<!-- keep:end -->

## registry

### `registry`

**Syntax**

```text
theforge registry [help]
```

| argument/flag | required | default | description |
|---|---|---|---|
| `help` | no | — | show this help message and exit |

<!-- keep:start -->
_free notes — errors, examples, next steps (hand-written, preserved)_
<!-- keep:end -->

### `registry list`

**Syntax**

```text
theforge registry list [help] [root] [json] [debug]
```

| argument/flag | required | default | description |
|---|---|---|---|
| `help` | no | — | show this help message and exit |
| `root` | no | — | workspace root (default: current dir) |
| `json` | no | — | machine-readable JSON output |
| `debug` | no | — | on error, print the redacted diagnostic (never a traceback) |

<!-- keep:start -->
_free notes — errors, examples, next steps (hand-written, preserved)_
<!-- keep:end -->

### `registry refresh`

**Syntax**

```text
theforge registry refresh [help] [root] [json] [debug]
```

| argument/flag | required | default | description |
|---|---|---|---|
| `help` | no | — | show this help message and exit |
| `root` | no | — | workspace root (default: current dir) |
| `json` | no | — | machine-readable JSON output |
| `debug` | no | — | on error, print the redacted diagnostic (never a traceback) |

<!-- keep:start -->
_free notes — errors, examples, next steps (hand-written, preserved)_
<!-- keep:end -->

### `registry show`

**Syntax**

```text
theforge registry show [help] [root] [json] [debug] <provider_id>
```

| argument/flag | required | default | description |
|---|---|---|---|
| `help` | no | — | show this help message and exit |
| `root` | no | — | workspace root (default: current dir) |
| `json` | no | — | machine-readable JSON output |
| `debug` | no | — | on error, print the redacted diagnostic (never a traceback) |
| `provider_id` | yes | — | — |

<!-- keep:start -->
_free notes — errors, examples, next steps (hand-written, preserved)_
<!-- keep:end -->

### `registry sources`

**Syntax**

```text
theforge registry sources [help] [root] [json] [debug]
```

| argument/flag | required | default | description |
|---|---|---|---|
| `help` | no | — | show this help message and exit |
| `root` | no | — | workspace root (default: current dir) |
| `json` | no | — | machine-readable JSON output |
| `debug` | no | — | on error, print the redacted diagnostic (never a traceback) |

<!-- keep:start -->
_free notes — errors, examples, next steps (hand-written, preserved)_
<!-- keep:end -->

## remote

### `remote`

**Syntax**

```text
theforge remote [help]
```

| argument/flag | required | default | description |
|---|---|---|---|
| `help` | no | — | show this help message and exit |

<!-- keep:start -->
_free notes — errors, examples, next steps (hand-written, preserved)_
<!-- keep:end -->

### `remote check`

**Syntax**

```text
theforge remote check [help] [root] [json] [debug] [data_classification] [locality] [network] [runtime] [region] [isolated]
```

| argument/flag | required | default | description |
|---|---|---|---|
| `help` | no | — | show this help message and exit |
| `root` | no | — | workspace root (default: current dir) |
| `json` | no | — | machine-readable JSON output |
| `debug` | no | — | on error, print the redacted diagnostic (never a traceback) |
| `data_classification` | no | — | — |
| `locality` | no | — | — |
| `network` | no | — | — |
| `runtime` | no | — | — |
| `region` | no | — | — |
| `isolated` | no | — | force locality 'isolated' |

<!-- keep:start -->
_free notes — errors, examples, next steps (hand-written, preserved)_
<!-- keep:end -->

### `remote policy`

**Syntax**

```text
theforge remote policy [help] [root] [json] [debug]
```

| argument/flag | required | default | description |
|---|---|---|---|
| `help` | no | — | show this help message and exit |
| `root` | no | — | workspace root (default: current dir) |
| `json` | no | — | machine-readable JSON output |
| `debug` | no | — | on error, print the redacted diagnostic (never a traceback) |

<!-- keep:start -->
_free notes — errors, examples, next steps (hand-written, preserved)_
<!-- keep:end -->

## replay

### `replay`

**Syntax**

```text
theforge replay [help] [root] [json] [debug] <run_id> <mode> [allow_unverified] [CAPABILITY]
```

| argument/flag | required | default | description |
|---|---|---|---|
| `help` | no | — | show this help message and exit |
| `root` | no | — | workspace root (default: current dir) |
| `json` | no | — | machine-readable JSON output |
| `debug` | no | — | on error, print the redacted diagnostic (never a traceback) |
| `run_id` | yes | — | — |
| `mode` | yes | — | — |
| `allow_unverified` | no | — | — |
| `CAPABILITY` | no | — | approve a capability for the re-execution (repeatable) |

<!-- keep:start -->
_free notes — errors, examples, next steps (hand-written, preserved)_
<!-- keep:end -->

## resume

### `resume`

**Syntax**

```text
theforge resume [help] [root] [json] [debug] <run_id> [allow_unverified] [CAPABILITY]
```

| argument/flag | required | default | description |
|---|---|---|---|
| `help` | no | — | show this help message and exit |
| `root` | no | — | workspace root (default: current dir) |
| `json` | no | — | machine-readable JSON output |
| `debug` | no | — | on error, print the redacted diagnostic (never a traceback) |
| `run_id` | yes | — | the plan run to resume |
| `allow_unverified` | no | — | — |
| `CAPABILITY` | no | — | approve a capability for the nodes that use it (repeatable) |

<!-- keep:start -->
_free notes — errors, examples, next steps (hand-written, preserved)_
<!-- keep:end -->

## specialists

### `specialists`

**Syntax**

```text
theforge specialists [help]
```

| argument/flag | required | default | description |
|---|---|---|---|
| `help` | no | — | show this help message and exit |

<!-- keep:start -->
_free notes — errors, examples, next steps (hand-written, preserved)_
<!-- keep:end -->

### `specialists doctor`

**Syntax**

```text
theforge specialists doctor [help] [root] [json] [debug]
```

| argument/flag | required | default | description |
|---|---|---|---|
| `help` | no | — | show this help message and exit |
| `root` | no | — | workspace root (default: current dir) |
| `json` | no | — | machine-readable JSON output |
| `debug` | no | — | on error, print the redacted diagnostic (never a traceback) |

<!-- keep:start -->
_free notes — errors, examples, next steps (hand-written, preserved)_
<!-- keep:end -->

### `specialists list`

**Syntax**

```text
theforge specialists list [help] [root] [json] [debug] [no_probe]
```

| argument/flag | required | default | description |
|---|---|---|---|
| `help` | no | — | show this help message and exit |
| `root` | no | — | workspace root (default: current dir) |
| `json` | no | — | machine-readable JSON output |
| `debug` | no | — | on error, print the redacted diagnostic (never a traceback) |
| `no_probe` | no | — | skip the CLI version probe |

<!-- keep:start -->
_free notes — errors, examples, next steps (hand-written, preserved)_
<!-- keep:end -->

### `specialists status`

**Syntax**

```text
theforge specialists status [help] [root] [json] [debug]
```

| argument/flag | required | default | description |
|---|---|---|---|
| `help` | no | — | show this help message and exit |
| `root` | no | — | workspace root (default: current dir) |
| `json` | no | — | machine-readable JSON output |
| `debug` | no | — | on error, print the redacted diagnostic (never a traceback) |

<!-- keep:start -->
_free notes — errors, examples, next steps (hand-written, preserved)_
<!-- keep:end -->

## status

### `status`

**Syntax**

```text
theforge status [help] [root] [json] [debug]
```

| argument/flag | required | default | description |
|---|---|---|---|
| `help` | no | — | show this help message and exit |
| `root` | no | — | workspace root (default: current dir) |
| `json` | no | — | machine-readable JSON output |
| `debug` | no | — | on error, print the redacted diagnostic (never a traceback) |

<!-- keep:start -->
_free notes — errors, examples, next steps (hand-written, preserved)_
<!-- keep:end -->

## targets

### `targets`

**Syntax**

```text
theforge targets [help]
```

| argument/flag | required | default | description |
|---|---|---|---|
| `help` | no | — | show this help message and exit |

<!-- keep:start -->
_free notes — errors, examples, next steps (hand-written, preserved)_
<!-- keep:end -->

### `targets list`

**Syntax**

```text
theforge targets list [help] [root] [json] [debug]
```

| argument/flag | required | default | description |
|---|---|---|---|
| `help` | no | — | show this help message and exit |
| `root` | no | — | workspace root (default: current dir) |
| `json` | no | — | machine-readable JSON output |
| `debug` | no | — | on error, print the redacted diagnostic (never a traceback) |

<!-- keep:start -->
_free notes — errors, examples, next steps (hand-written, preserved)_
<!-- keep:end -->

### `targets negotiate`

**Syntax**

```text
theforge targets negotiate [help] [root] [json] [debug] <provider> <capability> [data_classification] [locality] [network] [runtime] [region] [isolated]
```

| argument/flag | required | default | description |
|---|---|---|---|
| `help` | no | — | show this help message and exit |
| `root` | no | — | workspace root (default: current dir) |
| `json` | no | — | machine-readable JSON output |
| `debug` | no | — | on error, print the redacted diagnostic (never a traceback) |
| `provider` | yes | — | — |
| `capability` | yes | — | — |
| `data_classification` | no | — | — |
| `locality` | no | — | — |
| `network` | no | — | — |
| `runtime` | no | — | — |
| `region` | no | — | — |
| `isolated` | no | — | force locality 'isolated' |

<!-- keep:start -->
_free notes — errors, examples, next steps (hand-written, preserved)_
<!-- keep:end -->

## task

### `task`

**Syntax**

```text
theforge task [help]
```

| argument/flag | required | default | description |
|---|---|---|---|
| `help` | no | — | show this help message and exit |

<!-- keep:start -->
_free notes — errors, examples, next steps (hand-written, preserved)_
<!-- keep:end -->

### `task explain`

**Syntax**

```text
theforge task explain [help] [root] [json] [debug] <task_id>
```

| argument/flag | required | default | description |
|---|---|---|---|
| `help` | no | — | show this help message and exit |
| `root` | no | — | workspace root (default: current dir) |
| `json` | no | — | machine-readable JSON output |
| `debug` | no | — | on error, print the redacted diagnostic (never a traceback) |
| `task_id` | yes | — | — |

<!-- keep:start -->
_free notes — errors, examples, next steps (hand-written, preserved)_
<!-- keep:end -->

### `task plan`

**Syntax**

```text
theforge task plan [help] [root] [json] [debug] <intent> [target] [provider]
```

| argument/flag | required | default | description |
|---|---|---|---|
| `help` | no | — | show this help message and exit |
| `root` | no | — | workspace root (default: current dir) |
| `json` | no | — | machine-readable JSON output |
| `debug` | no | — | on error, print the redacted diagnostic (never a traceback) |
| `intent` | yes | — | — |
| `target` | no | — | path the specialist analyzes (default: root) |
| `provider` | no | — | pin one specialist |

<!-- keep:start -->
_free notes — errors, examples, next steps (hand-written, preserved)_
<!-- keep:end -->

### `task run`

**Syntax**

```text
theforge task run [help] [root] [json] [debug] <intent> [target] [provider] [max_parallel]
```

| argument/flag | required | default | description |
|---|---|---|---|
| `help` | no | — | show this help message and exit |
| `root` | no | — | workspace root (default: current dir) |
| `json` | no | — | machine-readable JSON output |
| `debug` | no | — | on error, print the redacted diagnostic (never a traceback) |
| `intent` | yes | — | — |
| `target` | no | — | path the specialist analyzes (default: root) |
| `provider` | no | — | pin one specialist |
| `max_parallel` | no | — | — |

<!-- keep:start -->
_free notes — errors, examples, next steps (hand-written, preserved)_
<!-- keep:end -->

## trace

### `trace`

**Syntax**

```text
theforge trace [help] [root] [json] [debug] <run_id>
```

| argument/flag | required | default | description |
|---|---|---|---|
| `help` | no | — | show this help message and exit |
| `root` | no | — | workspace root (default: current dir) |
| `json` | no | — | machine-readable JSON output |
| `debug` | no | — | on error, print the redacted diagnostic (never a traceback) |
| `run_id` | yes | — | — |

<!-- keep:start -->
_free notes — errors, examples, next steps (hand-written, preserved)_
<!-- keep:end -->

## workspace

### `workspace`

**Syntax**

```text
theforge workspace [help]
```

| argument/flag | required | default | description |
|---|---|---|---|
| `help` | no | — | show this help message and exit |

<!-- keep:start -->
_free notes — errors, examples, next steps (hand-written, preserved)_
<!-- keep:end -->

### `workspace show`

**Syntax**

```text
theforge workspace show [help] [root] [json] [debug]
```

| argument/flag | required | default | description |
|---|---|---|---|
| `help` | no | — | show this help message and exit |
| `root` | no | — | workspace root (default: current dir) |
| `json` | no | — | machine-readable JSON output |
| `debug` | no | — | on error, print the redacted diagnostic (never a traceback) |

<!-- keep:start -->
_free notes — errors, examples, next steps (hand-written, preserved)_
<!-- keep:end -->
