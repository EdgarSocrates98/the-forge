# Baseline — 2026-10-15

Captura sobre `main` dos nove repositórios em `~/Documentos/projetos/forjas/`. Coleta: `git rev-parse`, `pyproject.toml`/`package.json`, `.github/workflows/`. Estado de instalação prévio: `.forge-cli/state.json` (8/9 repos "validated" via setup.sh/npm ci em 2026-10-15).

## Inventário

| Repo | SHA | Versão | Build | Instalação | Tags | Workflows CI |
|---|---|---|---|---|---|---|
| the-forge | `68ddcbd` | 0.5.0 | pyproject | setup.sh (editable) | 0 | ci, compat, ecosystem-real, provider-surface-drift, release-compat |
| forge-cli | `15d9e44` | 0.1.0 | package.json | — | 0 | ci, release |
| forge-portal | `4a916d2` | 0.1.0 | package.json | npm ci | 0 | ci |
| api-forge | `d059598` | 0.1.0 | pyproject | setup.sh (editable) | 0 | api-change-control, change-control-pages, ci |
| platform-forge | `4376732` | 0.1.0 | pyproject | setup.sh (editable) | 0 | ci |
| spark-forge-aws | `5edaf29` | 0.5.0 | pyproject | setup.sh (editable) | 0 | ci, refresh-knowledge, release |
| spark-forge-azure | `75a64cb` | 0.1.0 | pyproject | setup.sh (editable) | 0 | ci, scheduled |
| forge-doctor-data | `a927c3c` | **1.0.0rc1** | pyproject | setup.sh (editable) | 0 | benchmarks, ci, release, security |
| forge-doctor-api | `83cfd22` | 0.2.0 | pyproject | setup.sh (editable) | 0 | doctor-scan, quality, release |

## Achados (evidência)

1. **Zero tags de release em todos os repos** (`git tag -l` = 0). Nenhuma versão publicada como release Git.
2. ~~forge-portal `version: 0.0.0` placeholder~~ — **resolvido 2026-10-15**: declarada `0.1.0`.
3. **forge-doctor-data em `1.0.0rc1`** — janela de RC ativa; doctor-api declara RC discipline (`docs/rc-discipline.md`, versão 0.2.0).
4. **platform-forge: 9 arquivos com `/home/edgar` hardcoded** (`git grep -l /home/edgar`) — dependência de caminho de desenvolvedor, viola §8.2.
5. **Instalação = checkout + `setup.sh` editable** em todos os Python repos — nenhum artefato wheel/sdist publicado; `python -m build` suportado (build-system presente) mas não exercitado como distribuição.
6. **CI existente é desigual**: the-forge já tem `compat.yml`/`release-compat.yml`; doctor-data tem `benchmarks.yml`/`security.yml`; platform-forge e forge-portal só `ci.yml`.
7. **`Loop-Factory/` ausente do workspace** — `forge-doctor-api/AGENTS.md` referencia `../Loop-Factory/bin/loop-factory` (referência obsoleta).
8. **`docs/homologation/` existe** — relatório anterior disponível para comparação de bloqueios (revisão detalhada pendente).

## Não verificado (honesto)

- Conteúdo dos workflows (gates reais vs. nomes).
- `docs/homologation/` — bloqueios anteriores ainda não comparados linha a linha.
- Testes de instalação de pacote (wheel install em venv limpo) — não executado nesta captura.
- Publicação atual em registries: nenhuma evidência de artefato publicado (PyPI/npm).
