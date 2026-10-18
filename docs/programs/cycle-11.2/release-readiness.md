# Cycle 11.2 — Release readiness por repo (+ refresh 11.2.1)

Escopo: estado de prontidão de release por repo em `origin/main` na
captura de 2026-10-17 (~19:30Z). CI consultado via `gh run list
--branch main`.

## Matriz (11.2, captura ~19:30Z)

| Repo | main SHA | CI main | Distribuído | Pendência de release |
|---|---|---|---|---|
| the-forge | ba660e7 | ✅ success | `theforge-core 0.5.0` PyPI | #83 (forge-lab) open; sem patch plan |
| forge-cli | 6ea2e79 | ✅ success | `theforge-cli 0.2.0` npm (OIDC+Sigstore) | worker B/C uncommitted (SAFE_TOOL, lock, no-color, --version); workflow endurecido nunca publicou |
| forge-portal | c1f8844 | ✅ success | — (não publicado) | #32 merged; sem release pendente |
| spark-forge-aws | 4a70021 | 🔄 in_progress na captura | `sparkforge-aws 0.5.0` PyPI | patch plan 0.5.1 pronto, aguarda mantenedor |
| spark-forge-azure | 3ed7e75 | ✅ success | `sparkforge-azure 0.1.0` PyPI | patch plan 0.1.1 pronto |
| api-forge | cb13bdb | ✅ success | `apiforge-af 0.1.0` PyPI | patch plan 0.1.1 pronto |
| platform-forge | 2a9bf44 | ✅ success | `platformforge 0.1.0` PyPI | patch plan 0.1.1 pronto |
| forge-doctor-data | 3f2fe0e | ✅ success | `forge-doctor-data 1.0.0` PyPI | nada a republicar (plano é checklist) |
| forge-doctor-api | beb0e08 | ✅ success | `forge-doctor-api 0.2.0` PyPI | patch plan 0.2.1; #65 (native install) open — conteúdo > patch |

## Leitura (11.2)

- **Pronto para patch agora** (CI verde + plano + sem mudança de
  código/API): platform-forge 0.1.1, api-forge 0.1.1, spark-forge-azure
  0.1.1, spark-forge-aws 0.5.1.
- **Pronto mas com ressalva**: forge-cli — próximo release deve ser o
  primeiro dispatch real do workflow endurecido; esperar o
  fechamento/commit do trabalho in-flight (SAFE_TOOL_CALLED, offline
  lock) maximiza o valor do patch.
