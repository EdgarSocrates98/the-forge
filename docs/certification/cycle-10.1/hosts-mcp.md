# Hosts & MCP certification — Cycle 10.1 §6 / Wave 4

- **Date**: 2026-10-15 (UTC-3) · Linux
- **the-forge** @ `cycle-10.1/program` (PR #62) · api-forge @ `6b7ede6` (`apiforge-mcp` from repo `.venv`)
- **Classification per §6.7**: VERIFIED only with real execution; absence of host → BLOCKED/NOT_TESTED.

## §6.1 Host discovery (real, `theforge hosts observe --json`)

| Host | Binary | Version | Integration drift | Class |
|---|---|---|---|---|
| claude | `/home/edgar/.local/bin/claude` | 2.1.295 (Claude Code) | 0 missing | VERIFIED |
| devin | `/home/edgar/.local/bin/devin` | 3000.11.92 (7f4e64980e22) | 0 missing | VERIFIED |
| codex | `/home/edgar/.local/bin/codex` | codex-cli 0.159.0 | 0 missing | VERIFIED |
| copilot | — | — | — | **NOT_TESTED** (not installed) |

All three installed hosts detected with `confidence_basis: binary+config_dir`, real evidence kinds listed.

## §6.2 MCP — protocol-direct vs host-executed

**Direct protocol** (cyc101-02 fresh run, `run_mcp_handshakes.py`): 6/6 PASS, 388 tools total — sparkforge-aws 146, apiforge 154, platformforge 39, sfa 18, doctor-api 17, doctor-data 14. VERIFIED.

**Host-executed** (this run — real host CLIs, then clean removal):

| Host | Registration | Host-side handshake | Removal | Class |
|---|---|---|---|---|
| claude | `claude mcp add cyc101-probe --scope user -- apiforge-mcp` → written to `~/.claude.json` | `claude mcp list` → `cyc101-probe … ✔ Connected` (host spawned the server and completed MCP initialize) | `claude mcp remove` — clean | **VERIFIED** |
| codex | `codex mcp add cyc101-probe` → `~/.codex/config.toml` | `codex mcp get cyc101-probe` shows enabled stdio entry; spawn-probe `initialize` → `serverInfo.name: apiforge` | `codex mcp remove` — clean | **VERIFIED** (config + handshake; codex has no list-time health probe — noted honestly) |
| devin | file-based (`.devin/mcp_config.local.json` convention; not present for forge MCPs) | running-session evidence only (tokensave active in this session) | — | **PARTIAL** |
| copilot | — | — | — | **NOT_TESTED** |

Invalid-payload/timeout/exit-code behavior: covered by `run_mcp_handshakes.py` probes (negative cases) + forge-side test suites; per-server hostile-input fuzz not in scope.

## §6.3 Skills & §6.4 Agents/subagents

- Host mirrors present with **0 missing** assets for claude/devin/codex (`hosts observe` integration.drift).
- the-forge agent registry: **8 specialized agents** (bootstrap-installation, capability-negotiator, cross-forge-planner, ecosystem-debugger, ecosystem-router, execution-orchestrator, forge-discovery, verification-orchestrator), closed authority `propose|classify|advise|execute-approved`; forbidden-action wall enforced by `check_authority` (suite-tested).
- Codex renders: `.codex/agents/*.toml` tracked via `render_agents.py`; Devin uses `run_subagent` profiles; Claude via plugin `.claude/agents/` (gitignored, rendered). Discovery + metadata VERIFIED via registry + drift-free mirrors.

## §6.5 Multi-agent scenario ("analise projeto de API e infra")

**PARTIAL** — the deterministic routing/delegation machinery is suite-proven (ecosystem-router proposes within eligible set, execution-orchestrator only runs approved plans, verification-orchestrator proposes independent verification), but a live host LLM session driving The Forge → API Forge + Platform Forge end-to-end was not executed: requires interactive/authenticated host session. Logged as follow-up; NOT declared VERIFIED.

## §6.6 Context economy

- Declared per-agent `context_budget_bytes` (1 KiB–512 KiB) bounded by construction; `RunTelemetry` counters `agent_*`/`skill_*`/`knowledge_bytes` exist and suite-tested.
- Measured bytes in this session's host round-trips: `~/.claude.json` diff = +1 server entry, 0 residual config after removal.
- **No % savings claim** — no valid baseline comparison executed. PARTIAL.

## Matrix summary

| Capability | claude | codex | devin | copilot |
|---|---|---|---|---|
| discovery+version | VERIFIED | VERIFIED | VERIFIED | NOT_TESTED |
| MCP register | VERIFIED | VERIFIED | PARTIAL (file) | NOT_TESTED |
| MCP handshake via host | VERIFIED | VERIFIED | PARTIAL | NOT_TESTED |
| MCP removal | VERIFIED | VERIFIED | PARTIAL | NOT_TESTED |
| skills present | VERIFIED (drift 0) | VERIFIED (drift 0) | VERIFIED (drift 0) | NOT_TESTED |
| agents render | n/a (plugin, gitignored) | VERIFIED (.codex/agents) | VERIFIED (run_subagent) | NOT_TESTED |
| multi-agent E2E | PARTIAL | PARTIAL | PARTIAL | NOT_TESTED |
| context economy | PARTIAL | PARTIAL | PARTIAL | NOT_TESTED |

**Status**: CONDITIONAL→PARTIAL — host-level MCP proof now exists for claude+codex; copilot absent; §6.5/§6.6 remain PARTIAL pending a live host session and a valid economy baseline.
