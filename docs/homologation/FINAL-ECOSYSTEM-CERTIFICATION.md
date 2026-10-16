# Certificação final do ecossistema The Forge

**Data da revisão:** 2026-10-16
**Programa:** `prompt_evo_cycle10.1.md` (anterior: `prompt_evo_auditabilidade.md`, 2026-10-14)
**Estado:** `CERTIFICATION_BLOCKED` (escopo reduzido — ver §3)

## 1. Resumo executivo

Revisão anterior (Windows, 2026-10-14) registrou `CERTIFICATION_BLOCKED` com
gates H1/H3/H4 bloqueados por ambiente. Esta revisão reexecutou H0–H7 em
**Linux real** contra os SHAs atuais de `origin/main`, após os Cycles 8–10.

Resultado: baseline, contratos, MCP local, cenários determinísticos, instaladores
Linux e Forge Lab passaram **todos** nos commits atuais. Permanecem abertos os
gates que exigem evidência de host real e Portal cross-forge, a auditoria de
segurança profunda e a preparação de release candidates — cobertos pelas specs
`cyc101-03..10` em execução.

## 2. Baseline das nove mains (2026-10-16)

| Projeto | SHA auditado | Versão | CI em main | Status gate |
|---|---|---|---|---|
| The Forge | `530ea52` | 0.5.0 | success | PASS parcial |
| Forge CLI | `6109f6a` | 0.1.0 | success | PASS parcial |
| Forge Portal | `ab5a3ef` | 0.1.0 | success | PENDENTE (cyc101-04) |
| API Forge | `6b7ede6` | 0.1.0 | success | PASS parcial |
| Spark Forge AWS | `f8ef41b` | 0.5.0 | success | PASS parcial |
| Spark Forge Azure | `f1e70ce` | 0.1.0 | success | PASS parcial |
| Platform Forge | `aed8d5a` | 0.1.0 | success | PASS parcial |
| Forge Doctor Data | `2e41171` | 1.0.0rc1 | success | PASS parcial |
| Forge Doctor API | `fb31db3` | 0.2.0 | success | PASS parcial |

Fonte: `audit/baseline/` recolhido por `collect_baseline.py --ref origin/main`
em 2026-10-16. "PASS parcial" = gates executáveis verdes; gates dependentes de
specs 10.1 posteriores permanecem pendentes por repo.

## 3. Matriz de gates H0–H7 (reexecutada)

| Fase | Estado | Evidência |
|---|---|---|
| H0 baseline | PASS | `audit/baseline/*.json`, gerado 2026-10-16, SHAs `origin/main` |
| H1 independência | PASS (Linux) | `installer-matrix.json`: **7/7 linux-bash PASS**; powershell-5.1/git-bash BLOCKED (shells Windows-only, ausentes) |
| H2 contratos | PASS | `contract-validation.json` PASS; `mcp-handshake.json` **6/6 PASS** (388 tools: 146+18+154+39+17+14) |
| H3 CLI/Portal | CONDITIONAL | Instaladores PASS; Portal cross-forge E2E pendente (cyc101-04) |
| H4 hosts/MCP/agentes | CONDITIONAL | MCP local 6/6 PASS; hosts claude/codex/devin detectados instalados; verificação via host pendente (cyc101-05); Copilot NOT_TESTED |
| H5 workflows multi-Forge | PASS (local) | `evidence-index.json` **19/19 PASS** nos SHAs atuais + Forge Lab 7/7 labs, 203 cenários |
| H6 segurança/observabilidade | CONDITIONAL | Auditoria de dependências/supply-chain pendente (cyc101-07); findings anteriores permanecem UNVERIFIED até reexecução |
| H7 regressão/certificação | PASS | 9/9 workflows em `main` success nos SHAs do baseline (AWS `f8ef41b` incluído) |

Deltas vs. revisão 2026-10-14: H1 subiu de CONDITIONAL para PASS em Linux;
H2 de CONDITIONAL para PASS; H4 de BLOCKED para CONDITIONAL (MCP local provado,
host real pendente); H5 com SHA-divergência resolvida (baseline = heads atuais);
H7 executado no head atual (anterior era smoke parcial/cancelled).

