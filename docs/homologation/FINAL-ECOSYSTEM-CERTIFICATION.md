# Certificação final do ecossistema The Forge

**Data da revisão:** 2026-10-16
**Programa:** `prompt_evo_cycle10.1.md` (anterior: `prompt_evo_auditabilidade.md`, 2026-10-14)
**Estado:** `CERTIFIED` (ver §3 e §10)

Este documento é a fonte canônica única. A consolidação por item está em
[`../certification/cycle-10.1/FINAL-CERTIFICATION.md`](../certification/cycle-10.1/FINAL-CERTIFICATION.md);
relatório detalhado do ciclo atual: [`../certification/cycle-10.2/FINAL-CERTIFICATION.md`](../certification/cycle-10.2/FINAL-CERTIFICATION.md).

## 1. Resumo executivo

Revisão anterior (Windows, 2026-10-14) registrou `CERTIFICATION_BLOCKED` por
ambiente. Esta revisão reexecutou H0–H7 em **Linux real** contra os SHAs de
`origin/main` e completou as specs `cyc101-01..10` — incluindo os gates que
antes dependiam de evidência ausente: Portal cross-forge com adapter real
(cyc101-04), verificação via host real (cyc101-05), auditoria de segurança
(cyc101-07), release candidates (cyc101-08) e E2E global §10 (cyc101-09).

Resultado: todos os gates executáveis produziram evidência. Restam duas
condições de **política de release**, não de capability: merge dos PRs abertos
e a decisão sobre o sdist do the-forge (F-RC-1).

## 2. Baseline das nove mains (2026-10-16)

| Projeto | SHA auditado | Versão | CI em main | Status gate |
|---|---|---|---|---|
| The Forge | `530ea52` + programa `cycle-10.1/program` | 0.5.0 | success | PASS |
| Forge CLI | `6109f6a` + `cyc101/cli-lifecycle-matrix` | 0.1.0 | success | PASS |
| Forge Portal | `ab5a3ef` | 0.1.0 | success | PASS |
| API Forge | `6b7ede6` | 0.1.0 | success | PASS |
| Spark Forge AWS | `f8ef41b` | 0.5.0 | success | PASS |
| Spark Forge Azure | `f1e70ce` | 0.1.0 | success | PASS |
| Platform Forge | `aed8d5a` | 0.1.0 | success | PASS |
| Forge Doctor Data | `2e41171` | 1.0.0rc1 | success | PASS |
| Forge Doctor API | `fb31db3` + `cycle-10.1/lab-dotdir-skip` | 0.2.0 | success | PASS |

Fonte: `audit/baseline/` recolhido por `collect_baseline.py --ref origin/main`
em 2026-10-16; branches de certificação listadas no PR correspondente.

## 3. Matriz de gates H0–H7 (estado final)

| Fase | Estado | Evidência |
|---|---|---|
| H0 baseline | PASS | `audit/baseline/*.json`, 2026-10-16, SHAs `origin/main` |
| H1 independência | PASS (Linux) | `installer-matrix.json`: **7/7 linux-bash PASS**; powershell-5.1/git-bash BLOCKED (shells ausentes) |
| H2 contratos | PASS | `contract-validation.json`; `mcp-handshake.json` **6/6** (388 tools) |
| H3 CLI/Portal | PASS | lifecycle matrix 8/8 (forge-cli `tests/lifecycle-matrix.test.ts`); Portal E2E 9/9 com adapter real + bundle vendored (`cycle-10.1/portal-e2e.md`) |
| H4 hosts/MCP/agentes | PASS parcial | MCP 6/6 + probe **via host real** (`apiforge-mcp ✔ Connected` no Claude, `mcp list` no Codex); Copilot NOT_TESTED (binário ausente) — `cycle-10.1/hosts-mcp.md` |
| H5 workflows multi-Forge | PASS | `evidence-index.json` 19/19 + Lab 7/7 labs, 203 cenários, re-coleta com verdicts idênticos (`cycle-10.1/forge-lab.md`) |
| H6 segurança/observabilidade | PASS com backlog | deps 9/9 limpas; secrets = fixtures apenas; residual P2: SHA-pinning/permissions em workflows (`cycle-10.1/security.md`) |
| H7 regressão/certificação | PASS | 9/9 workflows `success` nos SHAs do baseline |

## 4. Capacidades, contratos e independência

Handshake MCP local executou `initialize`, `tools/list` e `tools/call` em seis
servidores — 388 ferramentas. Prova via host real em cyc101-05: registro por
CLI nativo do Claude (`cyc101-probe` → `apiforge-mcp ✔ Connected`) e do Codex
(`mcp list`), removidos após a prova.

