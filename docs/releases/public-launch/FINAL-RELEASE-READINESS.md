# Release 1 — Readiness final

**Estado: `READY_FOR_APPROVAL`** — nada publicado; aprovação humana
pendente.

Data: 2026-10-16. Programa: `prompt_evo_release1.md`. Escopo: preparar
(Audit→Stage) — publicação só após autorização explícita.

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
| F-R1-1 | P0 | `theforge` PyPI ocupado por terceiro | ✅ renomeado `the-forge` |
| F-R1-2 | P0 | `forge-cli` npm ocupado por terceiro | ✅ renomeado `theforge-cli` |
| F-R1-3 | P2 | 346 links relativos quebram no PyPI | ⏳ decisão owner |
| — | info | `apiforge` exige Python>=3.12 | documentado |
| — | info | Copilot not-tested; macOS sem runner | declarado |

## Mudanças desta branch (release-1/prep)

- the-forge: rename dist → `the-forge`; docs de release completos.
- forge-cli: rename npm → `theforge-cli`; self-update usa novo nome.

## Pendências externas (bloqueiam Wave 11)

Ver `approval-checklist.md` — decisões de nome, versões, Trusted
Publishing config, autorização de publicação.
