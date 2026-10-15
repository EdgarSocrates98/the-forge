# Programa ecosystem-2026 — índice de specs

Fonte: `prompt_evo_cycles.md` (Cycles 8, 9, 10). Decomposto em 20 specs na convenção Loop Factory (`inbox` → `active` → `archive`). Todas com `grill: pending` — precisam de revisão humana antes de dispatch. Itens `⚠` em **Pending** são decisões de produto abertas, não assumidas.

| Spec | Repo | Wave | Pri | Entrega principal |
|---|---|---|---|---|
| cyc0-01 | the-forge | 0 | p0 | Baseline dos 9 repos + auditoria de distribuição + scaffold `docs/programs/ecosystem-2026/` |
| cyc8-01 | the-forge | 1 | p0 | Política de versões + Compatibility Manifest |
| cyc8-02 | the-forge | 1 | p0 | Empacotamento (wheels, npm, bundle Portal) |
| cyc8-03 | the-forge | 1 | p0 | Supply chain (SHA-256, SBOM, proveniência) |
| cyc8-04 | the-forge | 1 | p0 | Gates CI/CD + Release Candidate lifecycle |
| cyc8-05 | forge-cli | 1 | p0 | CLI: install/update/rollback/compat check |
| cyc8-06 | forge-portal | 1 | p0 | Portal: Release Management UI |
| cyc9-01 | the-forge | 2 | p1 | Forge Lab coordenador federado + harness (modos A/B/C) |
| cyc9-02 | the-forge | 2 | p1 | Métricas + ground truth + regression gates |
| cyc9-03 | the-forge | 3 | p1 | Cenários multi-Forge |
| cyc9-04 | spark-forge-aws | 3 | p1 | Cenários Data Engineering AWS |
| cyc9-05 | spark-forge-azure | 3 | p1 | Cenários Data Engineering Azure |
| cyc9-06 | api-forge | 3 | p1 | Cenários API Engineering |
| cyc9-07 | platform-forge | 3 | p1 | Cenários Platform Engineering |
| cyc9-08 | forge-doctor-data | 3 | p1 | Cenários Doctors (data) |
| cyc9-09 | forge-doctor-api | 3 | p1 | Cenários Doctors (api) — reusa `forge-doctor-api lab` |
| cyc9-10 | forge-portal | 3 | p1 | Portal: seção Forge Lab |
| cyc10-01 | the-forge | 4 | p2 | Onboarding + Getting Started + Golden Paths |
| cyc10-02 | the-forge | 4 | p2 | Docs unificados + posicionamento + GitHub Experience |
| cyc10-03 | the-forge | 5 | p2 | Contribuição externa + distribuição + templates + demos + feedback |

## Ordem e dependências

- `cyc0-01` precede tudo (levanta capacidades reais, CI existente, relatório anterior).
- `cyc8-01` → `cyc8-05`, `cyc8-06` (compat check consome o manifesto).
- `cyc9-01` + `cyc9-02` → `cyc9-03`–`cyc9-10` (harness e contrato de métricas).
- `cyc9-*` → `cyc10-03` (claims públicos exigem benchmarks aprovados; §4: Cycle 10 não publica benchmark não aprovado pelo Cycle 9).
- `cyc8-02` → `cyc10-01` (onboarding precisa de instalação como pacote).

## Execução

- **Autorização permanente (2026-10-15, usuário):** executar todas as specs na ordem do índice até a entrega final.
- **Ponto de retomada:** **PROGRAMA COMPLETO — 19/19 specs implementadas,
  validadas, revisadas e arquivadas em `archive/2026/`** (review humana delegada
  pelo dono em 2026-10-15). Specs `lf-0001..0006` permanecem em `active/` —
  programa distinto, revisão própria pendente. Decisões de dono pendentes:
  publicação PyPI/MCP e releases públicas (D5 em `cycle-10-decisions.md`);
  About/topics do GitHub é ação manual. Próximo passo quando houver: sign-off
  de publicação ou novo ciclo de specs.
- **Regra:** specs ficam em `active/` após implementação+verificação; arquivamento só com review aceita humana. `⚠` em Pending = decisão de produto — registrar, não inventar (cyc9-01 exige ADR por feature freeze; licença/canais de publicação ficam abertos).
- **Runs:** `factory/runs/` no repo dono da spec.

## Notas

- `loop-factory` CLI **não instalado**: `factory/specs/` foi populada manualmente; `Loop-Factory/` não existe no workspace (referência obsoleta em `forge-doctor-api/AGENTS.md` → `../Loop-Factory/bin/loop-factory`).
- Feature freeze no the-forge: specs de subsistema novo (cyc9-01) pedem ADR — registrado em Pending, decisão do mantenedor.
- RC window em forge-doctor-api (`docs/rc-discipline.md`): mudança de surface/contrato exige exceção.

## Status — 2026-10-15 (fim de sessão)

- **cyc9-01..cyc9-10 + cyc10-01..cyc10-03 implementadas, validadas, commitadas e pushadas** — **programa 19/19 completo**:
  - cyc9-01 coordenador federado (ADR-0060 opção B), cyc9-02 integridade de avaliação
    (estados/métricas/stats/gate), cyc9-03 biblioteca multi-forge (7 cenários, runner real).
  - cyc9-04..09 emissores `forge/BenchmarkResult/v1` nos 6 especialistas sobre os
    motores locais reais; `.venv` próprio via uv onde o motor exige deps
    (api-forge, platform-forge, sparks) — declarado `{checkout}/.venv/bin/python`.
  - Evidência: `theforge lab collect --mode A` → 7/7 labs ok, **203 cenários**,
    0 falhas de coleta; vereditos `fail` do corpus reportados honestamente.
  - cyc9-10 Portal Forge Lab UI: `GET /api/v1/lab` no portal_adapter (receipts
    reais, nada sintetizado) + página `/lab` no forge-portal (histórico,
    catálogo com filtro por forja, comparação de vereditos, exports
    JSON/Markdown, estados Sem dados/UNVERIFIED). 235 testes, build e
    vendor --check verdes; bundle re-vendored nos 7 repos.
- **cyc10-01..03** (2026-10-15): onboarding §10.2–§10.4 (jornada 8 estágios,
  11 guias de perfil, 4 golden paths + gate `check_onboarding.py`); portal de
  docs §10.5 (18 seções → fontes canônicas) + GitHub Experience §10.7 (47
  arquivos padronizados, DCO, licenças MIT — D1); adoção §10.9–§10.12 (modelo
  de confiança untrusted→trusted, plano PyPI+MCP — D2, 7 templates, 8 demos
  sintéticas, feedback opt-in — `check_adoption.py`). 12 gates verdes.
- **Decisões do dono registradas** em `docs/programs/ecosystem-2026/cycle-10-decisions.md` (D1–D5).
- **Restantes:** review humana das specs em `active/` (regra do programa);
  publicação PyPI/MCP e releases públicas aguardam sign-off (D5); About/topics
  do GitHub são ação manual (`github-experience.md`).
- Semântica estabelecida: emissor sai 0 quando o receipt foi escrito — vereditos
  `fail` são dado dentro do receipt; `skipped`/`not_applicable` nunca viram pass.
