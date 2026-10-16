# Portal E2E multi-forge — Cycle 10.1 §4 / Wave 3

- **Date**: 2026-10-15 (UTC-3)
- **Repos**: the-forge @ `cycle-10.1/program` (PR #62) · forge-portal @ `main` (`ab5a3ef` baseline)
- **Host**: Linux · Chrome 155.0.8059.79 (`channel="chrome"`, headless) · playwright (pip, the-forge venv) · Python 3.12
- **Primary evidence**: `TheForgePortal` — the real adapter (`src/theforge/portal_adapter.py`) serving the vendored production Angular bundle (`portal/assets/`). No stub adapter for the primary pass.

## Commands executed

```
cd the-forge
.venv/bin/pip install playwright
.venv/bin/python -m pytest tests/test_browser_real_adapter.py -q   # 9/9 PASS

cd forge-portal
uv run --with pytest python -m pytest tests/test_security_c5.py -q  # 24/24 PASS
```

## Coverage vs §4

| § | Item | Result |
|---|---|---|
| 4.1 | Portal via adapter oficial real, Linux | PASS — `TheForgePortal` + vendored bundle + `PortalServer` loopback |
| 4.2 | catálogo de estados | PARTIAL — installed/unverified states render real; incompatível/init-error states dependem de Forjas ausentes de fato (observados como `unverified`/`not-installed`, não sintetizados) |
| 4.3 | capabilities reais | PASS — `/capabilities` via serviços reais; nada não-suportado exibido como disponível (adapter emite `unverified`) |
| 4.4 | operações install→uninstall | PARTIAL — `plan`/status preview renderizados com dados reais; `apply/uninstall` mutantes validados no harness do forge-portal (`test_browser_e2e.py`, adapter E2E dedicado) + matriz CLI (cyc101-03). Apply real em ambiente descartável fica para cyc101-09 |
| 4.5 | observabilidade | PASS — run ids/receipts via `/lab`, federation e rotas reais; console sem erros em todas as rotas |
| 4.6 | `/lab` receipts reais | PASS — `/lab` serve `reports`/`notes` reais de `docs/programs/ecosystem-2026/benchmarks/`; rota renderiza |
| 4.7 | Playwright browsers | PARTIAL — Chromium (system Chrome 155) exercitado, desktop+mobile (390×844); Firefox/WebKit **NOT_TESTED** (binários não instalados no host) |
| 4.8 | segurança | PASS — `test_security_c5.py` 24/24: sessão/cookie, CSRF/Origin loopback-only, traversal+symlink, injection inerte, redaction por key, plan-token replay/stale/cross-plan, 429 bounded, payload cap |

## Tests added

`the-forge/tests/test_browser_real_adapter.py` — 9 testes: bundle vendored, first paint, todas as rotas declaradas pelo adapter real renderizam, federation com dados reais, `/lab` real, capabilities com ids, install preview, zero console errors em todas as rotas, viewport mobile. Screenshots em `e2e/artifacts/` (gitignored).

## Findings

- `/api/v1/*` exige `X-Forge-Session`/`?forge_session=` — 403 sem token (verificado, correto).
- `/lab` do the-forge emite `reports` (diretórios de benchmark), não `runs` — shape distinto do adapter do forge-portal; ambos legítimos por contrato.
- `BrokenPipeError` observado nos logs do servidor quando o browser aborta requests em navegação SPA — cosmético (cliente desconectou), sem impacto funcional; candidato a hardening futuro.
- Firefox/WebKit: **BLOCKED-external** — não instalados; instalação de browsers é escolha do mantenedor do host.

## Status

**PASS com limitações registradas** — evidência principal usa adapter real (§4.1); partes mutantes (§4.4) e browsers alternativos (§4.7) ficam para cyc101-09 / follow-up documentado.
