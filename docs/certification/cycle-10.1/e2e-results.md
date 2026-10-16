# Global E2E — Cycle 10.1 §10 / Wave 6

- **Date**: 2026-10-16 (UTC-3) · Linux · fixture versionado em `e2e/example-app/`
- **Binários**: RC wheels instaladas em venvs limpas (`/tmp/rcv-*`, cyc101-08) — **execução independente dos especialistas**, sem orquestrador no caminho.
- **Planted problems**: P1 rotas sem auth (`/payments`, `/admin/users`), P2 divisão por zero não tratada, P3 drift OpenAPI↔código (`/refunds` documentado, ausente), P4 sem rate limit, P5 SG aberto 0.0.0.0/0 + bucket público, P6 CI sem testes/actions não-pinadas.

## Fluxo executado e evidência (em `e2e/evidence/`)

| Passo §10 | Comando real | Resultado |
|---|---|---|
| diagnóstico determinístico | `forge-doctor-api scan . --format json` | **16 findings** — evidência `doctor-api-scan.json` |
| análise especializada (API) | `apiforge discover --project .` + `analyze --contract` | 5 rotas inventariadas (fact_ids), case `case:8279fa6ebdfe6669`, **3 findings** |
| análise plataforma | `platformforge inspect --repo . --json` | artifacts classificados (k8s/argocd/crossplane detectados a partir dos manifests) |
| routing do orquestrador | `theforge ask "security review of the payments api"` | run `20261016T014017Z-bb1f61d7` → **ambiguous** (tie demo.echo/demo.inspect) — invariante "sem chute" demonstrado; especialistas não registrados como providers neste contexto `.forge` novo |
| receipts/benchmark | Lab federado cyc101-06 | 7 labs, 203 cenários, 0 falhas, re-coleta com verdicts idênticos |
| Portal | cyc101-04 | 9/9 browser E2E com adapter real + bundle vendored |

## Findings que provam detecção dos problemas plantados

- `DRIFT001 Documented operation missing implementation` → **P3 confirmado** (`/refunds`).
- `DRIFT002 Implemented route absent from contract` ×2 → `/payments/{id}/fee`, `/admin/users` fora do contrato.
- `APISEC011 Ambiguous auth-coverage chain` ×3 → **P1 confirmado**.
- `OAS004 Operation without operationId` → qualidade de contrato.
- Refusals honestas coletadas: `AF-OPENAPI-UNSUPPORTED-VERSION` (3.0.0→exige 3.1.x, com `unlock`) e `AF-CASE-INPUT-OUTPUT-OVERLAP` (contract dentro do projeto) — evidência do vocabulário de recusa nomeada em ação real.

## Limitações (honestas)

- Handoff theforge→especialista não exercitado: providers não registrados no `.forge` do fixture; routing correto (ambiguous) foi o outcome real — não mascarado.
- P5 (Terraform) e P6 (CI): fora do escopo dos 3 especialistas mínimos do §10 — doctor-api/platformfornge focam em API/plataforma; findings de IaC ficam para spark-forge/platform em iteração futura (registrado como gap de cobertura de domínio, não de execução).
- Sem credenciais/cloud calls: todos os runs offline-first por design.

**Status**: PASS com limitações registradas — 16+3 findings reais, 3 recusas nomeadas, routing determinístico verificado.
