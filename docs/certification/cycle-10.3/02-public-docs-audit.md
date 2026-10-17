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

Auditoria refeita contra os READMEs que viram `long_description` no PyPI
(os 7 pacotes com `readme =` após o fix do api-forge):

- **Apenas 1 link relativo em 7 READMEs**: `the-forge/README.md` →
  `docs/adr/0008-cli-name.md` → trocado por URL absoluta pinada na tag
  `v0.5.0`.
- 0 imagens relativas, 0 `src=` locais.
- Os "346 links" da auditoria anterior eram de **docs internos**, não dos
  READMEs publicados — o risco PyPI real era 1 link. Resolvido.

## 3. Metadados PyPI (§4.5)

Antes → depois (verificado por build `uv build` + leitura do METADATA):

| Pacote | classifiers | project.urls | readme | Dev Status |
|---|---|---|---|---|
| theforge-core | 0→7 | 0→5 | ok | **Beta** (0.5.x) |
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