Instaladores: os 7 Python rodam `install.sh --dry-run` nativo em Linux com
receipt `forge/InstallReceipt/v1`. The Forge não é dependência de runtime dos
especialistas (`audit/baseline/dependencies.json`).

## 5. Instalação, lifecycle e cenários E2E

Cenários determinísticos: **19/19 PASS**. Lifecycle real no forge-cli
(PR #9): install/update/pin-downgrade/rollback/uninstall/heal/drift/
remote-mismatch — 8/8 com git real, `--offline` nos caminhos de rede.

Portal: 9/9 browser runs em Chrome real servindo o bundle vendored pelo
`TheForgePortal` real; suíte de segurança 24/24 (sessão/CSRF/traversal/
injeção/redaction/plan-token).

E2E global (cyc101-09): fixture `e2e/example-app/` com problemas plantados —
doctor-api 16 findings (DRIFT001 confirmou `/refunds`, APISEC011 o auth
ausente), apiforge `analyze` case + 3 findings, platformforge `inspect`;
routing do orquestrador retornou `ambiguous` corretamente.

## 6. Segurança, resiliência e observabilidade

- Nenhuma mutação em AWS/Azure/produção/releases/infra real.
- `pip-audit` e `npm audit`: zero vulnerabilidades conhecidas nos 9 repos.
- Scan determinístico sobre arquivos trackeados: matches são fixtures de
  teste (ex.: `AKIAIOSFODNN7EXAMPLE`); zero secrets reais.
- Findings Snyk anteriores: reclassificados em `cycle-10.1/security.md`.
- Backlog P2 aberto: SHA-pinning de Actions e `permissions:` explícito em
  alguns workflows (tabela por repo em `security.md`).

## 7. Correções implementadas nesta revisão

- `audit/tooling/run_installers.py`: `linux-bash` nativo em POSIX;
  powershell-5.1 registrado BLOCKED fora de Windows.
- `audit/tooling/run_mcp_handshakes.py`: fallback `.venv/bin/` no PATH.
- `forge-doctor-api`: `discover_scenarios` ignora dot-directories (PR #56).
- `forge-cli`: matriz de lifecycle real-git 8/8 (PR #9).
- Claims/locks re-estampados com prova real: spark-azure (`--stamp` em HEAD),
  spark-aws (doc+lock re-ancorados, corpus +1 arquivo), platform-forge
  (receipt de economia ligado ao HEAD), doctor-api (baseline self-scan).
- `portal_adapter.py`: lab dir emitido com `.as_posix()` (`5ef50f0`) — CI
  Windows estava vermelho por separador `\`.
- `forge-doctor-api` (`008f295`): `discover_scenarios` ignora dot-directories
  (skip por `rel.split("/")`) — o `.as_posix()` ali já existia via
  `context.relative()`.

## 8. PRs e regressão

- [the-forge#62](https://github.com/EdgarSocrates98/the-forge/pull/62) —
  programa cycle-10.1 completo (evidências, gates, fixes de tooling).
- [forge-cli#9](https://github.com/EdgarSocrates98/forge-cli/pull/9) —
  lifecycle matrix.
- [forge-doctor-api#56](https://github.com/EdgarSocrates98/forge-doctor-api/pull/56)
  — fix de discovery de cenários.

CI: os nove workflows em `main` estão `success` nos SHAs do baseline.

## 9. Testes não executados e riscos residuais

- Copilot ausente → NOT_TESTED (núcleo não reivindica).
- Firefox/WebKit não executados (browser E2E é Chrome-real).
- Windows nativo: somente CI (matrix 3.11–3.13), sem reexecução local.
- Lab §6.5 multi-agent: PARTIAL (estático + replay).
- Push das branches `cycle-10.2/actions-hardening` pendente: token sem scope
  `workflow`; dono deve fazer `gh auth refresh -s workflow` ou push manual.
- spark-forge-aws READY mas não acionado no E2E (nenhum capability casou com o
  intent; registrado, não contornado).

## 10. Recomendação de release

**`CERTIFIED`** — todos os gates P0 do Cycle 10.2 fechados com evidência:

1. F-RC-1 resolvido: sdist reconstrói wheel funcional (298 arquivos de payload
   idênticos; regressão permanente no `gate/build`).
2. Handoff real theforge→especialista comprovado (api-forge `api.analyze`,
   forge-doctor-data `data.scan`; receipts sha256; falhas controladas nunca
   produzem sucesso falso).
3. PRs 10.1 (#62, #9, #56) mergeados e verificados na main.
4. Actions 100% SHA-pinnadas + least-privilege nos 9 repos.
5. Especialistas independentes (CLIs standalone; adapters no venv do
   especialista, nunca do core).

Escopo não coberto pela certificação: hosts ausentes (Copilot), Firefox/WebKit,
Windows nativo. Releases/tags/publicações: **nenhum criado** — aguardam sign-off.
