# Agentic Tool Inventory — Forge Knowledge & Learning Experience 1.0

§3 of `prompt_evo_docs2.md`. Records tools **actually available** in this
Devin CLI session and in the seven checkouts. AVAILABLE=NO means verified
absence — nothing here is invented.

## Session host

```text
NAME: Devin CLI (SWE-2 Max)
TYPE: agentic host
SOURCE: devin.ai — local session, E:\projetos\FORJAS
AVAILABLE: YES
PURPOSE: program coordination + implementation
INVOCATION: this session
PERMISSIONS: read/write on all 7 checkouts, exec, git, gh
RELEVANCE: all waves
LIMITATIONS: no WSL/POSIX terminal; no GitHub Actions quota; no PTY —
  interactive surfaces verified by scripted-key tests, not live sessions
```

## Session tools

| NAME | TYPE | PURPOSE | RELEVANCE |
|---|---|---|---|
| read/edit/write | file tools | doc fixes, new guides | all waves |
| exec/get_output | shell | validators, tests, git, gh | all waves |
| grep / find_file_by_name | search | doc discovery | Wave 0–1 |
| web_search / webfetch | research | doc-tool evaluation (Hub) | Wave 4 |
| browser_preview | visual check | Hub local preview + a11y pass | Wave 4–5 |
| run_subagent (explore/general) | delegation | isolated doc review | Wave 5 |
| todo_write | tracking | wave plan | management |
| ask_user_question | interaction | product decisions | grill gates |

## MCP servers

| NAME | TOOLS | PURPOSE | RELEVANCE |
|---|---|---|---|
| tokensave | context/search/read/callers/callees/impact | code-graph nav, cheap verification | Wave 1, 5 |
| codebase-memory-mcp | search_graph/trace_path/query_graph | structural discovery for doc-vs-code checks | Wave 1 |
| Snyk | security scans | — | not used |
| aws-mcp | AWS docs | aws-forge recipe accuracy | Wave 3 |

## Subagents

```text
NAME: subagent_explore   TYPE: read-only
  PURPOSE: cross-repo doc audits, link verification    WAVES: 0–1, 5
NAME: subagent_general   TYPE: read/write
  PURPOSE: isolated implementation + independent review WAVES: 3–5
LIMITATIONS: no MCP inheritance; scope given via prompt with absolute paths
```

## Skills installed

| NAME | SOURCE | RELEVANCE |
|---|---|---|
| accessibility | ~/.agents/skills | Hub + visual content a11y (§19) |
| vhs-cli-demos | ~/.agents/skills | real TUI captures for visual docs (§21) |
| tui-design | ~/.agents/skills | contextual-help UX in TUI (§17) |
| kiro-* (12 skills) | the-forge/.claude/skills | spec, review, verify-completion, debug |

## External integrations

```text
Figma / design tool:     AVAILABLE: NO
GitHub:                  AVAILABLE: YES — gh authenticated
Browser automation:      AVAILABLE: PARTIAL — browser_preview only
VHS binary:              AVAILABLE: NO (checked: not on PATH) — TUI captures
                         via Buffer.render() text snapshots instead
RAG/vector tooling:      AVAILABLE: NO — §22 metadata stays file-based,
                         as designed ("no heavy RAG without need")
```

## Existing repo tooling (reuse, don't rebuild)

| TOOL | WHERE | PURPOSE |
|---|---|---|
| `scripts/docs/doc_inventory.py` | all 7 (vendored) | parser-walked command inventory + doc divergence |
| `scripts/docs/doc_reference.py` | all 7 | generated command reference pages |
| `scripts/docs/doc_catalogs.py` | all 7 | generated catalogs |
| `scripts/docs/check_docs.py` | all 7 | docs gate (keep-blocks, drift) |
| `scripts/docs/doc_manifest.py` | all 7 (this program) | §4.2 manifest + §4.6 reports |
| `check_docs_surface.py` / surface.lock | azure, aws | CLI surface lock |

## Team mapping (§3.1)

All nine roles execute inline in this session — no separate processes
created (§3.1: "Não presumir que todos esses papéis necessitam ser
implementados como processos autônomos separados"). Independent review is
delegated to `subagent_explore` where isolation matters (Wave 5).
