# Cycle 11.2 — PyPI patch plans (P1-006) + auditoria 11.2.1

Escopo: `docs/releasing/pypi-patch-plan.md` por repo — preparados nos 6
PRs de matrix/metadata, todos MERGED. Nada publica/taggeia/faz upload —
cada plano é checklist para o mantenedor.

## Comandos executados

```text
sed -n '/## What changes/,/## Blockers/p' docs/releasing/pypi-patch-plan.md  # por repo
gh pr view <n> --json state,mergeCommit
```

## Status por repo (11.2)

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

---

# Re-auditoria Cycle 11.2.1 (§11 + §5.5-analog PyPI)

Captura 2026-10-17 (~21:50Z). Fonte de build: `git archive HEAD` de cada
`origin/main` — nenhum artefato construído dentro das working trees.

## Comandos executados (11.2.1)

```text
# reconciliação (todos limpos em main, sem rebase em curso)
for r in the-forge api-forge platform-forge spark-forge-aws spark-forge-azure forge-doctor-data forge-doctor-api; do
  git -C $r checkout main && git -C $r pull
done

# registry — nenhum patch 0.x.1/1.0.1 publicado
curl -s https://pypi.org/pypi/<pkg>/json | jq '.info.version, (.releases|keys)'

# toolchain de auditoria (scratch, fora dos repos)
/usr/bin/python3 -m venv /tmp/c1121/buildenv
/tmp/c1121/buildenv/bin/pip install --quiet --upgrade pip build twine   # build 1.6.1, twine 7.0.0

# por repo: fonte limpa → sdist+wheel → wheel-from-sdist → venv limpa → smoke → twine → sha256
git -C $r archive HEAD | tar -x -C /tmp/c1121/src/$r
(cd /tmp/c1121/src/$r && /tmp/c1121/buildenv/bin/python -m build --outdir /tmp/c1121/dist/$r)
tar -xzf /tmp/c1121/dist/$r/*.tar.gz -C /tmp/c1121/sdist-unpack/$r
/tmp/c1121/buildenv/bin/python -m build --wheel --outdir /tmp/c1121/dist-from-sdist/$r /tmp/c1121/sdist-unpack/$r/<pkg>-<ver>
/usr/bin/python3 -m venv /tmp/c1121/venv/<pkg> && /tmp/c1121/venv/<pkg>/bin/pip install --quiet <wheel>
/tmp/c1121/venv/<pkg>/bin/<cli> --version && /tmp/c1121/venv/<pkg>/bin/<cli> --help
/tmp/c1121/buildenv/bin/twine check /tmp/c1121/dist/$r/*
sha256sum /tmp/c1121/dist/$r/*

# workflow audit
md5sum $r/.github/workflows/publish-pypi.yml   # f969a8505298ffe9a48e42c57c4df6b1 nos 7 — byte-identical
gh api repos/<owner>/<repo>/environments
gh run list --branch main --limit 4
```

## Matriz de artefatos (build 11.2.1)

Backend isolado por `python -m build` (hatchling 1.32.4; poetry-core nos
dois forge-doctor). `wheel (sdist)` = wheel reconstruída a partir do
sdist desempacotado — **sha256 byte-identical à wheel direta nos 7
pacotes** (reprodutibilidade do payload sdist→wheel).

