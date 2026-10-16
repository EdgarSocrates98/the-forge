# Cycle 10.2 — GitHub Actions Security Hardening

## SHA-pinning (§4.2)
Todas as referências por tag convertidas para SHA imutável + comentário de
versão humana, resolvidos via API oficial de commits (não inventados):
checkout@v4→11d5960a, setup-python@v5→a26af69b, upload-artifact@v4→ea165f8d,
download-artifact@v4→d3f86a10, setup-node@v4→49933ea5 / @v7→949feb24,
checkout@v7→3d3c42e5, configure-pages@v5→983d7736, upload-pages-artifact@v3→56afc609,
deploy-pages@v4→d6db9016, dependency-review@v4→2031cfc0, attest-build-provenance@v4→4d101475,
action-gh-release@v2→3bb12739 / @v3→efb35369, cache@v4→0057852b,
gh-action-pypi-publish@release/v1→dc37677b, setup-uv@v6→d0cc045d,
azure/login@v2→7184910d, codeql-action/upload-sarif@v3→ce5e7eea.
Arquivos alterados: 16 workflows em 8 repos (the-forge já estava 100% pinado).

## Least privilege (§4.3)
`permissions: contents: read` adicionado a 4 workflows sem bloco
(forge-doctor-data benchmarks+ci, forge-portal ci, platform-forge ci).
Release workflows já tinham `contents: write` (+`id-token`/`attestations` onde OIDC).

## Auditoria (§4.1)
- `pull_request_target`: **zero** ocorrências no ecossistema.
- Secrets: só via `secrets.` em `with:`/`env:` (GITHUB_TOKEN, NPM_TOKEN,
  tokens de cross-repo) — nenhum echo/log direto.
- YAML: 100% válido pós-edição (yaml.safe_load em todos os arquivos).

## Push pendente
Token OAuth sem scope `workflow` → pushes de workflow aguardam credencial do
owner (`gh auth refresh -s workflow`). Commits locais em
`cycle-10.2/actions-hardening` nos 8 repos.
