# Cycle 10.2 — Real Agentic E2E (theforge → specialists)

Ambiente descartável `/tmp/e2e-handoff` (fixture `e2e/example-app` + `jobs/etl_job.py` PySpark plantado).
Providers registrados pelo mecanismo oficial: user `providers.toml` (`THEFORGE_CONFIG_DIR`)
com `trust = "trusted"` — project-level toml é sempre `unverified` por design.
**Adapters instalados no interpretador de cada especialista** (arquitetura real:
`theforge_*` importa o pacote do especialista no venv dele, via `uv pip install -e`).

## Handoff principal — comprovado
`theforge ask "Analise esta API e sua infraestrutura, identifique problemas e proponha plano"`
→ decision `api-forge` / `api.analyze` (primary) → **status ok**, run `20261016T044800Z-1abc64f2`.
Result: 3 findings reais (AF-CONTRACT-001 contract-sem-impl, AF-CODE-002 ×2 code-sem-contract
— os problemas plantados), 7 evidence items, artifacts com sha256, `provider_receipt`
`case:f5168d24…` sha256-linked. Persistido em `.forge/runs/<id>/`.
Evidência: `audit/artifacts/cycle-10.2/handoff-apiforge.json`.

## Handoff secundário — comprovado
`theforge ask "scan data quality" --capability data.scan`
→ `forge-doctor-data` / `data.scan` → **status ok**, **72 findings**
(AIR000, AWS001–004, AZ000, BQ000…) sobre o fixture.
Evidência: `audit/artifacts/cycle-10.2/handoff-doctordata.json`.

## Falhas controladas (§5.6) — nenhum sucesso falso
| Injeção | Resultado observado |
|---|---|
| provider com timeout (sleep 60s) | `FORGE-PROVIDER-NOT-READY` |
| provider com resposta malformada (não-JSON) | `FORGE-PROVIDER-NOT-READY` |
| capability ausente ("bolo de chocolate") | `status: ambiguous`, selected: [] |
| provider untrusted (project toml) | `FORGE-PROVIDER-UNTRUSTED`, não executado |
| adapter sem pacote do especialista | `ADAPTER-UNAVAILABLE` com unlock explícito |

## Independência (§5.7)
`forge-doctor-api --help`, `apiforge --version`, `platformforge --help` executam
standalone sem theforge — 0 dependência reversa.

## Observações honestas
- Intent genérico sobre PySpark roteou `ambiguous` (data.scan de doctor-data é
  genérico; `--capability` resolveu — comportamento correto: sem chute).
- spark-forge-aws: handoff executado via `--capability pyspark.static-analysis`
  → finding real `SF-PY-002` (collect sem limite) sobre `jobs/etl_job.py`.
  Evidência: `audit/artifacts/cycle-10.2/handoff-sparkforge-aws.json`.
