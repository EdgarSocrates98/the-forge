# `theforge` command reference

Generated from the real CLI parser by `doc_inventory.py` + `doc_reference.py`. Do not hand-edit generated sections — write between `keep:start`/`keep:end` markers. `por que`/`quando` lines come from the curated `command-rationale.json` — edit rationale there, never here. Status vocabulary: `available` unless marked otherwise.

Rationale coverage: **27/27** first-level groups curated in `command-rationale.json`.

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

**para que:** specialized agent registry

- **por que:** registro de agentes especializados com autoridade declarada (AgentSpec/v1)
- **quando usar:** inspecionar qual agente propõe/classifica/executa antes de confiar num fluxo

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

- **por que:** registro de agentes especializados com autoridade declarada (AgentSpec/v1)
- **quando usar:** inspecionar qual agente propõe/classifica/executa antes de confiar num fluxo

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

- **por que:** registro de agentes especializados com autoridade declarada (AgentSpec/v1)
- **quando usar:** inspecionar qual agente propõe/classifica/executa antes de confiar num fluxo

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

**para que:** route a task to a specialist

- **por que:** pergunta em linguagem natural roteada ao especialista certo
- **quando usar:** você sabe o que quer mas não qual forja/workflow executa

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

**para que:** declared capabilities

- **por que:** catálogo de capabilities declaradas por cada provider — descoberta por contrato, não memória
- **quando usar:** antes de instalar/delegar: list/discover/search/check o que cada forja atende

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

**para que:** remote discovery by requirement: negotiates installed providers first, then consults enabled registry sources — reports RemoteProviderCandidate metadata, never installs (§22-26)

- **por que:** catálogo de capabilities declaradas por cada provider — descoberta por contrato, não memória
- **quando usar:** antes de instalar/delegar: list/discover/search/check o que cada forja atende

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

- **por que:** catálogo de capabilities declaradas por cada provider — descoberta por contrato, não memória
- **quando usar:** antes de instalar/delegar: list/discover/search/check o que cada forja atende

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

**para que:** negotiate a CapabilityRequirement against the registered manifests (offline, deterministic, machine-readable with --json)

- **por que:** catálogo de capabilities declaradas por cada provider — descoberta por contrato, não memória
- **quando usar:** antes de instalar/delegar: list/discover/search/check o que cada forja atende

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

- **por que:** catálogo de capabilities declaradas por cada provider — descoberta por contrato, não memória
- **quando usar:** antes de instalar/delegar: list/discover/search/check o que cada forja atende

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

**para que:** the project's reusable-decision memory (.forge/intel/decisions.json)

- **por que:** memória de decisões reutilizáveis do workspace (.forge/intel/decisions.json)
- **quando usar:** registrar ou auditar decisões que devem persistir entre sessões

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

**para que:** inspect host, workspace and providers

- **por que:** diagnóstico honesto de host, workspace e providers — primeira linha de troubleshooting
- **quando usar:** pós-install, ambiente novo, ou quando qualquer comando falha sem razão clara

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

**para que:** measured execution economy

- **por que:** economia medida de execução (bytes, não tokens estimados)
- **quando usar:** entender custo real de contexto/descoberta antes de otimizar

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

**para que:** evaluate a StrategyExperiment/v1 against local observations (read-only, advisory; never promotes)

- **por que:** economia medida de execução (bytes, não tokens estimados)
- **quando usar:** entender custo real de contexto/descoberta antes de otimizar

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

**para que:** aggregate recorded execution observations into a global economy receipt (read-only, offline)

- **por que:** economia medida de execução (bytes, não tokens estimados)
- **quando usar:** entender custo real de contexto/descoberta antes de otimizar

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

**para que:** explain a past run

- **por que:** explica um run passado — o porquê de cada passo
- **quando usar:** auditar uma execução que já aconteceu (trace mostra o quê, explain o porquê)

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

**para que:** the capability graph: declared+observed relations of the registry and workspace (cached manifests only, no provider process)

- **por que:** grafo de capabilities: relações declaradas+observadas do registry e do workspace
- **quando usar:** navegar dependências e abrir o Graph Studio sem spawnar providers

**Syntax**

```text
theforge graph [help] [root] [json] [debug] [CAPABILITY] [mesh] [view] [federated] [ui] [no_browser] [port]
```

