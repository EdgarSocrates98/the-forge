# Design Audit — Forge Experience 3.0

## O que existe

- Cores ANSI semânticas pontuais via `_c(ctx, code, text)` — sem tokens
  nomeados, literal por chamada.
- i18n pt/en por forge (`ui/i18n.py`, `FORGE_LANG`) — chrome do UI.
- Sem tema, sem identidade visual por forja, sem hierarquia tipográfica
  definida, sem estado visual sistemático.

## Identidade requerida (§1.5) → tokens

| Forja | Identidade | Token primário (ANSI/truecolor) |
|---|---|---|
| the-forge | âmbar, carvão, grafite | `accent` amber `#f5a623` |
| spark-forge-aws | laranja, âmbar, grafite | `accent` orange `#ff8c1a` |
| spark-forge-azure | ciano, azul, grafite | `accent` cyan `#22b8cf` |
| api-forge | violeta, índigo | `accent` violet `#8a5cf6` |
| platform-forge | verde, teal | `accent` green-teal `#2fbf9b` |
| forge-doctor-data | azul, verde | `accent` blue-green `#3aa7a3` |
| forge-doctor-api | violeta, teal | `accent` violet-teal `#7c6ff0` |

Tokens semânticos comuns (nunca cor literal espalhada):
`accent`, `surface`, `surface-alt`, `text`, `text-dim`, `ok`, `warn`,
`error`, `info`, `muted`, `focus`, `selection`.

## Estados visuais (§1.7) — vocabulário único

`LOADING READY EMPTY UNKNOWN UNAVAILABLE DEGRADED ERROR SUCCESS
CANCELLED` — cada um com (glyph ascii+unicode, cor semântica, label
i18n). `UNKNOWN` nunca renderiza como `SUCCESS`.

## GAP-005 — consolidação do kit (decisão Cycle 1.2)

Copias `ui/{kit,home,wizard,i18n}.py` ×7 diferem apenas no nome do
pacote importado. **Decisão: vendor controlado com geração automática**
— mesma convenção provada de `_installkit.py`/`_graphstudio.py`:
fonte canônica em `the-forge/src/theforge/ui/`, `vendor.py` reescreve o
import do pacote e copia; gate de paridade testa drift. Sem dependência
nova entre pacotes, sem The Forge obrigatório — casa com "não criar
dependência obrigatória" e com a portabilidade offline.

## O que será construído (design system §1.4)

Camada 1 (stdlib, sempre disponível): `ui/theme.py` (tokens + identidades
+ resolução NO_COLOR/mono), `ui/components.py` (StatusBadge, ActionCard,
StatusCard, DataTable, Tree, Progress, Notification, HelpOverlay,
ErrorRecovery — renderizados pelo kit ANSI existente).

Camada 2 (opcional `[tui]`): `ui/shell.py` — ForgeShell App em Textual:
TopBar, Sidebar, Footer, Dashboard, CommandPalette, Search,
ResultsExplorer, LogViewer, TaskTimeline, EvidenceViewer, Wizard screens,
ForgeForm/Select/MultiSelect/Confirmation/FilePicker — widgets reais
mapeando os 27 nomes do §1.4, dirigidos por um `ForgeProfile` por repo.
