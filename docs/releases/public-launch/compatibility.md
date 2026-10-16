# Release 1 — Matriz de compatibilidade verificada

Sucessora de `docs/programs/ecosystem-2026/compatibility-matrix.md`
(draft "não certificada"). O que abaixo foi **executado** nesta baseline
(2026-10-16) está marcado ✅; o restante permanece declarado.

## Combinações verificadas nesta baseline

| Par | Comprovação | Evidência |
|---|---|---|
| the-forge wheel → venv limpa py3.11 | instala + `theforge 0.5.0` | `packaging.md` |
| 6 especialistas wheel → venv limpa | instalam + CLIs respondem | `packaging.md` |
| forge-cli tarball npm → `npm install` | bin executa | `forge-cli` § |
| forge-cli → instala doctor-data + doctor-api | 2/2 OK, 33.7s | `hosts-mcp.md` |
| `theforge portal` da wheel | serve 127.0.0.1 + session token, index 200 | `portal.md` |
| the-forge → api-forge handoff (`api.analyze`) | status ok, findings reais | cycle-10.2 `agentic-e2e.md` |
| the-forge → forge-doctor-data (`data.scan`) | 72 findings | idem |
| the-forge → spark-forge-aws (`pyspark.static-analysis`) | finding SF-PY-002 | idem |

## Suporte de plataforma (declarado vs observado)

| Componente | Linux | Windows | macOS |
|---|---|---|---|
| the-forge | ✅ CI+local | ✅ CI matrix (py3.11–3.14) | declarado (sem runner macOS) |
| forge-cli | ✅ | ✅ (via testes) | declarado |
| especialistas | ✅ | ✅ CI | declarado |
| forge-portal | ✅ | ✅ | declarado |

`declarado` ≠ testado — macOS não tem runner CI em nenhum repo. Honesto
na matriz de suporte das release notes.

## Restrições concretas

- `apiforge` exige Python **>=3.12** (os outros: >=3.10/3.11).
- forge-cli exige Node **>=20**.
- Portal: depende da wheel the-forge (assets vendored + manifest sha256).

## Contratos

`theforge/<Name>/v1` (core), `forge/v1` provider protocol,
`specialist_manifest`, `install_receipt`, `portal_api` — inalterados
desde a certificação cycle-10.2 (zero commits funcionais desde então em
src/, verificado por diff de baseline).
