# Cycle 10.3 — Patch Release Plan

Proposta de patches onde existe mudança **distribuível** que justifica nova
versão. Nada publicado sem autorização — isto é preparação, não execução.

## Patches propostos

### theforge-core 0.5.0 → **0.5.1** (docs/metadata)

Conteúdo: PR #74 — classifiers+keywords+urls no metadata; link relativo
corrigido. **Justificativa**: a página PyPI publicada está sem classifiers e
renderiza link quebrado — só se corrige re-publicando. **Também candidato**:
G-DOCS-1 (seção `pip install` no README) e G-DOCS-2 (logo absoluto) — recomendo
adicionar ao mesmo patch antes de publicar. Tag proposta: `v0.5.1`.

### apiforge-af 0.1.0 → **0.1.1** (docs/metadata + resolução G-REG-2)

Conteúdo: PR #81 — rename `apiforge→apiforge-af` em docs/runtime strings +
metadata completo. **Justificativa**: PyPI page sem classifiers/urls; e o
GitHub Release v0.1.0 carrega assets `apiforge-*` stale (G-REG-2) — uma tag
nova publica artifacts `apiforge_af-*` e fecha as duas coisas.
Tag proposta: `v0.1.1`.

### forge-doctor-data 1.0.0 → **1.0.1** (metadata)

Conteúdo: PR #48 — project.urls + correção de classifier
(`Development Status` Alpha→Production/Stable num 1.0.0 é incoerente).
**Justificativa**: metadata publicado errado num release de major.
Tag proposta: `v1.0.1`.

### forge-doctor-api 0.2.0 → **0.2.1** (metadata + lab fix)

Conteúdo: PR #60 (urls/classifiers/keywords) + PR #61 (emissor lab
skip→skipped). O fix do emissor é repo-tooling (não vai na wheel), mas o
metadata justifica o patch. Tag proposta: `v0.2.1`.

### G-DX-1 — apiforge-af: mensagem guiada p/ extra mcp (acoplar a 0.1.1)

Pequeno: catch em `apiforge-mcp` → "requires extra: pip install
'apiforge-af[mcp]'". Barato, melhora DevEx. Recomendo incluir em 0.1.1.

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
2. Bump de versão em `pyproject.toml`/`package.json` + changelog entry.
3. Tag `v*` na main → GitHub Release com artifacts + SHA256SUMS.
4. `gh workflow run publish-pypi` (OIDC, attestation PEP 740) /
   `publish-npm` (provenance).
5. Verificar `pip install <pkg>==<nova>` limpo + smoke do CLI.
6. Atualizar release-matrix e fechar itens do gap register.

## Não-publicar

- `the-forge`, `api-forge`, `platform-forge`, `sparkforge-aws`,
  `sparkforge-azure`, `forge-doctor-data`, `forge-doctor-api` **não** precisam
  todos de patch — só os 4 listados. O resto fica como está.
- forge-portal: vendored — sai dentro de qualquer próxima theforge-core.
