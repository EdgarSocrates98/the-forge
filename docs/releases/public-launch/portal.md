# Release 1 — Forge Portal: distribuição

## Modelo escolhido (decisão arquitetural, não nova)

O Portal é distribuído **vendored dentro da wheel do the-forge**
(`portal/assets/` + `portal/manifest.json` com sha256 por arquivo,
servidos por `theforge portal` em `127.0.0.1` + session token).
É o mecanismo já implementado (ADR-0058) — preserva a arquitetura,
não exige pacote npm independente, e mantém o Portal opcional.

**Sem pacote npm separado** — não há caso de uso real para `npm i
forge-portal` (o SPA depende do backend `portal_api` do the-forge).

## Auditoria (baseline `55e01d5`)

- `forge-portal-app` 0.1.0, `ng build`, assets content-hashed
  (`chunk-*.js`) — integridade por nome + manifest sha256.
- Manifest: `the-forge/portal/manifest.json`, 34 arquivos com
  bytes+sha256 — verificável pós-instalação.
- Backend: loopback-only + `forge_session` token; resposta 200 com
  sessão válida.

## Gate 4 — verificado 2026-10-16

Wheel `theforge-0.5.0` instalada em venv limpa (`/tmp/r1-venv-tf`):
`theforge portal --no-browser --port 18342` → emite URL com
`forge_session`; `GET /` retorna 200 (SPA servida da wheel instalada).
Comando documenta "portal is optional — CLI/MCP keep working".

E2E profundo (browser real, 9/9 testes + 24/24 segurança): evidência
cycle-10.1/10.2 — código do portal inalterado desde então (diff de
baseline: zero commits funcionais em `forge-portal/` e
`the-forge/portal/`).

## Known limitations (para release notes)

- Sessão é efêmera por processo; reload exige URL com token.
- Firefox/WebKit: PARTIAL/NOT_TESTED (evidência cycle-10.1).
- Bind sempre loopback — sem modo remoto (by design).
