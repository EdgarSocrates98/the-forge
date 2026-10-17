# Cycle 10.3 — Patch Release Plan

Proposta de patches onde existe mudança **distribuível** que justifica nova
versão. Nada publicado sem autorização — isto é preparação, não execução.

## Patches propostos

### theforge-core 0.5.0 → **0.5.1** (docs/metadata)

Conteúdo: PR #74 — classifiers+keywords+urls no metadata (3.13 removido,
alinhado ao floor testado); 79 links + 1 img do README → absolutos
tag-pinned; `pip install theforge-core` + referência ao `theforge-cli` npm;
`real-providers.md` com dist `apiforge-af`. **Justificativa**: a página PyPI
publicada está sem classifiers e renderiza ~80 links/imagens quebrados — só
se corrige re-publicando. Tag proposta: `v0.5.1`.

### apiforge-af 0.1.0 → **0.1.1** (docs/metadata + mcp fix + resolução G-REG-2)

Conteúdo: PR #81 — rename `apiforge→apiforge-af` completo (inclui
`mcp/main.py` + `__init__.py` unlock strings); 56 links + 1 img absolutos;
`pip install apiforge-af` na Install; **G-DX-1**: `apiforge-mcp` sem extra
agora imprime `AF-MCP-UNAVAILABLE` + unlock, exit 2 (era traceback cru —
`except ImportError` não cobria o `RuntimeError` do build_server).
**Justificativa**: PyPI page sem classifiers/urls e com links quebrados; o
GitHub Release v0.1.0 carrega assets `apiforge-*` stale (G-REG-2) — tag nova
publica artifacts `apiforge_af-*` e fecha tudo. Tag proposta: `v0.1.1`.

### platformforge 0.1.0 → **0.1.1** (docs)

Conteúdo: PR #46 — 66 links + 1 img absolutos; `pip install platformforge`
na Install. Tag proposta: `v0.1.1`.

### sparkforge-aws 0.5.0 → **0.5.1** (docs)

Conteúdo: PR #168 — 86 links + 1 img absolutos (README já tinha
`pip install sparkforge-aws`). Tag proposta: `v0.5.1`.

### sparkforge-azure 0.1.0 → **0.1.1** (docs)

Conteúdo: PR #62 — 8 links + 1 img absolutos + linha `pip install
sparkforge-azure`. Tag proposta: `v0.1.1`.

### forge-doctor-data 1.0.0 → **1.0.1** (metadata + docs)

Conteúdo: PR #48 — project.urls + correção de classifier
(`Development Status` Alpha→Beta — ainda é um 1.0.0 jovem; Alpha num release
de major era incoerente) + 17 links + 1 img absolutos (README já tinha
`pipx install forge-doctor-data`).
**Justificativa**: metadata publicado errado num release de major.
Tag proposta: `v1.0.1`.

### forge-doctor-api 0.2.0 → **0.2.1** (metadata + docs + lab fix)

Conteúdo: PR #60 (urls/classifiers/keywords + 31 links + 1 img absolutos +
`pip install forge-doctor-api` na Install) + PR #61 (emissor lab
skip→skipped). O fix do emissor é repo-tooling (não vai na wheel), mas o
metadata+docs justificam o patch. Tag proposta: `v0.2.1`.

## Decisões pendentes (não são patch ainda)

| Item | Opções |
|---|---|
| G-MATRIX-1 (pf/sfaws/sfaz floor 3.10) | A) ampliar matrix CI pra 3.10 (sem release) · B) `requires-python>=3.12/3.11` (patch de metadata) — recomendo B se o suporte a 3.10 não for intenção real |
| G-CLI-1 (forge-cli clone-only) | spec de feature cyc11 — novo minor, não patch |
| G-LAB-1 (`{python}` do collect) | decisão de design no the-forge — documentar ou apontar pro venv |
| G-HOME-1/G-WIKI-1 | settings GitHub — sem release |
| G-SEC-1 | rotação do token — ação do dono |

## Checklist de publicação (quando autorizado)

1. Merge dos PRs de correção (CI verde confirmado).
2. Bump de versão em `pyproject.toml` + changelog entry.
3. **Re-pin dos links do README** para a nova tag (chore recorrente — os
   links apontam para a tag da release que os serve).
4. Tag `v*` na main → GitHub Release com artifacts + SHA256SUMS.
5. `gh workflow run publish-pypi` (OIDC, attestation PEP 740) /
   `publish-npm` (provenance).
6. Verificar `pip install <pkg>==<nova>` limpo + smoke do CLI + amostra de
   links na página PyPI renderizada.
7. Atualizar release-matrix e fechar itens do gap register.

## Quem não recebe versão nova

- **Todos os 7 pacotes Python têm mudança distribuível** (README + metadata
  vão na wheel/sdist) — justificam patch cada um.
- `forge-cli` (npm) e `forge-portal` (vendored) ficam como estão —
  forge-portal sai dentro de qualquer próxima theforge-core.