| argument/flag | required | default | description |
|---|---|---|---|
| `help` | no | — | show this help message and exit |
| `root` | no | — | workspace root (default: current dir) |
| `json` | no | — | machine-readable JSON output |
| `debug` | no | — | on error, print the redacted diagnostic (never a traceback) |
| `CAPABILITY` | no | — | only the edges touching this capability ('provider/capability' or a bare capability id) |
| `mesh` | no | — | the domain mesh projection: per domain, the observe/engineer/verify capabilities derived from declared produces/consumes/can_verify relations |
| `view` | no | — | emit the ForgeGraphView/v1 document (Graph Studio contract) instead of the capability listing |
| `federated` | no | — | collect views from every specialist checkout that exposes `graph view --json` and merge them namespaced by provider |
| `ui` | no | — | open the local Graph Studio explorer in a browser |
| `no_browser` | no | — | with --ui: serve without opening a browser (SSH/remote) |
| `port` | no | — | with --ui: port to bind (default ephemeral) |

<!-- keep:start -->
_free notes — errors, examples, next steps (hand-written, preserved)_
<!-- keep:end -->

## hosts

### `hosts`

**para que:** AI host detection and activation

- **por que:** detecção e ativação de hosts de IA (Claude/Devin/Codex)
- **quando usar:** ver onde a integração está ativa ou preparar a ativação

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

**para que:** evaluate activation for a host

- **por que:** detecção e ativação de hosts de IA (Claude/Devin/Codex)
- **quando usar:** ver onde a integração está ativa ou preparar a ativação

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

- **por que:** detecção e ativação de hosts de IA (Claude/Devin/Codex)
- **quando usar:** ver onde a integração está ativa ou preparar a ativação

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

- **por que:** detecção e ativação de hosts de IA (Claude/Devin/Codex)
- **quando usar:** ver onde a integração está ativa ou preparar a ativação

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

**para que:** create .forge/ in the workspace

- **por que:** cria `.forge/` no workspace — pré-requisito de quase tudo
- **quando usar:** primeiro passo num diretório que ainda não é workspace

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

**para que:** governed provider installation

- **por que:** instalação governada de providers com plano→aprovação
- **quando usar:** instalar/atualizar um especialista com recibo verificável

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

**para que:** install this forge's host assets into the resolved scope

- **por que:** instalação governada de providers com plano→aprovação
- **quando usar:** instalar/atualizar um especialista com recibo verificável

**Syntax**

