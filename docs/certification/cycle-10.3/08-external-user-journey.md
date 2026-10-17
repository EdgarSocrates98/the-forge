# Cycle 10.3 — Wave 8: External User Journey (doc-only, medido)

Jornada simulada de usuário novo usando **apenas documentação pública**
(PyPI/npm/README) e artefatos publicados. Sem conhecimento interno.

## 8.1 Passo a passo executado

| # | Passo | Comando/ação | Resultado | Fricção |
|---|---|---|---|---|
| 1 | Encontrar o projeto | pypi.org/project/theforge-core | página existe, README renderiza | logo quebrado (path relativo `docs/assets/`) |
| 2 | Entender o propósito | README PyPI | claro: control plane + especialistas | tagline em PT — ok para audiência-alvo |
| 3 | Instalar Forge CLI | `npm i -g theforge-cli` / `npx theforge-cli` | OK — binário `forge-cli` funciona | README não diz que existe pacote npm — usuário precisa achar |
| 4 | Instalar forjas | `forge-cli install` | 23s, 7 componentes | **clone-only** — sem `pip install` path (gap conhecido) |
| 5 | Configurar host IA | `forge-cli hosts` | detecta 5 hosts, versões reais | nenhuma |
| 6 | Instalar uma forja direta | `pip install forge-doctor-api` | OK do PyPI público | — |
| 7 | Executar tarefa real | `forge-doctor-api scan ws/` num OpenAPI de teste | **findings reais**: OAS010 HIGH (3 ops sem auth), OAS020 INFO (sem tags), RELAPI008 LOW (sem idempotency) — `gate: PASS` | nenhuma — saída rica com rule_id + severity + evidence_ref |
| 8 | Explorar no Portal | `theforge portal` | serve, token na URL, `/api/v1` protegido | abre browser; headless precisa `--no-browser` + capturar token da URL |
| 9 | Atualizar/remover | `forge-cli update --check`, `uninstall` | funciona; backup em `.forge-cli/backups/` | nenhuma |

## 8.2 Fricções reais encontradas (com evidência)

**F-1 — PyPI README não ensinava `pip install`** (alto impacto) — ✅ corrigido
A página pública de `theforge-core` mostrava só instalação por checkout.
`pip install <dist>` agora lidera Install nos 7 READMEs. → **G-DOCS-1**.

**F-2 — Logo quebrado no PyPI** (baixo) — ✅ corrigido
7 imagens relativas → `raw.githubusercontent.com/.../<tag>/`. → **G-DOCS-2**.

**F-2b — ~350 links relativos quebrados** (achado pelo revisor) — ✅ corrigido
343 links + 7 imagens nos READMEs registry-bound eram 404 garantidos no PyPI.
Reescritos para absolutos tag-pinned, 0 unresolved. → **G-DOCS-4**.

**F-3 — forge-cli é clone-only** (conhecido, confirmado)
Instalar forjas exige `git` + build local; o caminho `pip install` existe nos
registries mas o CLI não o usa. Já registrado como feature gap — spec futura.
→ **G-CLI-1**.

**F-4 — `apiforge-mcp` sem extra → traceback cru** — ✅ corrigido
`except ImportError` não cobria o `RuntimeError` de `build_server` — a
mensagem guiada era inalcançável. Agora imprime `AF-MCP-UNAVAILABLE` + unlock,
exit 2. → **G-DX-1**.

**F-5 — npm package não mencionado nos READMEs das forjas** — parcial
`theforge-cli` agora é referenciado no README do the-forge. → **G-DOCS-3**.

## 8.3 O que funcionou sem fricção

- Scan real produz findings **acionáveis e rastreáveis** (rule_id, severity,
  evidence_ref) — a promessa central do produto se cumpre da wheel.
- `forge-cli hosts` detecta e reporta honestamente (autenticado vs não
  verificado vs não detectado).
- Lifecycle completo: install/status/update/reinstall/rollback/uninstall —
  tudo funcional, com backups.
- Portal: segurança real (403 sem token), API `/api/v1` viva da wheel.
- MCP: 154 tools + call real — protocolo completo.
- Lab federado: 137 cenários determinísticos.

## 8.4 Avaliação first-use honesta

Um usuário **consegue**: achar, instalar e obter findings verificáveis —
a trilha central funciona. As fricções são **de descoberta** (o caminho pip
existe mas não é ensinado; o CLI npm não é referenciado) e **uma falsa falha
de lab** já corrigida — não de quebra funcional. Sem métricas de tempo
inventadas: onde medido, consta; onde não, não consta.
