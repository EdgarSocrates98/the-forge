# Cycle 11.2 — Portal registry ops E2E (P1-003)

Escopo: forge-portal#32 MERGED `c1f8844` (2026-10-17) — UI `/forges`
registry-ops-panel + fix backend + E2E real (Chromium + forge-cli real +
PyPI real).

## Comandos executados

```text
gh pr view 32 --json body,files
git show c1f8844 --stat
grep -n "PORTAL-\|_REGISTRY_ACTIONS\|_SAFE_FORGE\|consume_plan\|sign_plan" portal_core/registry_ops.py portal_core/forge_portal.py
```

## O que entra (do corpo do PR + leitura do código)

- **UI** `/forges`: `registry-ops-panel` — tabela do estado real de
  `GET /api/v1/registry/state` (versão, método/dist, pin, instalada em;
  `present:false`/`malformed` marcados, nunca inventados) + formulário
  plan → review → confirm → execute → receipt + refresh para
  install/update/reinstall/rollback/pin/unpin/repair/uninstall. Cliente
  tipado `PortalApi.registryPlan/registryExecute`.
- **Backend fix** (`portal_core/registry_ops.py`): `pin`/`unpin` do
  forge-cli **não têm `--plan`** — o verbo grava `state.json`
  incondicionalmente. Planning agora deriva preview offline do registry
  state (`_offline_plan`), sem subprocess — invariante "plan é
  não-mutante" restaurada. `_REGISTRY_ACTIONS` = allowlist fechada de
  argv head; `_SAFE_FORGE` regex; `_cli_binary()` ausente →
  `PORTAL-CLI-UNAVAILABLE` (409) — nunca execução inventada.
- **Token de plano**: `sign_plan(plan)` no plan → `consume_plan(token,
  plan)` no execute — one-time, bound ao plano; replay/expirado →
  `PORTAL-PLAN-INVALID` (409). `PORTAL-PLAN-MISMATCH` quando plan do body
  diverge de action/forge.

## Segurança HTTP (do PR, E2E real)

| Cenário | Resultado |
|---|---|
| sem sessão | 403 `PORTAL-SESSION` |
| sessão forjada / origem estrangeira | 403 `PORTAL-ORIGIN` |
| ação fora da allowlist | 400 `PORTAL-ACTION` |
| nome de forja inválido | 400 `PORTAL-FORGE` |
| execute sem confirm / sem plan_token | 400 `PORTAL-CONFIRM` / `PORTAL-PLAN-REQUIRED` |
| replay de token | 409 `PORTAL-PLAN-INVALID` |
| `fetch` do SPA sem `X-Forge-Session` | 403 |
| plan de pin | side-effect-free — `state.json` byte-idêntico |

## E2E real (não mock)

Chromium real → plan install `forge-doctor-api` (resolve PyPI real +
venv install ~9s em `FORGE_CLI_HOME`/`FORGE_HOME_OVERRIDE` isolados em
tmp) → confirm → `executed` → linha no estado → uninstall planejado →
confirmado → removida — asserção no `state.json` isolado. Screenshots
20–23 em `e2e/artifacts/`. `~/.forge-cli` real nunca tocado. Preflight
`--plan` + `pytest.skip` explícito quando PyPI/CLI inalcançável — não
finge verde offline.

## Gates do PR (declarados)

`npm test` 384 ✓ · `tsc --noEmit` ✓ · `prettier --check` ✓ ·
`check_i18n` 785/785 ✓ · `ng build` ✓ · `ruff` ✓ · `pytest tests/` 84 ✓ ·
`pytest e2e/` 25 ✓ (101s). Unit novo: 3 backend + 8 Angular specs.

## Não coberto (declarado no PR)

update/rollback/repair **executados** de verdade (precisariam histórico
de versões publicadas); `verify` (mcp --verify) fica no backend, não
entrou na UI; pin/unpin no CLI seguem sem `--plan` (gap upstream
documentado em cli-plan-purity.md).

## Veredito

VERIFIED — única operação de registry exercitada de ponta a ponta com
browser+backend+PyPI reais; segurança com códigos nomeados e replay
rejeitado.

## Risco residual

Execução acontece no contexto do processo do portal (subprocess argv sem
shell); quem opera o portal precisa do forge-cli instalado no mesmo host
— `PORTAL-CLI-UNAVAILABLE` cobre a ausência, não a versão errada.
