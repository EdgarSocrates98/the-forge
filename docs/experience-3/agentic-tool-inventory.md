# Agentic Tool Inventory — Forge Experience 3.0

PARTE I §1.1. Recursos **realmente disponíveis** na sessão Devin CLI +
manifestos agentic das sete Forjas. Nada aqui é inventado: AVAILABLE=NO
significa ausência verificada, não disfarçada.

## Sessão Devin (host executor deste programa)

```text
NAME: Devin CLI (SWE-2 Max)
TYPE: agentic host
SOURCE: devin.ai — sessão local, E:\projetos\FORJAS
VERSION: cli (worktree Windows 11, Python 3.11/3.14 presentes)
AVAILABLE: YES
PURPOSE: coordenação + implementação das ondas
INVOCATION: esta sessão
PERMISSIONS: leitura/escrita nos 7 checkouts, exec, git, gh
RELEVANT_CYCLES: todos
LIMITATIONS: sem WSL/distro POSIX; sem quota de GitHub Actions;
  sem PTY real — loops interativos verificados por testes de teclas
  roteadas (scripted keys), não por sessão de terminal ao vivo
```

## Tools da sessão

| NAME | TYPE | PURPOSE | RELEVANT_CYCLES |
|---|---|---|---|
| read/edit/write/notebook_edit | file tools | implementação e specs | 1–5 |
| exec/get_output/kill_shell | shell | testes, git, gh, builds | 1–5 |
| grep / find_file_by_name | search | descoberta de código | auditoria |
| web_search / webfetch | research | pesquisa de frameworks/padrões | 1.3, 4, 5 |
| ask_user_question | interaction | decisões de produto com o owner | grill gate |
| run_subagent (explore/general) | delegation | implementadores e revisores isolados | 2–5 |
| browser_preview | visual check | Graph Studio no browser real | 4.7 |
| todo_write | tracking | plano de ondas | gestão |

## MCP servers configurados

| NAME | TOOLS RELEVANTES | PURPOSE | CYCLES |
|---|---|---|---|
| tokensave | context/search/read/callers/callees/impact + str_replace | code-graph navegação econômica | auditoria, 1–5 |
| codebase-memory-mcp | search_graph/trace_path/query_graph/get_architecture | structural discovery | auditoria |
| Snyk | security scans | security review | 5.6 |
| aws-mcp | AWS docs | referência spark-forge-aws | docs |

## Subagents disponíveis

```text
NAME: subagent_explore   TYPE: read-only explorer
  PURPOSE: auditorias, rastros de dependência   CYCLES: auditoria, 5.8
NAME: subagent_general   TYPE: read/write implementer
  PURPOSE: implementar ondas isoladas           CYCLES: 1–5
LIMITATIONS: subagents não herdam MCP nem contexto; recebem
  escopo + caminhos absolutos no prompt
```

## Skills acionáveis (instaladas)

| NAME | SOURCE | RELEVANT_CYCLES |
|---|---|---|
| tui-design | ~/.agents/skills | 1.3, 2, 3, 4 (framework eval, patterns, testing) |
| accessibility | ~/.agents/skills | 1.6, 5.3 (WCAG/checklist) |
| vhs-cli-demos | ~/.agents/skills | 5.7, relatório (evidência visual real) |
| algorithmic-art | ~/.agents/skills | — (não usado; sem papel no programa) |
| auto-setup | ~/.agents/skills | 1 (quality gates) |
| kiro-spec-* / kiro-review / kiro-debug / kiro-verify-completion | the-forge/.claude/skills, .agents/skills | spec-driven per-repo, revisão independente |
| agent-launcher-orchestrator | ~/.agents/skills | orchestração futura (não usado nesta wave) |
| agent-teams | ~/.agents/skills | — (multi-sessão; sessão única aqui) |

## Plugins / integrações externas

```text
Figma:              AVAILABLE: NO  — sem integração instalada
GitHub:             AVAILABLE: YES — `gh` CLI autenticado (PRs/merges)
Browser automation: AVAILABLE: PARTIAL — browser_preview (preview + DOM select),
                    sem Playwright/Puppeteer dedicado
Visual testing:     AVAILABLE: NO
Design system tool: AVAILABLE: NO  — tokens implementados em código (theme engine)
UX evaluation:      AVAILABLE: PARTIAL — heurísticas de Nielsen via tui-design skill
```

Alternativas adotadas onde a integração ideal não existe: design system
em código (`ui/theme.py`), evidência visual via `browser_preview` +
`vhs-cli-demos` quando aplicável, UX review por checklist Nielsen.

## Manifestos agentic por Forja

| Forja | forge.agentic.json | workflows | skills | agents | mcp |
|---|---|---|---|---|---|
| the-forge | yes (coordenador) | delegation + task | 16 canonical | 8 AgentSpec | — |
| spark-forge-aws | yes | yes | yes | yes | `sparkforge_aws_*` (~90 tools) |
| api-forge | yes | yes | yes | 25 coordinators | yes |
| spark-forge-azure | yes | yes | yes | yes | yes |
| platform-forge | yes | yes | yes | roster | yes |
| forge-doctor-data | yes | yes | yes | — | yes |
| forge-doctor-api | yes | yes | yes | — | script-driven |

## Limitações de ambiente (honestas)

- Sem distro WSL → verificação POSIX real: **UNVERIFIED** por ambiente.
- Sem quota GitHub Actions → CI remoto não roda; evidência local máxima.
- Sem terminal PTY → TUI verificada via `textual run` headless /
  `App.run_test()` (pilot de Textual) e scripted keys no kit stdlib.
