# Cycle 11.1 — final report

Estado final: **CONDITIONALLY_CERTIFIED** — todos os gates tecnicamente
executáveis localmente estão verdes; publicação npm e dois itens P2 ficam
`BLOCKED_EXTERNAL`/`OPEN` por decisão de produto, nunca fingidos.

## 1. Nine-main audit (baseline)

| Repo | SHA baseline | Versão | CI main antes | CI main depois |
|---|---|---|---|---|
| the-forge | ba090c7 | v0.5.0 | success | success |
| forge-cli | 12fe75c | v0.1.0 | success | success |
| forge-portal | 26e6d9f | v0.1.0 | success | success |
| spark-forge-aws | 0b50f0d | v0.5.0 | **failure** (VNX-827) | success (#171) |
| spark-forge-azure | 74d76f2 | v0.1.0 | success | success |
| api-forge | 1ef4898 | v0.1.0 | success | success |
| platform-forge | 86732cf | v0.1.0 | success | success |
| forge-doctor-data | 190a7f4 | v1.0.0 | success | success |
| forge-doctor-api | 1ffcb42 | v0.2.0 | success | success |

## 2. Inventory of gaps

`gap-register.md` — 13 itens (3×P0, 6×P1, 4×P2). Estados finais:
8 VERIFIED · 1 FIXED_UNVERIFIED (P0-001, setup externo) ·
3 OPEN (P1-005 lab, P1-006 patches, P2-001 offline pins, P2-003 hosts E2E,
P2-004 polish, P2-005 metadata) · 1 BLOCKED_EXTERNAL (P2-002 doctor-api
native installer = decisão de produto).

## 3. P0 outcomes

- **P0-001 npm Trusted Publishing**: `publish-npm.yml` — validate job
  (npm ≥11.5.1, ci/typecheck/lint/format/tests/build, `npm pack --dry-run`
  não-vazio, `verify-version.mjs`) → publish job com `environment: npm`,
  `id-token: write`, checkout do SHA validado (sem TOCTOU),
  `npm publish --provenance --access public`, verificação pós-publish
  (versão no registry, attestation, install em tmp limpo + smoke `npx
  theforge-cli --help`). **BLOCKED_EXTERNAL** até binding trusted
  publisher no npmjs.com + environment `npm` com aprovação.
- **P0-002 plan/dry-run purity**: `ephemeral` resolve — plan/check não
  escrevem cache PyPI, venv, receipt ou state. Prova: snapshot SHA-256 da
  árvore home idêntico antes/depois (`tests/plan-purity.test.ts`).
- **P0-003 transações/integridade**: já coberto no Cycle 11 (hash verify,
  quarentena `.rejected`, writes atômicos, `.corrupt` backup, history).

## 4. P1 outcomes

- **P1-001 registry-first UX**: README npm-first; PyPI recomendado, git
  documentado, sem fallback silencioso.
- **P1-002 real MCP**: `src/mcp/handshake.ts` — spawn argv (sem shell),
  JSON-RPC `initialize` → `notifications/initialized` → `tools/list`,
  validação de schema, níveis INSTALLED→TOOLS_DISCOVERED, erros nomeados
  (`stdout-non-json`, `server-exit`, `initialize-invalid`,
  `tools-list-invalid`, `timeout`, `spawn-failed`), sem `tools/call`.
  `probe.{ok,levels,tools,server,protocol,error}` no JSON.
- **P1-003 Portal registry ops**: `portal_core/registry_ops.py` — plan
  (token CSRF + expiry + allowlist de args) → confirm (one-time) →
  execução bounded via argv forge-cli (sem shell) → receipt + state
  refresh. 33 testes; guard estrutural anti-exec preservado.
- **P1-004 Python matrix**: pisos `requires-python` cobertos pela CI em
  todos os repos. Cobertura intermediária parcial registrada (spark-azure
  sem 3.11/3.13; spark-aws sem 3.13/3.14; api-forge só 3.12).
- **P1-005 Forge Lab**: OPEN.
- **P1-006 patches/provenance PyPI**: OPEN — depende de releases
  autorizados.

## 5. CLI changes

862 testes (+~50 no ciclo): handshake MCP real com fixture ESM, pureza de
plan, release workflow, hosts registry-aware. tsc/eslint/prettier/tsup
limpos; CI 9/9 (ubuntu/windows/macos × Node 20/22/24).

## 6. npm Trusted Publishing

Ver P0-001. Workflow + gate prontos e testados; publicação real bloqueada
em setup externo (npmjs trusted publisher `EdgarSocrates98/forge-cli` +
workflow `publish-npm.yml` + environment `npm`).

## 7. Provenance/integrity evidence

`--provenance` no publish; `receipt.provenance` (url + resolvedVia) em
cada install registry; sha256 verify + quarentena `.rejected` em
divergência; `writeFileAtomic` em cache/state; chmod 0700 no state dir
POSIX; `redactSecrets` em stderr de subprocesso.

## 8. Plan/dry-run security tests

`tests/plan-purity.test.ts`: install `--plan`, update `--check`,
uninstall não-TTY sem `--yes` — hash da árvore idêntico, `needsYes`
emitido, zero mutação.

## 9. Lifecycle E2E

`scripts/e2e-certify.mjs` cenários A–H contra `dist/` real em
`FORGE_CLI_HOME` isolado — 8 PASS / 0 FAIL (install real contra PyPI).
Lifecycle registry: update/reinstall/rollback/pin/unpin sobre receipts,
ghosts fora do catálogo, delegação `--native` ao bin da venv.

## 10. Real MCP

Níveis reportados: INSTALLED, EXECUTABLE, MCP_INITIALIZED,
TOOLS_DISCOVERED. `TOOL_INVOKED`/`HOST_VERIFIED` não atingidos por
design — `tools/call` requer allowlist explícita de tools read-only;
verificação em hosts reais fica OPEN (P2-003).

## 11. Host matrix

`forge-cli mcp <forja>` resolve argv por clone (forge.json) ou receipt
(`{bin}`/`{binDir}` templates). `hosts register` sem clone grava
`mcpServers` apontando para a venv. the-forge sem `mcp_command` reporta
`ok:false` honesto. Hosts reais (Claude/Codex/Devin E2E): OPEN.

## 12. Portal integration

`GET /api/v1/registry/state` (RegistryState/v1, read-only) + operações
plan→confirm→execute (P1-003). CLI ausente → erro nomeado, nunca execução
inventada. 81 pytest + ruff verdes; CI main success pós-merge.

## 13. Python matrix

Ver P1-004 + `capabilities.md` (matriz por dist). Pisos: the-forge/doctors
≥3.11, api-forge ≥3.12, platform/spark ≥3.10 — todos cobertos pela CI.

## 14. Forge Lab

SKIPPED honesto (interpreter/extras) — P1-005 OPEN.

## 15. Offline integrity

Artifacts sha256-pinned; deps transitivas via `--find-links` sem pin de
hash completo — P2-001 OPEN, documentado.

## 16. Benchmarks

`scripts/bench.mjs` medido real: `--help` 259ms · `status` 72ms ·
`registry` 67ms · resolve `--plan` 290ms · install frio ~3.2s ·
`update --check` 217ms (`BenchReport/v1`).

## 17. CI

Baseline: spark-forge-aws failure (VNX-827 claim drift 396239→396244) —
corrigido (#171), `check_claims` 0 divergências. Todos os PRs mergearam
com checks verdes; mains pós-merge success (forge-cli, forge-portal,
the-forge, spark-forge-aws).

## 18. PRs

| PR | Escopo | Estado |
|---|---|---|
| forge-cli#25 | Waves 2–9 (TUI, lifecycle, MCP, bench, hardening, e2e) | MERGED |
| forge-cli#26 | Cycle 11.1 P0/P1 (publish, plan purity, MCP handshake, docs) | MERGED |
| forge-portal#22 | `/registry/state` + contrato | MERGED |
| forge-portal#23 | Registry ops plan→confirm→execute | MERGED |
| the-forge#79 | waves-2-9 report | MERGED |
| the-forge#80 | cycle-11.1 baseline + gap register | MERGED |
| spark-forge-aws#171 | VNX-827 claim drift | MERGED |

## 19. Residual risks

- Publicação npm nunca executada de ponta a ponta (setup externo pendente).
- `mcp --verify` prova protocolo até `tools/list`; não invoca tools.
- Hosts reais não exercitados E2E.
- Offline transitive deps sem hash pinning.
- PyPI token antigo (G-SEC-1) ainda não revogado — ação humana.

## 20. Release readiness

forge-cli `theforge-cli` 0.1.0: pacote pronto para patch/minor release —
workflow + gate + provenance + smoke definidos; requer binding npm +
environment approval. Demais repos sem mudança distribuível neste ciclo.

## 21. Publication recommendation

**HOLD** até: (a) trusted publisher configurado no npmjs.com, (b)
environment `npm` com required reviewers, (c) revogação do token PyPI
legado, (d) um `workflow_dispatch` real observado de ponta a ponta.

## 22. Estado de certificação

**CONDITIONALLY_CERTIFIED** — gates técnicos locais verdes com evidência
(862+81 testes, e2e 8/8, plan purity por hash, MCP protocolo real, portal
ops com CSRF/plan-token, claims 0 divergências). `CERTIFIED` completo
exige fechar o setup npm externo + uma publicação real observada.