## 4. Capacidades, contratos e independência

Contratos validados em `origin/main`. Handshake MCP local executou
`initialize`, `tools/list` e `tools/call` em seis servidores — 388 ferramentas
catalogadas, agora incluindo resposta real de `tools/call` em todos (anterior:
doctor-api timeout). Isso prova protocolo local; prova de host externo vem de
cyc101-05.

Instaladores: os 7 Python rodam `install.sh --dry-run` nativo em Linux — plano
completo com receipt `forge/InstallReceipt/v1` e detecção de hosts. Nenhuma
mutação de HKCU/PATH/perfil/checkout. The Forge não é dependência de runtime
dos especialistas (verificado em `audit/baseline/dependencies.json`).

## 5. Instalação, lifecycle e cenários E2E

Cenários determinísticos: **19/19 PASS** contra runtimes `.venv` dos checkouts
nos SHAs atuais (anterior: mesmo total em Windows, SHAs antigos). O runner de
instaladores agora executa `linux-bash` de verdade — corrigido durante esta
revisão (era hardcoded BLOCKED).

Forge Lab: 7/7 laboratórios, 203 cenários coletados em `mode A` nos SHAs
atuais, vereditos `fail` reais preservados. Auditoria do conteúdo das
evidências: cyc101-06.

## 6. Segurança, resiliência e observabilidade

- Nenhuma mutação em AWS/Azure/produção/releases/infra real.
- Auditoria de dependências e supply-chain reexecutada em cyc101-07 (pendente).
- Findings Snyk anteriores permanecem `UNVERIFIED_FOR_RELEASE` até a reauditoria.
- Doctor-api self-scan baseline re-gravado em `fb31db3` (mesmo finding revisado,
  novo hash de bundle).

## 7. Correções implementadas nesta revisão

- `audit/tooling/run_installers.py`: execução nativa `linux-bash` em POSIX
  (antes hardcoded BLOCKED); powershell-5.1 registrado BLOCKED fora de Windows.
- `audit/tooling/run_mcp_handshakes.py`: fallback `.venv/bin/` quando o binário
  declarado não está no PATH (destravou api-forge e platform-forge).
- `forge-doctor-api`: `discover_scenarios` ignora dot-directories — resíduo de
  `.pytest-tmp/` quebrava o lab federado (PR forge-doctor-api#56).
- `api-forge` venv local: extra `mcp` instalado para `apiforge-mcp`.
- `.venv` criado em `forge-doctor-data` para cenários CLI locais.

## 8. PRs e regressão

- [the-forge#62](https://github.com/EdgarSocrates98/the-forge/pull/62) — setup do
  programa cycle-10.1 + correções do tooling de auditoria
- [forge-doctor-api#56](https://github.com/EdgarSocrates98/forge-doctor-api/pull/56)
  — fix de discovery de cenários
- Anteriores (ciclo auditabilidade): spark-forge-aws#164, the-forge#61

CI: os nove workflows mais recentes em `main` estão `success` nos SHAs do
baseline — incluindo o run completo do spark-forge-aws (`38826592343`,
~1h09m) em `f8ef41b`.

## 9. Testes não executados e riscos residuais

Não executados/não comprovados nesta revisão: Portal cross-forge real
(cyc101-04), hosts externos dirigindo as configurações instaladas (cyc101-05 —
claude/codex/devin disponíveis, Copilot ausente), deep scan e fechamento de
findings de dependência (cyc101-07), RCs (cyc101-08), E2E global §10
(cyc101-09), Firefox/WebKit e CUA visual, cenários Windows neste host.

Riscos residuais: regressão específica de host, vulnerabilidades sem correção
publicada, cobertura visual/Portal incompleta.

## 10. Recomendação de release

Manter `CERTIFICATION_BLOCKED` até que as specs cyc101-03..10 produzam suas
evidências e os P0 restantes (Portal E2E, hosts reais, segurança, RCs, E2E
global) sejam resolvidos ou classificados `blocked-external` com justificativa.
O estado pode transitar para `CONDITIONALLY_CERTIFIED` quando nenhum P0
permanecer aberto e as limitações estiverem documentadas.
