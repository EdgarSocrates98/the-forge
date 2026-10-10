# Test Coverage Audit — Forge Experience 3.0

Últimos resultados completos medidos (suítes reais, `python -m pytest`):

| Forja | Resultado | Notas |
|---|---|---|
| the-forge | 4629 default verde (55 slow/real_provider deselected) | kit+i18n+wizard+home: 24 testes; parity gate vendored |
| spark-forge-aws | 14836 passed (5 drifts corrigidos, 386 focused green) | tool schemas reais, parity CLI↔MCP |
| api-forge | 1828 passed / 1 flake | flake pré-existente sob carga (green standalone) |
| spark-forge-azure | 2998 passed, 13 skipped | mirrors/agents sync gates |
| platform-forge | suite completa verde + lab 44/44 + evals 93/93 | data_path, sqlite, Windows fixes |
| forge-doctor-data | 2618 passed | — |
| forge-doctor-api | 1713 passed, 40 skipped | extras opcionais |

## Cobertura TUI/UI hoje

- `test_ui_kit.py`-família: scripted keys por select/multi_select/confirm,
  i18n, wizard, parity byte-vendored — 24 testes no the-forge, espelhados.
- api-forge: `tests/tui/` para o app Textual task-scoped.
- **Ausente**: snapshots de frame em tamanhos fixos (80×24, 60 col),
  pilot tests `run_test()` para shell full-screen, jornadas E2E.

## Obrigatórios do §IV.3 que já existem

UNIT ✓ CONTRACT ✓ CLI REGRESSION ✓ (surface.lock + generated docs)
MCP HANDSHAKE ✓ (verify real) DOCUMENTATION DRIFT ✓ (check_docs)
SECURITY ✓ (boundary/refusal gates) INSTALLATION E2E ✓ (scripts E2E)
GRAPH STUDIO ✓ (node --check + view parity) MULTI-FORGE ✓ (federação)

## Os que a Wave 3–6 deve adicionar

TUI COMPONENT (widgets), TUI PILOT (`run_test`), ACCESSIBILITY (tema
contrast/labels), CROSS-PLATFORM (guardas OS), PERFORMANCE (startup
medido), BROWSER E2E (studio via preview — parcial honesto), HOST
INTEGRATION (declarado UNVERIFIED sem hosts reais no CI).