```text
theforge install apply [help] [root] [json] [debug] [scope] [yes] [host] [profile] [LIST] [dry_run]
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
| `LIST` | no | — | comma-separated optional components (skills,agents,mcp,tui,graph-studio) — overrides the profile's component set |
| `dry_run` | no | — | — |

<!-- keep:start -->
_free notes — errors, examples, next steps (hand-written, preserved)_
<!-- keep:end -->

### `install auto`

**para que:** delegate install to every registered forge; --scope workspace discovers sibling repos, --member fans out

- **por que:** instalação governada de providers com plano→aprovação
- **quando usar:** instalar/atualizar um especialista com recibo verificável

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

**para que:** deep install health (ledger, drift, mcp, handshake)

- **por que:** instalação governada de providers com plano→aprovação
- **quando usar:** instalar/atualizar um especialista com recibo verificável

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

**para que:** real JSON-RPC handshake against the MCP server

- **por que:** instalação governada de providers com plano→aprovação
- **quando usar:** instalar/atualizar um especialista com recibo verificável

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

**para que:** build a deterministic InstallationPlan/v2 for a remote candidate (plan-only: nothing is downloaded or installed)

- **por que:** instalação governada de providers com plano→aprovação
- **quando usar:** instalar/atualizar um especialista com recibo verificável

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

**para que:** restore managed assets that drifted or went missing

- **por que:** instalação governada de providers com plano→aprovação
- **quando usar:** instalar/atualizar um especialista com recibo verificável

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

**para que:** install ledger + drift + health of the target

- **por que:** instalação governada de providers com plano→aprovação
- **quando usar:** instalar/atualizar um especialista com recibo verificável

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

**para que:** remove only what the ledger declares as managed

- **por que:** instalação governada de providers com plano→aprovação
- **quando usar:** instalar/atualizar um especialista com recibo verificável

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

**para que:** upgrade the bootstrap-installed runtime (pinned only)

- **por que:** instalação governada de providers com plano→aprovação
- **quando usar:** instalar/atualizar um especialista com recibo verificável

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

**para que:** bootstrap installation registry (~/.forge/installations)

- **por que:** registro de instalações bootstrap (~/.forge/installations)
- **quando usar:** auditar o que está instalado e de onde veio

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

- **por que:** registro de instalações bootstrap (~/.forge/installations)
- **quando usar:** auditar o que está instalado e de onde veio

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

**para que:** forge knowledge layer (bootstrap packages)

- **por que:** camada de conhecimento ForgeKnowledge/v1 (appropriate_for/inappropriate_for)
- **quando usar:** decidir qual forja usar por contrato declarado — base do which-forge

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

- **por que:** camada de conhecimento ForgeKnowledge/v1 (appropriate_for/inappropriate_for)
- **quando usar:** decidir qual forja usar por contrato declarado — base do which-forge

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

- **por que:** camada de conhecimento ForgeKnowledge/v1 (appropriate_for/inappropriate_for)
- **quando usar:** decidir qual forja usar por contrato declarado — base do which-forge

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

- **por que:** camada de conhecimento ForgeKnowledge/v1 (appropriate_for/inappropriate_for)
- **quando usar:** decidir qual forja usar por contrato declarado — base do which-forge

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

**para que:** engineering memory (.forge/memory/)

- **por que:** memória de engenharia do workspace (.forge/memory/)
- **quando usar:** persistir/recuperar contexto entre sessões sem re-derivar fatos

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

**para que:** entries allowed to leave the project (portable/organization only)

- **por que:** memória de engenharia do workspace (.forge/memory/)
- **quando usar:** persistir/recuperar contexto entre sessões sem re-derivar fatos

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

**para que:** import portable/organization entries (project/workspace are refused)

- **por que:** memória de engenharia do workspace (.forge/memory/)
- **quando usar:** persistir/recuperar contexto entre sessões sem re-derivar fatos

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

**para que:** distill a run's persisted artifacts into memory entries

- **por que:** memória de engenharia do workspace (.forge/memory/)
- **quando usar:** persistir/recuperar contexto entre sessões sem re-derivar fatos

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

**para que:** structured query over memory entries (deterministic, bounded)

- **por que:** memória de engenharia do workspace (.forge/memory/)
- **quando usar:** persistir/recuperar contexto entre sessões sem re-derivar fatos

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

**para que:** failure-pattern rollup over recorded failure entries

- **por que:** memória de engenharia do workspace (.forge/memory/)
- **quando usar:** persistir/recuperar contexto entre sessões sem re-derivar fatos

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

**para que:** distill entries into a MemorySummary (sources are kept)

- **por que:** memória de engenharia do workspace (.forge/memory/)
- **quando usar:** persistir/recuperar contexto entre sessões sem re-derivar fatos

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

**para que:** Plan a task across providers, one node per specialist, executed locally in sequence.

Without --from FILE the nodes are ordered by declared capability relations first (rule
`capability-graph`: requires and produces→consumes among qualified providers) and then by
the textual order of their keywords in the intent (rule `intent-order`): proxies of the
data flow that can infer a wrong dependency (e.g. "an API that consumes the Spark pipeline
data" puts the API first). Review the plan without --execute; --from FILE fixes the order
explicitly. An ambiguous decomposition may be resolved by a `proposes_plans` provider
(semantic tier), revalidated by the deterministic plan checks.

- **por que:** plano multi-provider: um nó por especialista, sequência local
- **quando usar:** trabalho composto que precisa ser revisto antes de executar

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

**para que:** provider authoring: scaffold and conformance

- **por que:** authoring de provider: scaffold + conformance
- **quando usar:** criar ou validar um novo provider Forge — não uso diário

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

**para que:** run the Forge Protocol conformance battery against an argv

- **por que:** authoring de provider: scaffold + conformance
- **quando usar:** criar ou validar um novo provider Forge — não uso diário

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

**para que:** write a stdlib-only provider skeleton into an empty directory

- **por que:** authoring de provider: scaffold + conformance
- **quando usar:** criar ou validar um novo provider Forge — não uso diário

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

**para que:** provider operations

- **por que:** operações sobre providers registrados (health, surface)
- **quando usar:** verificar saúde e superfície declarada da frota local

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

- **por que:** operações sobre providers registrados (health, surface)
- **quando usar:** verificar saúde e superfície declarada da frota local

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

**para que:** provider registry

- **por que:** registry de providers — fonte de descoberta além do checkout local
- **quando usar:** descobrir/instalar forjas que não estão no workspace

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

- **por que:** registry de providers — fonte de descoberta além do checkout local
- **quando usar:** descobrir/instalar forjas que não estão no workspace

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

- **por que:** registry de providers — fonte de descoberta além do checkout local
- **quando usar:** descobrir/instalar forjas que não estão no workspace

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

- **por que:** registry de providers — fonte de descoberta além do checkout local
- **quando usar:** descobrir/instalar forjas que não estão no workspace

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

**para que:** configured registry sources (untrusted metadata; the local installed registry stays authoritative)

- **por que:** registry de providers — fonte de descoberta além do checkout local
- **quando usar:** descobrir/instalar forjas que não estão no workspace

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

**para que:** remote-execution trust layer (remote-policy.toml)

- **por que:** camada de confiança de execução remota (remote-policy.toml)
- **quando usar:** configurar política para execução fora do host local

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

**para que:** evaluate each declared remote target against the policy

- **por que:** camada de confiança de execução remota (remote-policy.toml)
- **quando usar:** configurar política para execução fora do host local

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

**para que:** the effective remote policy (absent file = deny-all)

- **por que:** camada de confiança de execução remota (remote-policy.toml)
- **quando usar:** configurar política para execução fora do host local

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

**para que:** re-render, re-verify or re-execute a past run

- **por que:** re-renderiza, re-verifica ou re-executa um run persistido
- **quando usar:** reproduzir uma execução com a mesma evidência gravada

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

**para que:** resume a plan run: nodes whose recorded inputs still verify are reused, the rest re-execute

- **por que:** retoma um plano: nós com inputs ainda válidos são reutilizados, o resto re-executa
- **quando usar:** uma execução multi-step falhou no meio e você não quer recomeçar

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

**para que:** specialist lifecycle control plane

- **por que:** control plane do ciclo de vida dos especialistas delegáveis
- **quando usar:** listar/inspecionar quem pode receber `task` via forge.agentic.json

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

**para que:** real health probes per specialist

- **por que:** control plane do ciclo de vida dos especialistas delegáveis
- **quando usar:** listar/inspecionar quem pode receber `task` via forge.agentic.json

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

**para que:** lifecycle state per catalog forge

- **por que:** control plane do ciclo de vida dos especialistas delegáveis
- **quando usar:** listar/inspecionar quem pode receber `task` via forge.agentic.json

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

- **por que:** control plane do ciclo de vida dos especialistas delegáveis
- **quando usar:** listar/inspecionar quem pode receber `task` via forge.agentic.json

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

**para que:** summarize workspace state

- **por que:** resumo do estado do workspace
- **quando usar:** visão rápida: inicializado? providers? últimas runs?

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

**para que:** declared execution targets (targets.toml)

- **por que:** targets de execução declarados (targets.toml)
- **quando usar:** gerenciar destinos reutilizáveis de `task run`

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

**para que:** declared targets, merged user+project (project wins per id)

- **por que:** targets de execução declarados (targets.toml)
- **quando usar:** gerenciar destinos reutilizáveis de `task run`

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

**para que:** dry-run provider×target negotiation for a requirement

- **por que:** targets de execução declarados (targets.toml)
- **quando usar:** gerenciar destinos reutilizáveis de `task run`

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

**para que:** delegate a task to specialists (real argv execution)

- **por que:** delega um intent a um especialista — argv real do workflow declarado
- **quando usar:** executar trabalho na forja certa (plan antes, run depois, explain para auditar)

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

**para que:** inspect a delegation

- **por que:** delega um intent a um especialista — argv real do workflow declarado
- **quando usar:** executar trabalho na forja certa (plan antes, run depois, explain para auditar)

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

**para que:** build delegation requests

- **por que:** delega um intent a um especialista — argv real do workflow declarado
- **quando usar:** executar trabalho na forja certa (plan antes, run depois, explain para auditar)

**Syntax**

```text
theforge task plan [help] [root] [json] [debug] <intent> [target] [provider] [workflow]
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
| `workflow` | no | — | pin a workflow id when routing is ambiguous |

<!-- keep:start -->
_free notes — errors, examples, next steps (hand-written, preserved)_
<!-- keep:end -->

### `task run`

**para que:** execute delegations

- **por que:** delega um intent a um especialista — argv real do workflow declarado
- **quando usar:** executar trabalho na forja certa (plan antes, run depois, explain para auditar)

**Syntax**

```text
theforge task run [help] [root] [json] [debug] <intent> [target] [provider] [workflow] [max_parallel]
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
| `workflow` | no | — | pin a workflow id when routing is ambiguous |
| `max_parallel` | no | — | — |

<!-- keep:start -->
_free notes — errors, examples, next steps (hand-written, preserved)_
<!-- keep:end -->

## trace

### `trace`

**para que:** the run's local trace: what happened, span by span (explain answers why)

- **por que:** o trace local do run, span por span — o que aconteceu
- **quando usar:** depurar uma execução (explain responde porquê, trace mostra o quê)

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

**para que:** workspace description

- **por que:** descrição e administração do workspace `.forge/`
- **quando usar:** configurar/inspecionar o workspace atual

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

**para que:** describe the workspace (cached manifests only, no provider)

- **por que:** descrição e administração do workspace `.forge/`
- **quando usar:** configurar/inspecionar o workspace atual

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
