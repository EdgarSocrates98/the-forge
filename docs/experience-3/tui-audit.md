# TUI Audit — Forge Experience 3.0

## Estado real

| Forja | Superfície interativa | Tipo | Full-screen? |
|---|---|---|---|
| the-forge | `ui/home.py` Command Center | stdlib kit, summon-choose-exit | não |
| spark-forge-aws | `ui/home.py` | idem | não |
| api-forge | `ui/home.py` + `tui/app.py` | kit + **Textual** (task-scoped) | parcial (só execução) |
| spark-forge-azure | `ui/home.py` | kit | não |
| platform-forge | `ui/home.py` | kit | não |
| forge-doctor-data | `run_home` | kit | não |
| forge-doctor-api | `run_home` | kit | não |

## Kit stdlib atual (reutilizado em todos)

`UIContext` detecta tty/cor/unicode/largura; `select`, `multi_select`,
`confirm`, `prompt`, `dashboard`, `status_table`. Degrada honestamente:
non-TTY → `NonInteractive`, `NO_COLOR`/`TERM=dumb` → sem escapes,
cp1252 → glifos ASCII. ~450 LOC, zero deps. **É o fallback correto do
§2.9/DoD-16** — não será removido.

## GAP-001 confirmado — o que falta para "full-screen premium"

- Alternate screen, layout persistente (sidebar + painéis), foco e
  navegação por Tab/Shift+Tab, `Ctrl+K` palette, `/` search, `?` help,
  refresh Ctrl+R, estados LOADING/EMPTY/ERROR/SUCCESS em widgets.
- Textual app do api-forge é **task-scoped** (`apiforge-tui <task>`),
  não um home full-screen com navegação entre seções.
- Nenhuma forge tem: dashboard full-screen, MCP manager visual, skills/
  agents explorer navegável, results explorer, install manager visual.

## Avaliação de framework (Cycle 1.3 — decisão)

| Critério | Textual | Rich só | prompt_toolkit | urwid | curses stdlib |
|---|---|---|---|---|---|
| Full-screen real | ✓ alt-screen + widgets | parcial (Live) | parcial | ✓ | manual |
| Cross-platform Win/mac/Linux | ✓ | ✓ | ✓ | ✓ | Win=fragil |
| Testes headless | ✓ `App.run_test()` pilot | parcial | ✓ | fraco | não |
| Licença | MIT | MIT | BSD | LGPL | stdlib |
| Manutenção/comunidade | ativa | ativa | estável | dormente | — |
| Dep footprint | médio | pequeno | médio | pequeno | nenhum |
| Já no ecossistema | **api-forge `[tui]` extra** | doctor-* core | não | não | kit próprio |
| CSS/declarativo | ✓ .tcss | — | — | — | — |
| Async workers | ✓ | — | ✓ | — | — |

**Decisão: Textual** como camada full-screen **opcional** (`[tui]` extra),
lazy-import com fallback honesto para o kit stdlib quando ausente ou
non-TTY. Mantém os cores offline/stdlib-only intactos — igualdade ao
precedente `apiforge[tui]` + `_graphstudio.py` (componente opcional).
Rich entra como dependência transitiva do Textual, não como camada
separada.

## Riscos

- Textual não instalado → fallback deve ser explícito ("instale `x[tui]`"),
  nunca crash nem fake.
- PTY real indisponível no ambiente → verificação via `run_test()` e
  snapshots, declarado UNVERIFIED para terminal real.
