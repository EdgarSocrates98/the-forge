# Release 1 — Readiness final

**Estado: `PARTIALLY_PUBLISHED`** — aprovado pelo owner
("se estiver tudo certo, feito e os ci verde, pode considerar aprovado",
2026-10-16) e executado até onde as credenciais permitem:

- **Publicado (GitHub)**: tags `v*` + GitHub Releases nos 9 repos com
  wheel/sdist/tarball + `SHA256SUMS.txt` anexados. Verificação
  pós-release: wheel baixada do release `the-forge v0.5.0`, checksum
  conferido, instala em venv limpa → `theforge 0.5.0`.
- **npm publicado**: `theforge-cli@0.1.0` live em
  npmjs.com — verificado com install limpo do registry (`npm install
  theforge-cli` → `forge-cli --help`/`doctor` OK).
- **Pendente (registries)**: PyPI **não** publicado — sem
  credenciais (`~/.pypirc`/tokens ausentes; Trusted Publishing requer
  setup do owner). Artifacts prontos para `gh release download` →
  `twine upload` quando as credenciais existirem.
- **Promovido**: `forge-doctor-data 1.0.0rc1 → 1.0.0` (PR #46 mergeado,
  `c799eca`; rc-baseline re-selado com 2668 testes + cobertura medida).
- **Manifesto**: `ecosystem-compatibility.json` consistente com os
  nomes finais de distribuição e versões GA.

Data: 2026-10-16. Programa: `prompt_evo_release1.md`. Escopo executado:
Audit→Approve→Publish(GitHub+npm)→Verify; PyPI aguarda credenciais.

## Resumo executivo

- **9/9 repos** auditados na baseline (`baseline.md`), mains limpas,
  zero PRs abertos.
- **CI verde** nos SHAs exatos de release (`ci-matrix.md`) — inclui
  ladder completa `release-gates` revalidada pós-fix (`38923380792`).
- **7/7 pacotes Python** constroem sdist+wheel, instalam em venv limpa
  e respondem `--version` (`packaging.md`).
- **npm pack** do forge-cli + instalação real de 2 Forjas em
  workspace descartável (33.7s) — Gate 3 verde.
- **Portal** serve da wheel instalada com session token — Gate 4 verde.
- **Handoffs reais** reutilizados do ciclo 10.2 (código inalterado).
- **Community files 9/9** completos.

## Achados desta auditoria (corrigidos ou decididos)

| # | Severidade | Item | Estado |
|---|---|---|---|
| F-R1-1 | P0 | `theforge` PyPI ocupado; `the-forge` barrado por similar-name | ✅ `theforge-core` |
| F-R1-2 | P0 | `forge-cli` npm ocupado por terceiro | ✅ renomeado `theforge-cli` |
| F-R1-3 | P2 | 346 links relativos quebram no PyPI | ⏳ decisão owner |
| — | info | `apiforge` exige Python>=3.12 | documentado |
| — | info | Copilot not-tested; macOS sem runner | declarado |

## Mudanças desta branch (release-1/prep)

- the-forge: rename dist → `theforge-core` (PyPI rejeitou `the-forge`
  por similar-name ao existente `theforge`); docs de release completos.
- forge-cli: rename npm → `theforge-cli`; self-update usa novo nome.

## Pendências externas (bloqueiam Wave 11)

Ver `approval-checklist.md` — decisões de nome, versões, Trusted
Publishing config, autorização de publicação.
