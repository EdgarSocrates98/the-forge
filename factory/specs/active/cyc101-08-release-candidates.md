---
id: cyc101-08
title: release-candidates-supply-chain
status: active
created: 2026-10-15
owner: the-forge
scope: ecosystem
cycle: "10.1"
wave: 5
priority: p0
risk: medium
agent: devin
source: prompt_evo_cycle10.1.md §7 (GAP 05), §11 Wave 5
verification:
  - python scripts/check_gates.py --pytest
---

# Release candidates verificáveis por projeto — sem publicar

## Escopo

- §7.1 versionamento por repo: versão do pacote, CLI, contratos, assets,
  compat de hosts, changelog, git tags (preparar, não criar tag pública),
  release notes. Sem versões fictícias.
- §7.2 um RC independente por projeto (versões heterogêneas OK).
- §7.3 build: Python wheel+sdist, instalação em venv limpa sem checkout, smoke
  test; Portal: build de produção, instalação limpa, integridade de assets.
- §7.4 supply chain: SHA-256 dos artefatos, SBOM, deps, vulnerabilidades,
  licenças, proveniência, secrets ausentes, permissões de CI.
- §7.5 CI no commit exato: lint, typecheck, unit, contract, integration, E2E,
  security, package install, compatibility, RC — nunca reutilizar run antiga.
- §7.6 preencher a release matrix (9 projetos × Build/Testes/Segurança/
  Contratos/RC) em `docs/certification/cycle-10.1/release-matrix.md`.

## Respeitar

- Nada de PyPI/npm/marketplace/tags públicas — apenas artefatos locais + docs.
- doctor-api: versão 0.2.0 travada — RC sem bump sem rationale do dono.
- doctor-data: já em 1.0.0rc1 — RC existente é válido se build+checks passarem.

## Aceite

- Artefatos locais com SHA-256 + SBOM por repo, release matrix preenchida com
  evidência (não TBD) e pendências explícitas.
