# Cycle 11.2 — FINAL CERTIFICATION

Estado final: **CONDITIONALLY_CERTIFIED** — com evidência real acumulada
sobre o 11.1 e dois trabalhos ainda em voo no momento da captura
(2026-10-17 ~19:40Z).

## CERTIFIED (evidência em main)

| Item | Evidência |
|---|---|
| npm publish OIDC real | `theforge-cli@0.2.0` vivo no registry com `dist.attestations` SLSA v1 + `dist.integrity` sha512 (`npm view` auditado hoje) |
| publish-npm.yml endurecido | forge-cli#29 (6ea2e79): env-var inputs, SemVer estrito+lock/tag/SHA/branch gates, artefato imutável anti-TOCTOU, attestation hard-fail, integrity pós-publish — 24 testes estruturais verdes |
| Plan purity | 18/18 cenários verdes em main — hash da árvore idêntico |
| Fault injection | 17/17 verdes — quarentena `.rejected`, restore de lifecycle, `.corrupt` backup |
| Portal registry ops | forge-portal#32 (c1f8844): E2E real Chromium+CLI+PyPI, install/uninstall reais, CSRF/one-time-token/replay/allowlist com códigos nomeados |
| MCP protocolo real | handshake stdio até TOOLS_DISCOVERED em main (spawn argv, sem shell, erros nomeados) |
| Python matrix | pisos cobertos + intermediárias fechadas em api-forge/spark-aws/spark-azure; parciais documentadas em platform/doctors |
| Patch plans PyPI | 6 planos mergeados, `Blockers: None`, com smoke local |
| Detecção de hosts | real nesta máquina: 5 hosts, auth honesta (só codex verified) |
| CI mains | success em 8/9; spark-forge-aws in_progress na captura |
| Suite forge-cli main | **909 testes / 58 arquivos, 0 falhas** (worktree limpo, medido) |

## IN_PROGRESS

| Item | Estado real na captura |
|---|---|
| the-forge#83 Forge Lab | OPEN, mergeable, checks 10 SUCCESS / 4 IN_PROGRESS — resolução 5-níveis + estados honestos implementados |
| forge-doctor-api#65 native install | OPEN — ADR-0006 aceito, 1863 testes declarados; catalog do forge-cli ainda não delega |
| forge-cli worker B/C (feat/c11-2-bc) | uncommitted: SAFE_TOOL_CALLED+HOST_VERIFIED+allowlist `mcp_safe_tools`, `forge-cli-offline-lock/1` (P2-001), `--no-color`/NO_COLOR, `--version` disambiguado, `registry lock`; 20 testes novos em mcp-verify.test.ts |
| P2-003 hosts E2E | detecção/validate/plan reais feitos; registro real + MCP vivo + skills/agents não exercitados |

## OPEN / BLOCKED_EXTERNAL

| Item | Por quê |
|---|---|
| P1-006 releases PyPI 0.x.1 | planos prontos; cortar release é ação do mantenedor |
| P2-002 adoção do catálogo | doctor-api 0.2.1 com _installkit precisa existir no PyPI antes do forge-cli delegar |
| Fault spec 8/20 restantes | permissão/disco/concorrência/native-install/MCP-register/host-setup/contrato sem fixture |
| pin/unpin `--plan` | mutação silenciosa em main — contornado pelo portal, não corrigido |
| NVDA/VoiceOver walkthrough | item manual; nenhum AT no ambiente — MANUAL-NEEDED (não PASS) |
| Token PyPI legado (G-SEC-1) | revogação é ação humana |
| publish-pypi.yml hardening | repos Python sem a mesma revisão OIDC do npm |

## Riscos residuais consolidados

1. Workflow npm endurecido nunca executou um dispatch — 0.2.0 publicou na
   revisão anterior (prova de que OIDC funciona, não de que o endurecido
   funciona).
2. `pin/unpin` mutam `state.json` com `--plan` silenciosamente ignorado.
3. Offline transitivo sem pin de hash **em main** (fix existe, não
   mergeado).
4. Falhas de FS (ENOSPC/EACCES) e concorrência sem injeção real.
5. Hosts: escrita real nunca exercitada (por desenho — exige `--yes`).
6. Screen-reader: nunca verificado por humano com AT.

## Linha de veredito

**CONDITIONALLY_CERTIFIED**: tudo que era gate técnico local está verde
com prova (909 testes forge-cli, E2E portal real, publish OIDC real
observado, hashes antes/depois); `CERTIFIED` pleno exige mergear #83/#65/
worker B-C e cortar os patch releases planejados — nada disso foi
convertido em PASS sem evidência.
