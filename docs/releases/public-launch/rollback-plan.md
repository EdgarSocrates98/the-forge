# Release 1 — Política de reversão & hotfix

## Premissas de irreversibilidade

- PyPI **não permite re-upload** do mesmo nome+versão — correção é
  patch release (`0.5.0 → 0.5.1`) ou `yank`.
- npm permite `unpublish` só em janela estreita (72h) e é desaconselhado;
  correção real = patch ou `deprecate`.
- Tags git públicas não se movem — nunca reescrever uma tag publicada.
- GitHub Releases podem ser editadas (notas/assets) mas a tag fica.

## Política

1. **Versão ruim publicada** → `yank`/`deprecate` + patch release com
   a correção. Nunca deletar para esconder.
2. **Hotfix** → branch `hotfix/<ver>` do tag publicado, CI verde,
   bump patch, publicar.
3. **Rollback de instalação** → usuário: `pip install <dist>==<prev>`
   / `npm i -g theforge-cli@<prev>`; forge-cli: `rollback <forja>`.
4. **Vulnerabilidade** → SECURITY.md + GitHub Security Advisory +
   patch + comunicação pública (não silenciosa).
5. **Integridade histórica** → releases, tags, checksums e receipts
   permanecem — errata documentada na release note.