| Pacote | main SHA | sdist + wheel | wheel (sdist) | clean-venv install | CLI smoke | twine check |
|---|---|---|---|---|---|---|
| theforge-core 0.5.0 | 073b95b | OK | idêntica | OK | `theforge 0.5.0`, `--help` 29 verbos | PASSED ×2 |
| apiforge-af 0.1.0 | a775bda | OK | idêntica | OK | `apiforge 0.1.0`, `--help` (typer) | PASSED ×2 |
| platformforge 0.1.0 | dcdd6b8 | OK | idêntica | OK | `platformforge 0.1.0`, `--help` 56 verbos | PASSED ×2 |
| sparkforge-aws 0.5.0 | 7ba3863 | OK | idêntica | OK | `sparkforge-aws 0.5.0`, `--help` 68 verbos | PASSED ×2 |
| sparkforge-azure 0.1.0 | 4f49426 | OK | idêntica | OK | `sparkforge-azure 0.1.0`, `--help` | PASSED ×2 |
| forge-doctor-data 1.0.0 | 1abae68 | OK | idêntica | OK | `forge-doctor-data 1.0.0`, `--help` | PASSED ×2 |
| forge-doctor-api 0.2.0 | 64fe467 | OK | idêntica | OK | `forge-doctor-api 0.2.0`, `--help` | PASSED ×2 |

## SHA-256 dos artefatos (captura 11.2.1)

```text
917a498319513de104f5d37c1222d8a414bd994702ceabda508d801604435986  theforge_core-0.5.0-py3-none-any.whl
31b666045db2d3e193f2d54f8796762f2ca7153d21faa0c78c4ce7f95db2815d  theforge_core-0.5.0.tar.gz
12b0a01ccc1be6f9a7bbe23ef80a1386b843b3b796f28feaba84d9bace9cec38  apiforge_af-0.1.0-py3-none-any.whl
1d7d07691d2240536043614f31018bd3c030302a32ca1df7a2d54d074c1c70f3  apiforge_af-0.1.0.tar.gz
10a4cd605d8796da98446db1bdb4aaa8239478bfae2194263d9c5b7f2260123e  platformforge-0.1.0-py3-none-any.whl
b5b1f513fd277f98b8eb22709141424b5bce8411a8f68fe5b401e8d87a72ce9a  platformforge-0.1.0.tar.gz
3a4a70bed4d4ab8378810a63d0dc12710dffaf06806fd6a00b7b94e075d0a424  sparkforge_aws-0.5.0-py3-none-any.whl
17aa1306cd97a609e8aff5999cae775e167aee34c4045979957bc028929995c2  sparkforge_aws-0.5.0.tar.gz
d0817766b32aa0c581f47e3360cf61f8e39a28cc3f6c0e6d5655b5f4678ecc5b  sparkforge_azure-0.1.0-py3-none-any.whl
b28498718d32fcb3da3a0341733c0213efc2b9cf863e93359e85d8b1f1bb06a8  sparkforge_azure-0.1.0.tar.gz
dfdeb1f7fedace83a95c2aa946005df68b8998d25cf47a0fcbc3f39d5c752876  forge_doctor_data-1.0.0-py3-none-any.whl
572728ea1bb09de147b744d5be5a4736e890611fa1747246d125c5784c060ea6  forge_doctor_data-1.0.0.tar.gz
76b230e420152c59aae7c033623a68a27dce5ef66dd036f52e25ab2e3557f0f8  forge_doctor_api-0.2.0-py3-none-any.whl
35edc3bb82218493f71e2e5f62922aa83c48349ecddb94228dbfcfe94c9a3c4a  forge_doctor_api-0.2.0.tar.gz
```

## Metadata observado nas wheels

