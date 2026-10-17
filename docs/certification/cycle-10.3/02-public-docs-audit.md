# Cycle 10.3 — Wave 2: Documentation & public metadata polish

Data: 2026-10-16.

## 1. Nomes de distribuição corrigidos (§4.3)

| Repo | Arquivo(s) | Correção |
|---|---|---|
| api-forge | 6× `knowledge/*/troubleshooting.md` | `pip install apiforge[mcp]` → `apiforge-af[mcp]` |
| api-forge | `src/collectors/{apigateway,messaging,graph_explain,lambda_}.py`, `tui/fallback.py` | mensagens de erro → `apiforge-af[aws|tui]` |
| api-forge | `README.md`, `docs/guides/PORTABLE_DISTRIBUTION`, `docs/learn/recipes/primeiro-uso`, `docs/plans/mcp-funnel`, `docs/catalog-contract` | idem |
| the-forge | `adapters/apiforge/README.md` | `pip install apiforge` → `apiforge-af` |

Docs históricos (`cycle-10-decisions`, `packaging-matrix`) mantidos
inalterados — pré-publicação, preservados por §4.2.

## 2. Links relativos em READMEs (§4.4)

> **Errata 2026-10-17** — a versão anterior desta seção certificava "1 link
> relativo / 0 imagens". Recontagem com parser dedicado (markdown + `<img>`,
> fenced code excluído) provou o contrário: **~350 relativos**. A versão
> original desta seção estava errada — corrigido aqui e implementado abaixo.

Contagem real nos 7 READMEs registry-bound (script `/tmp/fix_links.py`,
verificação de cada alvo em disco):

| Repo | md links | `<img>` | Tag-pin aplicado |
|---|---|---|---|
| the-forge | 79 | 1 | v0.5.0 |
| api-forge | 56 | 1 | v0.1.0 |
| platform-forge | 66 | 1 | v0.1.0 |
| spark-forge-aws | 86 | 1 | v0.5.0 |
| spark-forge-azure | 8 | 1 | v0.1.0 |
| forge-doctor-data | 17 | 1 | v1.0.0 |
| forge-doctor-api | 31 | 1 | v0.2.0 |
| **total** | **343** | **7** | **0 unresolved** |

Regra aplicada: arquivo → `…/blob/<tag>/`, diretório → `…/tree/<tag>/`,
`<img src>` → `raw.githubusercontent.com/<org>/<repo>/<tag>/` (PyPI não serve
`blob/` como imagem). Âncoras e query preservadas. **0 alvos faltantes** —
todo caminho existe no checkout.

**Decisão de pin**: links apontam para a tag da release publicada — o que o
PyPI serve naquele release corresponde ao doc daquela versão. Chore de
release: re-pin ao bump (documentado no patch plan).

O PyPI **não** reescreve links relativos (npm reescreve via `repository` —
forge-cli está isento). Cada link era um 404 garantido na página do pacote.

Também corrigido nesta rodada: `docs/real-providers.md` usava o dist morto
`apiforge` em 4 posições (support table, specialist list, `pip install`) →
`apiforge-af` (nomes de módulo/CLI `apiforge` preservados — existem).

## 3. Metadados PyPI (§4.5)

Antes → depois (verificado por build `uv build` + leitura do METADATA):

| Pacote | classifiers | project.urls | readme | Dev Status |
|---|---|---|---|---|
| theforge-core | 0→6 | 0→5 | ok | **Beta** (0.5.x) |
| apiforge-af | 0→6 | 0→5 | 0→ok | **Alpha** (0.1.0) |
| forge-doctor-api | 4→7 | 0→6 | ok | **Beta** |
| forge-doctor-data | 9→9 | 2→5 | ok | **Alpha→Beta** ⚠ |

⚠ `forge-doctor-data 1.0.0`: classifier subiu de Alpha→Beta — GA com
rc-baseline congelado (2668 testes, contracts sealed) justifica Beta;
"Production/Stable" ainda seria overclaim sem evidência de adoção.
**Decisão do mantenedor** — flag explícita no PR.

Coerência pós-fix: 0.5.x/1.0.0 → Beta; 0.1.0/0.2.0 → Alpha/Beta conforme
maturidade declarada (apiforge-af Alpha, doctor-api Beta, azure Alpha).

## 4. Bilíngue (§4.6)

- `docs/dogfooding.md`, `FINAL-RELEASE-READINESS.md` já refletem
  `PUBLISHED`/`theforge-core` — conferido.
- Sem textos mistos detectados nas superfícies públicas editadas.

## 5. Pendências Wave 2

- PRs abertos nos 4 repos alterados (revisão do mantenedor).
- Traduções literais menores nos docs internos — fora da superfície
  pública; registrado, não bloqueante.
