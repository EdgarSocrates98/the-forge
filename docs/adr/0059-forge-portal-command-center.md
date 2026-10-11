# ADR 0059 — Forge Portal: UI local opcional e command center

- Status: aceito (2026-10-11)

## Contexto

O programa de produtização do ecossistema (prompt_evo_portal) pede uma
experiência única por cima das sete Forjas: *clone once, setup once,
install anywhere, use every Forge through your AI host* — e, para quem
prefere ver antes de agir, uma UI web local opcional com a mesma verdade
que CLI/MCP reportam.

Cada especialista já ganhou seu portal (`<cli> portal`) na sua própria
fase. Falta o command center: o lugar onde a *federação* é o objeto de
trabalho — lifecycle das seis forjas, registry `~/.forge/installations`,
handshakes MCP por forja, grafo federado com namespace por provider, e a
delegação `install auto`. O control plane é o dono natural desse escopo
(ADR-0005 roteamento, ADR-0006 registry, ADR-0058 instalação portátil).

O feature freeze (`docs/feature-freeze.md`) exige ADR para subsistema
novo. A exceção registrada aqui é estreita: o portal não adiciona
semântica ao core — é uma *superfície* read-mostly sobre serviços que já
existem e já são exercidos pelos verbos, com mutações delegadas aos
mesmos gates (`plan` → `confirm` → `plan_token` assinado → receipt).

## Decisão

1. **Servidor vendored, não subsistema**: `theforge._forge_portal` é a
   cópia byte-idêntica do servidor stdlib canônico
   (`forge-portal/portal_core/forge_portal.py`) — mesma classe de
   `_installkit.py` (ADR-0058): stdlib-only, sem conhecimento de domínio,
   sem imports de provider. Divergências entram pelo canônico, nunca por
   fork local.
2. **Adapter na superfície, não no core**: `theforge.portal_adapter`
   mapeia o contrato `forge/PortalApi/1` para serviços existentes
   (`install.service`, `hostflow`, `specialists`, `agents`,
   `graphview.federated_views/merge`, `_installkit.mcp_verify`). Nenhum
   estado é fabricado: capability inexistente vira `unsupported`/
   `unverified`, nunca zero fingido (the-forge não declara MCP próprio —
   a página MCP mostra o estado por especialista).
3. **Segurança por construção**: bind `127.0.0.1`, token de sessão de
   128 bits (`X-Forge-Session`), Origin loopback, mutações atrás de
   `confirm` literal + `plan_token` HMAC que amarra o plano ecoado —
   a mesma matriz do servidor canônico. Launch de host devolve o comando
   para copiar (o browser não tem TTY); `install_auto` delega ao CLI real
   de cada forja — o control plane coordena, cada forja executa a si
   mesma (ADR-0058 §5), nunca simula.
4. **Assets vendored com manifest sha256**: `portal/assets/` no clone;
   `theforge/portal_assets/` no wheel via force-include (mesma emenda de
   `host_assets`). Sem CDN, sem telemetria, offline-first — ADR-0003
   preservado.
5. **Federação honesta**: `/federation` reporta `specialists.collect` +
   `kit.installed_forges` — o mesmo par de evidências de
   `theforge specialists`; o grafo é `federated_merge` real (ids com
   prefixo de provider, sem arestas inferidas entre forjas).
   `InstallError` vira recusa nomeada `TF-PORTAL-NOT-REGISTERED`,
   nunca stack trace.

## Consequências

- Novo verbo `theforge portal [--no-browser|--port|--root]` — superfície
  aditiva; nenhum contrato `theforge/*` muda (o portal fala
  `forge/PortalApi/1`, contrato do ecossistema, não do core).
- `commands.generated.json`/`command-rationale.json` regenerados;
  `test_portal.py` cobre sessão, plan→apply, federação, MCP, tasks,
  recusas nomeadas e o verbo via subprocess real.
- O freeze permanece: nenhum subsistema de domínio entra no core — o
  portal é wiring de superfície sobre serviços existentes e pode ser
  removido sem tocar `theforge/*` contracts.

## Alternativas consideradas

- **Script de checkout** (como `forge-doctor-api/scripts/forge_portal.py`):
  recusado — o boundary de `src/` do doctor-api não existe aqui; o
  verbo é a superfície consistente com os seis irmãos.
- **Servir sem token, só loopback**: recusado — a matriz de segurança
  exige sessão para qualquer `/api` (DNS-rebind mitigação).
- **Página de federação própria**: adiado — o shared SPA ganha a rota
  quando a capability `federation` está presente; o endpoint
  `/federation` já existe e é testado hoje.
