# Cycle 11.2 — PyPI patch plans (P1-006)

Escopo: `docs/releasing/pypi-patch-plan.md` por repo — preparados nos 6
PRs de matrix/metadata, todos MERGED. Nada publica/taggeia/faz upload —
cada plano é checklist para o mantenedor.

## Comandos executados

```text
sed -n '/## What changes/,/## Blockers/p' docs/releasing/pypi-patch-plan.md  # por repo
gh pr view <n> --json state,mergeCommit
```

## Status por repo

| Repo | PR | SHA merge | Próximo release proposto | Conteúdo do patch |
|---|---|---|---|---|
| platform-forge | #54 MERGED | 2a9bf44 | `0.1.1` | classifier 3.13 (CI já cobria; metadata atrasada). Sem mudança de código. |
| api-forge | #84 MERGED | cb13bdb | `0.1.1` | CI matrix → 3.12–3.14 (validate + windows-parity); classifiers 3.13/3.14. Sem mudança de runtime. |
| spark-forge-aws | #172 MERGED | 4a70021 | `0.5.1` | CI schedule/dispatch → 3.10–3.14; classifiers 3.13/3.14; project.urls Documentation+Changelog; locks py3.13/py3.14 via `gen_lock.py`. |
| spark-forge-azure | #65 MERGED | 3ed7e75 | `0.1.1` | CI `full` → 3.10–3.14 ambos OS; project.urls Documentation+Changelog. Classifiers já corretos. |
| forge-doctor-data | #51 MERGED | 3f2fe0e | `1.0.1` (se houver motivo) | **Nada a republicar** — metadata coerente; URLs ausentes na página PyPI se autocorrigem no próximo upload. Plano = checklist só. |
| forge-doctor-api | #64 MERGED | beb0e08 | `0.2.1` | plano de patch + metadata; native install (#65) é conteúdo separado e maior que patch. |

Sem drift de versão em nenhum repo (PyPI = pyproject = tag = GitHub
release, auditado em cada plano).

## Checklist do mantenedor (padrão comum)

- CI verde no PR **e** na leg schedule/dispatch onde aplicável
- `gen_lock.py --check` / `lock_audit.py` / gates específicos por repo
- bump de `version` em `pyproject.toml` no release
- tag + publish via `publish-pypi.yml`/`release.yml` existentes
- verificar página PyPI (classifiers + project.urls)

`Blockers: None` nos 6 planos.

## Veredito

FIXED_UNVERIFIED — planos escritos, mergeados, com evidência local de
smoke (builds de wheel + `--help` nos interpretadores novos); nenhum
release cortado — depende de autorização do mantenedor.

## Risco residual

Página PyPI segue com metadata antiga até o próximo upload (esperado).
`publish-pypi.yml` dos repos Python não passou pelo mesmo hardening
observável do `publish-npm.yml` (OIDC/provenance PyPI não auditado neste
ciclo).
