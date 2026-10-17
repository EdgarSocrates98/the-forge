# Cycle 11.2 — npm workflow (P0-001)

Escopo: `.github/workflows/publish-npm.yml` pós-forge-cli#29 (merge
`6ea2e79`, 2026-10-17) + `scripts/release/verify-version.mjs` +
`tests/release-workflow.test.ts`. Estado auditado em
`forge-cli@origin/main = 6ea2e79`.

## Comandos executados

```text
cat .github/workflows/publish-npm.yml
sed -n 1,120p scripts/release/verify-version.mjs
npx vitest run tests/release-workflow.test.ts   # worktree limpo de origin/main
gh run list --workflow publish-npm.yml --limit 5
gh run view 39040262185 --json jobs
gh run view 39041701852 --log
npm view theforge-cli@0.2.0 dist.attestations dist.integrity --json
```

## Requisito → evidência

| Requisito | Evidência no arquivo | Teste |
|---|---|---|
| OIDC-only, sem token persistente | `permissions: contents: read` no topo; `id-token: write` só no job `publish`; nenhum `NODE_AUTH_TOKEN` | `id-token só no job publish`, `sem token persistente: nenhum NODE_AUTH_TOKEN` |
| Inputs via env, nunca `${{ inputs.* }}` em `run:` | `env: RELEASE_VERSION: ${{ inputs.version }}` / `RELEASE_TAG` no header; steps consomem `$RELEASE_VERSION` | `inputs chegam via env — nenhum ${{ inputs.* }} dentro de run:` |
| SemVer estrito incl. leading zeros | `SEMVER` regex semver.org em `verify-version.mjs` (rejeita `01.2.3`, parciais, input perigoso antes do shell) | `SemVer estrito: leading zero e versão parcial recusados`, `input malformado/perigoso ⇒ version-invalid` |
| Lockfile parity | `lock-missing`/`lock-mismatch`: `lock.version` e `lock.packages[''].version` devem igualar o input | `lock divergente ⇒ lock-mismatch`, `lock ausente ⇒ lock-missing` |
| Branch gate | step "Branch gate" falha se `github.ref_name != "main"` | `branch gate: dispatch fora da main falha` |
| Tag gate | `--tag` opcional: `tag-missing` / `tag-mismatch` (tag deve apontar para HEAD) | `tag inexistente`, `tag apontando para commit ≠ HEAD` |
| SHA/CI gates | `verify-version.mjs` → package.json match, version-exists (idempotência), `--expect-sha` re-check no job publish; quality gates `npm ci/typecheck/lint/format/test/build` | `sha-mismatch`/`sha-invalid`, `version-exists (0.1.0)` — teste real contra registry |
| TOCTOU → artefato imutável | validate gera `npm pack` tarball e sobe via `upload-artifact` (SHA-pinned, `retention-days: 1`, `if-no-files-found: error`); publish faz `checkout ref: needs.validate.outputs.sha` + re-gate `--expect-sha` + `download-artifact` + artifact gate "exatamente 1 `.tgz` nomeado `theforge-cli-$VERSION.tgz`"; **nunca rebuilda** | `binding anti-TOCTOU`, `publish re-valida SHA e não rebuilda`, `artifact gate` |
| Provenance fail-hard | `npm publish .tgz --provenance --access public`; pós-publish exige `dist.attestations` não-vazio — `if(!n) process.exit(1)`, sem `|| echo` mascarando | `attestation ausente é falha` |
| Post-publish integrity | `dist.integrity` do registry comparado a `sha512-<base64>` local do tarball; divergência → `exit 1`; + install em `mktemp -d` + `npx theforge-cli --help` | `integrity pós-publish`, `publish com provenance + verificação` |
| Registry propagation | poll `npm view` 18×10s (adicionado em #28 após falha real observada) | coberto pelo shape do step |

Actions pinadas em SHA de 40 chars: `actions/checkout@3d3c42e…` (v7),
`setup-node@949feb2…` (v7), `upload-artifact@cf430e0…` (v7.0.2),
`download-artifact@9000827…` (v8.0.2). `environment: npm` (aprovação
humana) + `concurrency` por versão (`cancel-in-progress: false`).

## Testes (execução real, worktree limpo)

```text
✓ tests/release-workflow.test.ts (24 tests) 4226ms
Test Files 1 passed · Tests 24 passed   (origin/main @ 6ea2e79)
```

## Publicação real observada (0.2.0)

`npm view theforge-cli@0.2.0` no registry público — **viva**, com
`dist.attestations.url` e `predicateType: https://slsa.dev/provenance/v1`
e `dist.integrity: sha512-uG9asVO1…`. História real das runs:

| Run | SHA | Resultado |
|---|---|---|
| 39040262185 (14:19Z) | 185ec69 | `npm publish --provenance` assinou statement Sigstore (logIndex 3296060559) mas o PUT foi recusado: `E403 OIDC permission denied` — binding trusted-publisher ainda não efetivo |
| 39041701852 (14:39Z) | 185ec69 | publish OK; post-publish verify falhou com `E404` 10s após o PUT — lag de propagação do registry. Corrigido em #28 (poll 18×10s) |

## Veredito

**VERIFIED com ressalva documentada**: a publicação OIDC+provenance de
0.2.0 aconteceu de verdade e o attestation está vivo no registry — mas
rodou na revisão pré-#29 do workflow (`185ec69`). A revisão endurecida
(artefato imutável, attestation hard-fail, integrity check) ainda não
executou um dispatch de ponta a ponta.

## Risco residual

- Workflow endurecido nunca executou um publish real (próximo dispatch
  será a prova). Fluxo `--tag` nunca exercido. `version-exists` testado
  só contra 0.1.0. Environment `npm` com required reviewers é config de
  repo — não verificável daqui.