- **Bloqueado por PR aberto**: the-forge (#83), forge-doctor-api (#65).
- **Sem ação**: forge-portal (não distribui pacote), forge-doctor-data.

## Veredito (11.2)

Releases são decisão do mantenedor; os planos estão prontos e honestos —
nenhum exige código novo além do bump.

## Risco residual (11.2)

spark-forge-aws main CI em execução na captura (legs novas 3.13/3.14 do
schedule) — confirmar verde antes do release. PyPI publish workflows dos
repos Python não passaram pela mesma revisão de hardening do npm.

---

# Refresh Cycle 11.2.1 — captura 2026-10-17 (~21:50Z)

Reconciliação: `git checkout main && git pull` nos 7 repos Python —
todos limpos, nenhum rebase em curso, todos `Already up to date`.
PRs abertos: `gh pr list -R <repo> --state open` → `[]` nos 7 (blockers
da captura 11.2 — the-forge #83, forge-doctor-api #65 — resolvidos).
Registry: `pypi.org/pypi/<pkg>/json` — nenhum patch publicado.

## Matriz 11.2.1 (repos Python)

| Repo | main SHA | CI main (captura) | PyPI publicado | Patch proposto | Build+smoke | Estado §2.4 |
|---|---|---|---|---|---|---|
| the-forge | 073b95b | 🔄 in_progress | `theforge-core 0.5.0` | 0.5.1 | VERIFIED (wheel idêntica, `theforge 0.5.0`, twine PASSED) | OPEN — CI em execução; sem patch plan próprio |
| api-forge | a775bda | ✅ success | `apiforge-af 0.1.0` | 0.1.1 | VERIFIED (wheel idêntica, `apiforge 0.1.0`, twine PASSED) | VERIFIED |
| platform-forge | dcdd6b8 | ✅ success | `platformforge 0.1.0` | 0.1.1 | VERIFIED (wheel idêntica, `platformforge 0.1.0`, twine PASSED) | VERIFIED |
| spark-forge-aws | 7ba3863 | 🔄 in_progress | `sparkforge-aws 0.5.0` | 0.5.1 | VERIFIED (wheel idêntica, `sparkforge-aws 0.5.0`, twine PASSED) | OPEN — confirmar CI verde |
| spark-forge-azure | 4f49426 | 🔄 in_progress | `sparkforge-azure 0.1.0` | 0.1.1 | VERIFIED (wheel idêntica, `sparkforge-azure 0.1.0`, twine PASSED) | OPEN — confirmar CI verde |
| forge-doctor-data | 1abae68 | ✅ success | `forge-doctor-data 1.0.0` | 1.0.1 condicional | VERIFIED (wheel idêntica, `forge-doctor-data 1.0.0`, twine PASSED) | NOT_APPLICABLE — nada a republicar |
| forge-doctor-api | 64fe467 | 🔄 in_progress | `forge-doctor-api 0.2.0` | 0.2.1 | VERIFIED (wheel idêntica, `forge-doctor-api 0.2.0`, twine PASSED) | BLOCKED_EXTERNAL — bump exige rationale do owner em `docs/versioning.md` (`version_gate.py` + rc-discipline) |

Detalhe de build, hashes e SBOM: `pypi-patches.md` (seção 11.2.1).

## Auditoria `publish-pypi.yml` — resumo (detalhe em `pypi-patches.md`)

Os 7 workflows são byte-identical (`md5 f969a8505298ffe9a48e42c57c4df6b1`).

| Controle | Veredito |
|---|---|
| SHA binding | ✅ PASS (3 actions pinadas em 40-char SHA) |
| Environment approval | ❌ GAP (sem `environment:`; nenhum environment nos 7 repos) |
| Version gate | ❌ GAP (`if: true`; sem check pyproject↔tag↔registry no caminho PyPI) |
| Sem token persistente | ✅ PASS (OIDC-only) |
| OIDC trusted publishing | ✅ PASS (`id-token: write` + `gh-action-pypi-publish`) |
| Artifact immutability | ⚠ PARCIAL (PyPI rejeita re-upload; workflow rebuilda — artefato publicado ≠ artefato de CI) |
| Provenance/attestation | ✅ PASS (PEP 740 `attestations: true`; fail-hard não exercido) |
| Post-publish smoke | ❌ GAP (nenhum step pós-publish) |

## Leitura 11.2.1

- **Pronto para patch** (CI verde + plano + build VERIFIED): api-forge
  0.1.1, platform-forge 0.1.1.
- **Pronto pendendo CI verde**: spark-forge-aws 0.5.1,
  spark-forge-azure 0.1.1, the-forge 0.5.1.
- **Bloqueado externo**: forge-doctor-api 0.2.1 (rationale do owner).
- **Sem ação**: forge-doctor-data.
- **Gaps de workflow**: 3 claros + 2 parciais, idênticos nos 7 —
  candidatos a um único PR-padrão de hardening (environment `pypi` com
  required reviewers, version gate, post-publish smoke, artefato único
  validate→publish) quando o mantenedor autorizar.

## Veredito 11.2.1

Cadeia de build dos 7 pacotes VERIFIED com evidência de comando + hash.
Nenhum release cortado — decisão do mantenedor. Hardening dos workflows
reportado, não modificado (instrução da passagem).

## Risco residual 11.2.1

- 4 mains com CI `in_progress` na captura — estados OPEN acima expiram
  quando as runs fecharem.
- `publish-pypi.yml` sem aprovação de environment, sem version/branch
  gate, sem post-publish smoke — defesa real hoje = imutabilidade
  server-side do PyPI + revisão humana do dispatch.
- Binding do trusted publisher é config externa ao repo — não
  verificável daqui (limite registrado).
