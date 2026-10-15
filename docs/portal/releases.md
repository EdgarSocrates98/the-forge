# Releases & compatibilidade

## Política

- Compatibilidade declara-se por manifesto: `ecosystem-compatibility.json`
  (schema `forge/EcosystemCompatibility/v1`) — veja
  `docs/programs/ecosystem-2026/versioning-policy.md` e
  `docs/programs/ecosystem-2026/compatibility-matrix.md`.
- Cada repo tem `CHANGELOG.md`; release notes são publicadas por release
  no GitHub (preparação apenas — publicação exige sign-off do dono, D5 de
  `cycle-10-decisions.md`).
- RC windows ativas: `forge-doctor-data` 1.0.0rc1, `forge-doctor-api` 0.2.0
  — `docs/rc-discipline.md` de cada repo rege exceções.

## Verificar compatibilidade instalada

```bash
forge-cli update --check --json   # envelope {manifest, repos} + installed_compat
theforge doctor                   # ambiente + providers
```

## Política de suporte

Veja `SUPPORT.md` na raiz de cada repositório — canal único: GitHub Issues
do repo correspondente.
