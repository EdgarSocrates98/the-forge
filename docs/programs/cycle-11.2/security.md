# Cycle 11.2 — Security consolidado

Escopo: postura de segurança do ciclo — npm OIDC, portal CSRF/tokens,
fronteiras de subprocesso, tratamento de segredos. Fontes:
`forge-cli@6ea2e79`, `forge-portal@c1f8844`, runs reais do Actions.

## 1. Publicação npm sem token

- `publish-npm.yml`: `id-token: write` só no job `publish`;
  `environment: npm` com aprovação; **zero `NODE_AUTH_TOKEN`** (teste
  estrutural prova a ausência); actions pinadas em SHA; inputs só via
  env; artifact binding anti-TOCTOU; `--provenance` + attestation
  hard-fail + `dist.integrity` comparado ao tarball local.
- Evidência real: `theforge-cli@0.2.0` publicado com statement Sigstore
  (transparency logIndex observado no log da run) e attestation SLSA v1
  consultável no registry hoje.
- Falha observada e tratada: E403 OIDC no primeiro dispatch (binding
  ainda não efetivo) — erro real, não silenciado; corrigido o setup e
  re-dispachado.

## 2. Portal — sessão, CSRF, one-time tokens

- `X-Forge-Session` (128-bit) exigido em todo `/api`; origem estrangeira
  → `PORTAL-ORIGIN` 403; sessão ausente/forjada → `PORTAL-SESSION` 403.
- Registry ops: `plan` emite `sign_plan(plan)`; `execute` exige
  `plan_token` bound àquele plano (`PORTAL-PLAN-MISMATCH`) e o consome
  uma única vez — replay → `PORTAL-PLAN-INVALID` 409.
- Allowlist fechada `_REGISTRY_ACTIONS` (ação fora → 400
  `PORTAL-ACTION`) + `_SAFE_FORGE` regex (nome → 400 `PORTAL-FORGE`).
- CLI ausente → `PORTAL-CLI-UNAVAILABLE` 409, nunca execução inventada.
- Execução via argv array (`_run_cli(argv, timeout)`, sem shell);
  timeouts bounded (60s plan / 180-300s execute).

## 3. Fronteiras de subprocesso (forge-cli)

- Todo spawn é argv-array `shell:false` (handshake MCP, pip, git).
- `redactSecrets` aplicado a stderr/stdout de subprocesso antes de virar
  `detail` de erro (install.ts:465/544/591).
- Home `~/.forge-cli/forges` chmod 0700 em POSIX (no-op honesto em
  Windows — comentário no código).
- `resolveInside` confina paths; `isSafeRepoName` valida nomes;
  `writeFileAtomic` em state/receipts/lock.

## 4. Segredos

- Nenhum token armazenado pelo workflow npm (OIDC efêmero).
- `context`/AI-mode: context builder exclui secrets e honra budget
  (keyless-gate tests: "context builder excludes secrets").
- Quarentena `.rejected` move artefato adulterado em vez de deletar —
  preserva evidência.

## 5. Gates estruturais

`tests/release-workflow.test.ts` (24) provam invariantes do workflow por
parsing; `tests/safety.test.ts` (35) cobre redact/resolveInside/atomic;
`tests/test_security_c5.py` + security E2E no portal cobrem as rotas.

## Veredito

VERIFIED no escopo do ciclo — a superfície de publicação e a de
execução remota (portal) têm evidência real; subprocess boundaries e
secret handling têm prova de teste.

## Risco residual

- Token PyPI legado (G-SEC-1): revogação segue ação humana — não
  verificada neste ciclo.
- `publish-pypi.yml` dos repos Python: hardening OIDC equivalente não
  auditado aqui.
- Auth de hosts: só codex tem probe; demais reportam "não verificável"
  (honesto, não um risco novo).
