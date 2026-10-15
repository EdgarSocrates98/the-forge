# FINAL PROGRAM REPORT — ecosystem-2026

Data: 2026-10-15 · Programa `prompt_evo_cycles.md` — Cycles 8, 9, 10.

## Resultado

| Ciclo | Specs | Estado |
|---|---|---|
| Cycle 8 — Release Engineering | 6 | ✅ implementadas, verificadas, pushed |
| Cycle 9 — Forge Lab & Benchmark | 10 | ✅ implementadas, verificadas, pushed |
| Cycle 10 — Public Adoption | 3 | ✅ implementadas, verificadas, pushed |

**19/19 specs do programa entregues** (+ cyc0-01 baseline = 20 com baseline).

## Evidências centrais

- `theforge lab collect --mode A` → **7/7 labs, 203 cenários, 0 falhas de
  coleta** — receipts reais em `benchmarks/results-2026-10-15-A.jsonl`.
- Gates locais do the-forge: **12** (`check_gates.py`) — lint, tipos,
  schemas, agents, zero-deps, onboarding, docs portal, adoção.
- Compatibilidade: `ecosystem-compatibility.json` publicado; CLI `update
  --check` emite envelope `{manifest, repos}` + `installed_compat`.
- Supply chain: `cryptography>=50,<51` (0 CVEs no audit regenerado),
  SHA256SUMS dos wheels de referência.
- Portal `/lab`: receipts reais na UI — `Sem dados`/`UNVERIFIED` honestos.
- GitHub experience: matriz §10.7 auditada, 47 arquivos padronizados,
  DCO exigido, badges só medidos.

## Decisões do dono registradas

`cycle-10-decisions.md`: D1 MIT uniforme, D2 PyPI+diretórios MCP,
D3 DCO Signed-off-by, D4 the-forge/docs+GitHub Pages, D5 preparar/publicar
só com sign-off. ADR-0060 opção B (agregador fino do Lab).

## Pendências honestas (handoff)

- Specs ficam em `factory/specs/active/` — **arquivamento só com review
  humana** (regra do programa).
- Publicação PyPI/MCP e releases públicas aguardam sign-off (D5).
- About/topics/releases dos repos GitHub: ação manual do dono
  (`github-experience.md` tem os valores sugeridos).
- Comparativo baseline-vs-forge-enabled por métricas na UI: depende de o
  `/lab` expor a série `subject`/`judge` de cyc9-02 (evolução futura).
