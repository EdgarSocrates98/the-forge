# Baseline — Forge Experience 3.0

PARTE III §3.2. Estado real medido nesta auditoria (2026-10), não herdado
de relatórios antigos. Os oito GAPs pré-identificados foram revalidados no
código atual.

## Revalidação dos GAPs pré-identificados

| GAP | Descrição | Veredito na revisão atual |
|---|---|---|
| GAP-001 | TUI limitada a menus ANSI | **CONFIRMADO** — `ui/home.py` ×7 usa `select/multi_select` inline; full-screen real só no api-forge (`tui/app.py`, extra `[tui]`) |
| GAP-002 | `signature(install_fn)` p/ components | **CONFIRMADO** — `ui/wizard.py:162` nas 7 cópias; wrapper `lambda **kw` esvaziaria `components` silenciosamente |
| GAP-003 | `host_arg or "all"` | **CONFIRMADO** — `ui/wizard.py:165,198` nas 7 cópias; zero hosts marcados → `host=None` → `or "all"` configura **todos** os hosts |
| GAP-004 | `workflows[0]` sem routing | **CONFIRMADO** — `theforge/cli/commands.py:1459,1498`, `theforge/ui/home.py:96`; primeiro workflow sempre vence |
| GAP-005 | Duplicação de UI kit | **CONFIRMADO** — `ui/{kit,home,wizard,i18n}.py` copiado ×7 com só o import do pacote alterado; sem fonte canônica nem gate de paridade |
| GAP-006 | Docs extensos vs discoverability | **PARCIAL** — `check_docs` 0 problemas e reference gerado existem; falta ajuda contextual *dentro* da interface |
| GAP-007 | Hosts reais ≠ config declarada | **CONFIRMADO como dívida** — receipts distinguem ACTIVE_NOW/RESTART_REQUIRED, mas sem handshake real por host no ambiente |
| GAP-008 | Graph Studio recursos visuais | **CONFIRMADO** — explorer canvas funciona; busca/filtros/inspector/diff/temporal ausentes ou básicos |

## Estado por Forja (verificado)

| Forja | CLI cmds | Home (stdlib kit) | Textual app | Extra `[tui]` | Graph view | MCP tools |
|---|---|---|---|---|---|---|
| the-forge | 63 | Command Center | — | — | `graph view/status/ui` | — (orquestrador) |
| spark-forge-aws | 242 | home.py | — | — | `graph view/status/ui` | ~90 + graph_view/status |
| api-forge | 443 | home.py | `tui/app.py` (execução) | yes | `graph view/ui` | yes + `apiforge_graph_view` |
| spark-forge-azure | 93 | home.py | — | — | `graph view/ui` | yes |
| platform-forge | 57 | home.py | — | — | `graph view/ui` + `--snapshot` | yes |
| forge-doctor-data | 289 | run_home | — | — | `graph view/ui` | yes |
| forge-doctor-api | 35 | run_home | — | — | `graph view/ui` | yes |

## Infraestrutura já entregue (reutilizar, não reescrever)

- `ui/kit.py` stdlib: `select`, `multi_select`, `confirm`, `prompt`,
  `dashboard`, `status_table`, `UIContext` (tty/color/unicode/width),
  `NonInteractive`; i18n pt/en via `FORGE_LANG`.
- Install wizard real em todos: env-check → scope → profile → hosts →
  components → dry-run review → confirm → apply → doctor.
- Installkit vendored byte-parity + `_SOURCE_SHA256` + `vendor.py`.
- Graph Studio embutido (`_graphstudio.py` byte-parity), ForgeGraphView/v1,
  federação via the-forge, `graph view --snapshot` (platform-forge).
- docs-as-code: `doc_inventory.py`, `doc_reference.py`, `check_docs.py`,
  `doc_catalogs.py` — 1222 comandos, 0 drift nos 7 repos.
- UTF-8 stdout guards nos entrypoints dos 7 repos (cp1252-safe).

## Métricas baseline de fricção (medidas, não inventadas)

| Métrica | Valor atual | Fonte |
|---|---|---|
| Comandos para primeira instalação | 2 (`forge_bootstrap.py` → wizard) | scripts/forge_bootstrap.py |
| Decisões obrigatórias no wizard | 5 (scope, profile, hosts, components, confirm) | ui/wizard.py |
| Telas até primeira tarefa | home → 1 menu → confirmação ≈ 3 | ui/home.py |
| Passos para verificar MCP | 1 (`mcp-verify` menu/script) | install kit |
| Passos para achar uma skill | skills catalog doc ou menu (sem busca) | GAP-006 |
| `bare <cli>` fora de TTY | help/summary linear (headless ok) | homes |
| Startup do kit stdlib | import ~0 deps (stdlib) | kit.py |

## Limitações do ambiente desta auditoria

Sem WSL, sem PTY real, sem quota CI. Itens dependentes ficam
UNVERIFIED de forma honesta nos relatórios finais.
