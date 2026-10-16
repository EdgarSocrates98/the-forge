# FINAL-CERTIFICATION — Cycle 10.1

- **Date**: 2026-10-16 (UTC-3) · Executed on Linux · evidence in `docs/certification/cycle-10.1/`
- **Classification**: **CONDITIONALLY_CERTIFIED**

## Verdict

The nine Forges are **technically ready for distribution and external use via wheel/npm-pack artifacts**, conditional on two items that are release policy, not capability:

1. **F-RC-1** — `the-forge` sdist cannot build a wheel (force-included assets excluded from sdist). Wheel distribution unaffected. Fix before publishing sdists.
2. **Merge of open PRs** — the-forge #62 (this certification), forge-cli #9 (lifecycle matrix), forge-doctor-api #56 (lab dot-dir skip). All green locally; merge is the owner's call.

## §16 report — the 15 items

| # | Item | Evidence (fresh this cycle) |
|---|---|---|
| 1 | Auditoria dos 9 `main` | `baseline.md` — SHAs + CI at commit |
| 2 | Gaps P0/P1 | `gap-register.md` — 8 gaps tracked, all closed or explicitly conditional |
| 3 | Causas-raiz | per-doc findings (F-RC-1, doctor dot-dirs, claims sha-binding, remote-mismatch safety) |
| 4 | Correções | commits cited per doc |
| 5 | PRs | the-forge **#62**, forge-cli **#9**, forge-doctor-api **#56** — created/updated, not merged by me |
| 6 | Testes | forge-cli 622/622 · portal 235/235 · doctor-api suite · the-forge pytest+gates 11/11 |
| 7 | Matriz hosts/MCP | `hosts-mcp.md` — claude 2.1.295 / devin 3000.11.92 / codex 0.159.0; **MCP 6/6 handshakes**; probe registrada via CLI nativo (`apiforge-mcp ✔ Connected` no Claude real); copilot NOT_TESTED |
| 8 | CLI lifecycle | `cli-lifecycle.md` + forge-cli `tests/lifecycle-matrix.test.ts` 8/8 — install/update/pin-downgrade/rollback/uninstall/heal/drift/remote-mismatch-safety com git real |
| 9 | Portal E2E | `portal-e2e.md` — 9/9 browser runs (Chrome 155 real + adapter real + bundle vendored) + 24/24 security suite |
| 10 | E2E global | `e2e-results.md` — fixture com problemas plantados; doctor-api 16 findings (DRIFT001/APISEC011 confirmaram os plantados), apiforge case + 3 findings, platformforge inspect, routing `ambiguous` honesto |
| 11 | Forge Lab | `forge-lab.md` — 7 labs, 203 cenários, re-coleta com verdicts idênticos, auditoria estrutural 9/9 |
| 12 | Segurança | `security.md` — deps limpas (pip-audit/npm audit 9/9), secrets = fixtures only, residual: SHA-pinning/perms em workflows (P2, documentado) |
| 13 | RCs | `release-matrix.md` — 9/9 artefatos construídos; 7 wheels instalam+smoke em venv limpa; `SHA256SUMS.txt` commitado; nada publicado |
| 14 | Pendências | F-RC-1 (sdist), merges dos PRs, SHA-pinning de Actions (P2), copilot ausente |
| 15 | Status final | **CONDITIONALLY_CERTIFIED** |

## Certification gates re-executed on Linux (cyc101-02)

H0–H7 all with fresh evidence: installers 7/7 linux-bash PASS (runner bug fixed — was hardcoded Windows), MCP 6/6, scenarios 19/19, lab 203/0-fail, CI 9/9 green at HEAD.

## Answer to the §13 question

**Estão prontas para distribuição, integração e uso externo?** Sim, com as condições acima: publique wheels (não sdists) até F-RC-1 ser resolvido, faça merge dos 3 PRs, e aceite/corra o backlog P2 de hardening de Actions. Nenhuma capability essencial falhou em verificação real durante este ciclo.

*Assinado por evidência, não por prosa: cada linha desta tabela aponta para um documento com comandos, SHAs e saídas.*
