# Cycle 10.3 — Test Evidence

Evidência executável produzida no ciclo. Tudo reproduzível — comandos e
ambientes descartáveis em `/tmp/c103-*`.

## Registry (Wave 1)

- `pip download` 14/14 arquivos (wheel+sdist × 7) — sha256 idênticos ao JSON
  API do PyPI.
- `pip install` limpo em venv por pacote — 7/7 OK; CLIs respondem
  (`apiforge --version` → 0.1.0, `forge-doctor-api`, `theforge` OK).
- npm: tarball `theforge-cli-0.1.0.tgz` integrity sha512 confere; `npx
  theforge-cli doctor` executa.
- Provenance PEP 740: `theforge-core`, `apiforge-af`, `forge-doctor-api` têm
  attestation verificável (publicados via OIDC); os 4 por token não têm —
  consistente com o método.

## CLI DevEx (Wave 3)

- `forge-cli install` workspace descartável: ~23s, 7 componentes
  (mais lento: forge-doctor-data ~12.6s).
- Lifecycle: `status`, `update --check`, `reinstall`, `rollback`,
  `uninstall` — todos funcionais; uninstall gera backups em
  `.forge-cli/backups/`.

## Portal (Wave 4)

- `theforge portal` da wheel: loopback 127.0.0.1 + token na URL.
- `GET /api/v1/versions` sem `X-Forge-Session` → **403**; com token → **200**
  (`forge/PortalApi/1`, installed 0.5.0).
- Traversal → 404; POST `text/plain` → 404; headers de segurança presentes.

## Hosts/MCP (Wave 5)

- `apiforge-mcp` (com `[mcp]`): initialize OK; `tools/list` → **154** (full),
  **6** (compact); legacy=modern=154. `tools/call capabilities_list` →
  `isError:false` + capability JSON. Nome inválido → `isError:true`
  estruturado.
- `platformforge-mcp`: initialize + `tools/list` → **39**.
- `forge-cli hosts`: 5 hosts detectados com versões; `theforge hosts list`:
  detecção honesta (weak/no evidence); `apiforge ai`: codex SUPPORTED.
- Sem extra `mcp`: `ModuleNotFoundError` (esperado) — G-DX-1.

## CI/Security (Wave 6)

- `pip-audit` nos 7 pacotes: 0 vulnerabilidades conhecidas.
- `npm audit` (theforge-cli instalado): 0.
- SHA-pin: 100% dos `uses:` nos workflows dos 9 repos (40-hex ou local `./`).
- Matriz Python: floor não coberto em 3 pacotes → G-MATRIX-1.

## Forge Lab (Wave 7)

- `theforge lab collect --mode A`: 6 labs, **137 cenários**, receipts strict
  `forge/BenchmarkResult/v1`.
- Resultados: api-forge 27/27 · platformforge 44/44 · sparkforge-aws 2/2 ·
  the-forge 8/8 · spark-forge-azure 1 pass + 1 skip (corpus ausente) ·
  forge-doctor-api 52 pass + 2 fail→skipped (bug do emissor, corrigido #61).
- Bug real: skip reportado como fail → PR #61 (32 testes lab verdes).

## Jornada externa (Wave 8)

- Scan E2E da wheel: `forge-doctor-api scan` em OpenAPI de teste → findings
  OAS010/OAS020/RELAPI008 com rule_id+severity+evidence_ref, `gate: PASS`.
- Fricções F-1..F-5 registradas no 08-external-user-journey.md.

## Community (Wave 9)

- `/community/profile`: health 100% nos 9; topics ricos; MIT; issue+PR
  templates; SECURITY.md 9/9.
