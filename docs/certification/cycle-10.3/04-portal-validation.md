# Cycle 10.3 — Wave 4: Forge Portal distribuído

Data: 2026-10-16. Fonte: wheel `theforge_core-0.5.0` baixada do PyPI,
instalada em venv limpa — **não** o checkout local.

## 1. Distribuição (§6.2)

| Item | Resultado |
|---|---|
| Bundle vendored no wheel | ✅ `theforge portal` serve `index.html` + `main-*.js` + `styles-*.css` reais |
| Servidor | ✅ bind `127.0.0.1` loopback, porta configurável |
| Sessão | ✅ token 128-bit na URL de boas-vindas (`?forge_session=`) |
| Index | ✅ HTTP 200, Angular `ForgePortalApp` |

## 2. Segurança (§6.6) — testado, não declarado

| Teste | Resultado |
|---|---|
| `GET /api/v1/versions` **sem token** | **403** ✅ |
| mesmo GET com `X-Forge-Session` | **200** — envelope `forge/PortalApi/1` |
| `installed.version` na resposta | `0.5.0`, `origin: site-packages` — dist metadata real (fix do rename verificado em produção) |
| Path traversal (`--path-as-is ../../etc/passwd`) | **404** ✅ |
| POST `text/plain` em op desconhecida | **404** (op inexistente; content-type gate adicional) |
| Headers (do código `_forge_portal.py`) | `nosniff`, `Referrer-Policy: no-referrer`, `CSP`, `Cache-Control: no-store` |
| Limites (código) | payload 1 MiB, 10 POST mutantes/min, timeout por op |

Modelo (comentários do fonte): token → header `X-Forge-Session` em toda
`/api` call; POST exige Origin loopback + `application/json`; chaves
sensíveis na blocklist de redact (`token|secret|password|cookie|…`).

## 3. API real

Prefixo `API_PREFIX = "/api/v1"`; respostas carregam
`correlation_id` + `data` + `error` estruturado (`PORTAL-*` codes).
`available.version: null` com `source: "offline — remote lookups
disabled"` — honesto, sem fingir lookup remoto.

## 4. Não testado aqui

- Navegação UI completa (headless); fluxos §6.3 (Graph Studio, Lab, etc.)
  requerem browser — registrado, não declarado como testado.
- `forge_session` na URL de boas-vindas: token transitório visível no
  log/histórico — risco baixo (loopback), documentar no security notes.