| Pacote | Classifiers Python | License | project.urls | vs PyPI publicado |
|---|---|---|---|---|
| theforge-core 0.5.0 | 3.11–3.12 | `License: MIT` (legacy) + classifier | completos | sem patch plan próprio — gap de housekeeping |
| apiforge-af 0.1.0 | 3.12–3.14 | `License: MIT License` | completos | PyPI mostra só 3.12 → patch 0.1.1 propaga |
| platformforge 0.1.0 | 3.10–3.13 | `License: MIT License` | completos | PyPI mostra 3.10–3.12 → patch 0.1.1 propaga |
| sparkforge-aws 0.5.0 | 3.10–3.14 | `License: MIT License` | completos (+Doc+Changelog) | PyPI 0.5.0 sem novas URLs → patch 0.5.1 propaga |
| sparkforge-azure 0.1.0 | 3.10–3.14 | `License: MIT License` | completos | PyPI 0.1.0 sem Doc/Changelog → patch 0.1.1 propaga |
| forge-doctor-data 1.0.0 | 3.11–3.13 | `License-Expression: MIT` (SPDX) | completos | PyPI sem Homepage/Doc/Issues — autocorrige no próximo upload |
| forge-doctor-api 0.2.0 | 3.11–3.13 | `License-Expression: MIT` (SPDX — fix de #64 já no main) | completos | PyPI 0.2.0 mostra `License:` legacy + URLs vazias → patch 0.2.1 propaga |

## SBOM / provenance tooling por repo

| Repo | Ferramenta | Artefato |
|---|---|---|
| the-forge | — | nenhum gerador SBOM localizado |
| api-forge | `scripts/sbom.py` (+ `tests/scripts/test_sbom.py`) | gerador; artefato não conferido nesta passagem |
| platform-forge | `platformforge/security/sbom.py` | `docs/freeze/SBOM.cdx.json` congelado |
| spark-forge-aws | `scripts/gen_sbom.py` (+ locks por minor) | gerador |
| spark-forge-azure | — | `evals/parity/sbom.cdx.json` (artefato de eval) |
| forge-doctor-data | `tools/release_candidate.py` → `core.sbom.build_sbom` (CycloneDX 1.5) | `dist/sbom.json` no release |
| forge-doctor-api | `factory/sbom.py` (CycloneDX 1.5, gate `--check`) | `factory/artifacts/sbom.cdx.json`; `release.yml` gera `dist/sbom.cdx.json` |

## Auditoria `publish-pypi.yml` (8 controles §11.5)

Os 7 arquivos são **byte-identical** (`md5 f969a8505298ffe9a48e42c57c4df6b1`):
trigger `workflow_dispatch` só; top-level `permissions: contents: read`;
job `pypi` com `if: true`, `id-token: write`, `attestations: write`;
steps checkout@v7-SHA → setup-python@v5-SHA → `python -m build` →
`pypa/gh-action-pypi-publish@SHA` com `attestations: true`.

| Controle | Veredito | Evidência |
|---|---|---|
| SHA binding | ✅ PASS | `checkout@3d3c42e5…` (v7), `setup-python@a26af69b…` (v5), `gh-action-pypi-publish@dc37677b…` — todos 40-char SHA |
| Environment approval | ❌ GAP | job sem `environment:`; comentário registra publisher PyPI com `environment: (vazio)`; `gh api repos/*/environments` — nenhum environment `pypi`/release existe nos 7 repos (api-forge tem só `github-pages`, 0 reviewers) |
| Version gate | ❌ GAP | `if: true`, dispatch sem inputs; nenhum check pyproject↔tag↔registry. Mitigação parcial fora do caminho PyPI: `release.yml` de spark-forge-aws tem step "Tag agrees with the package version"; forge-doctor-data roda `verify_release.py --dist`; forge-doctor-api roda `version_gate.py` — nenhum deles protege `publish-pypi.yml` |
| Sem token persistente | ✅ PASS | nenhum `password:`/`secrets.*PYPI*`; OIDC-only |
| OIDC trusted publishing | ✅ PASS | `id-token: write` + `gh-action-pypi-publish`; comentário afirma publisher registrado — binding externo não verificável do repo (limite da auditoria) |
| Artifact immutability | ⚠ PARCIAL | PyPI rejeita re-upload de filename (imutabilidade server-side). Mas o workflow **rebuilda** no job de publish — o artefato publicado não é o mesmo validado em CI (diverge do desenho npm endurecido: artefato único carregado validate→publish); sem SHA-256 registrado pré-upload no caminho PyPI |
| Provenance/attestation | ✅ PASS | `attestations: write` + `attestations: true` → PEP 740. Semântica fail-hard não exercida (nenhum dispatch observado) |
| Post-publish smoke | ❌ GAP | nenhum step pós-publish (sem poll do registry, sem `pip install` de verificação, sem checagem de attestation) |

### §5.5-analog — ausências verificadas nos 7 arquivos

Secrets persistentes: ausente. Interpolação insegura em `run:`: ausente
(bodies estáticos, zero `${{ }}`). Execução de PR não-confiável: ausente
(`workflow_dispatch` apenas). Escalação de privilégio: ausente
(`contents: read` no topo; job adiciona só `id-token`/`attestations`).
Action tags mutáveis: ausente. **Bypass de branch: presente** — dispatch
pode rodar de qualquer ref selecionado no `workflow_dispatch` (sem branch
gate). **TOCTOU de build: presente** — rebuild no job de publish.
**Silent attestation failure: não exercido** (nunca despachado; o
comportamento hard-fail do action não foi observado).

## Versões propostas (registry conferido 11.2.1)

`pypi.org/pypi/<pkg>/json` — todos os 7 têm exatamente UMA release
publicada; nenhum `0.x.1`/`1.0.1` existe. Sem risco de duplicar:

| Pacote | Publicado | Patch proposto |
|---|---|---|
| theforge-core | 0.5.0 | 0.5.1 (sem plano próprio — housekeeping pendente) |
| apiforge-af | 0.1.0 | 0.1.1 |
| platformforge | 0.1.0 | 0.1.1 |
| sparkforge-aws | 0.5.0 | 0.5.1 |
| sparkforge-azure | 0.1.0 | 0.1.1 |
| forge-doctor-data | 1.0.0 | 1.0.1 (só se houver motivo) |
| forge-doctor-api | 0.2.0 | 0.2.1 |

## Veredito por pacote (§2.4)

| Pacote | Build+smoke | Pronto p/ patch | Estado |
|---|---|---|---|
| theforge-core | VERIFIED | CI main in_progress na captura; sem patch plan | OPEN |
| apiforge-af | VERIFIED | CI verde; plano pronto | VERIFIED |
| platformforge | VERIFIED | CI verde; plano pronto | VERIFIED |
| sparkforge-aws | VERIFIED | CI main in_progress na captura; plano pronto | OPEN |
| sparkforge-azure | VERIFIED | CI main in_progress na captura; plano pronto | OPEN |
| forge-doctor-data | VERIFIED | nada a republicar | NOT_APPLICABLE |
| forge-doctor-api | VERIFIED | bump 0.2.1 exige rationale do owner em `docs/versioning.md` (`version_gate.py` + rc-discipline) | BLOCKED_EXTERNAL |

Gaps de workflow (environment approval, version gate, post-publish
smoke, TOCTOU rebuild): **OPEN** — reportados, não modificados nesta
passagem (instrução explícita: report only).

## Veredito geral

11.2: FIXED_UNVERIFIED — planos escritos, mergeados, com evidência local
de smoke; nenhum release cortado.

11.2.1: cadeia de build **VERIFIED** de ponta a ponta (sdist → wheel →
wheel-from-sdist idêntica → clean venv → CLI smoke → twine PASSED →
sha256 registrado) nos 7 pacotes. Patches tecnicamente publicáveis
mediante aprovação do mantenedor (aceite P1). Hardening de
`publish-pypi.yml` tem 3 gaps claros + 2 parciais — reportados, não
corrigidos nesta passagem.

## Risco residual

Página PyPI segue com metadata antiga até o próximo upload (esperado).
`publish-pypi.yml` (idêntico nos 7) publica sem environment approval, sem
version/tag/branch gate e sem smoke pós-publish — a única linha de
defesa hoje é a imutabilidade server-side do PyPI e a revisão humana do
dispatch. Binding do trusted publisher no PyPI é config externa —
registrada nos comentários, não verificável do repo. 4 mains com CI
em execução na captura — confirmar verde antes de cortar.
