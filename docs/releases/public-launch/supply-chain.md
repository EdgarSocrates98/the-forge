# Release 1 — Supply chain & segurança

## GitHub Actions (verificado 2026-10-16, ciclo 10.2 + fix pós-merge)

- 16 workflows nos 9 repos: **100% `uses:` pinados a SHAs imutáveis**
  (verificados contra `git ls-remote` upstream em cycle-10.2).
- `permissions: contents: read` em todos os workflows read-only;
  write restrito a jobs de publish/release onde necessário.
- Zero `pull_request_target`; secrets nunca interpolados em `run:`.
- fix pós-merge `20f0105`: SHA256SUMS com nomes relativos a `dist/`
  (verificado verde no run 38923380792).

## Dependências

- Core the-forge: **zero dependências de runtime** (stdlib-only,
  invariante arquitetural — testado por `test_packaging.py`).
- Especialistas: pin ranges declarados; nenhum CVE aberto detectado na
  auditoria de deps do cycle-10.2 (`security-hardening.md`).
- SBOM: `sbom.cdx.json` gerado pela ladder de release-gates (artefato CI).

## Secrets & conteúdo de artefatos

- Listagem de sdists/wheels: nenhum `.env`, chave, ou path pessoal
  embalado. `.agents/` no sdist contém apenas `skills/` (conteúdo de
  produto, verificado em F-RC-1).
- Fixtures de teste com credenciais falsas permanecem marcados como
  fixtures (auditoria cycle-10.1 `security-report.md`).

## Trusted Publishing (plano)

- PyPI: OIDC Trusted Publisher por repo → job `publish` com
  `permissions: id-token: write` isolado; sem `PYPI_TOKEN` em secrets.
- npm: `npm publish --provenance` (OIDC) ou token granular de
  granularidade mínima, expiração curta.
- Pendência externa: mantenedor configura Trusted Publisher no PyPI/npm
  (ação humana, listada em `approval-checklist.md`).

## Políticas de não-reversão

Tags públicas e versões em registries são efetivamente permanentes —
ver `rollback-plan.md`.
