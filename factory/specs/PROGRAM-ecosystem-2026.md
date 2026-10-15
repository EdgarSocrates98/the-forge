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
- **Ponto de retomada:** `cyc0-01` a `cyc8-06` implementadas e em `active/` aguardando review humano — **Ciclo 8 completo (6/6)**. Segunda revisão endereçada (2026-10-15): rc-lifecycle agora faz bootstrap antes do `update` (verificado com `FORGE_HOME_OVERRIDE` isolado → `pip:PASS`), `.env*` no `.gitignore`, teste de versões parametrizado nos 9 siblings (9/9 OK), `installed.origin` derivado de `direct_url.json`, `created_by` normalizado `dist/version` no canônico + re-vendored, `status:` dos specs alinhado. Terceira revisão endereçada (2026-10-15): regressão do re-vendor revertida — features do PR #61 (Git Bash `MSYSTEM`/`OSTYPE`, sourced-vs-exec com `return`, `py.exe`, dot-source PS1, HKCU→`Env:`, try/finally) portadas para os templates `INSTALL_SH`/`INSTALL_PS1` do `vendor.py` e re-vendored na frota (`--check` verde); leftovers limpos (`*.tgz`, `.env` stubs, `config.yaml` agora ignorados nos siblings); `portal_adapter._versions()` honesto (`origin` de `direct_url.json`, `history[].version` null sem campo real); `compat.ts` espelha validação estrita do Python (`manifestProblems`); `update --check --json` emite envelope `{manifest:{release,sha256,path}, repos}` e `installed_compat` por repo (611 testes verdes). Quarta revisão endereçada (2026-10-15): **crítico** — bundle do Portal re-vendored aos 7 repos (`forge-portal/scripts/vendor.py`; a UI cyc8-06 estava só em `dist/`, nunca propagada — `--check` verde, chaves novas nos assets, `SHA256SUMS.txt` atualizado); scripts install/setup re-vendored com `--config @forge.json` por repo (`requires-python` correto `>=3.11`/`>=3.12` — o check **sem** config mascarava drift via default `>=3.10`); `compat.ts` paridade estrita completa (SemVer exato de `contracts/semver.py`, `max_major` em família unversioned, `scheme` Literal) — 613 testes; guard `-f audit.json` no security gate; CHANGELOG do forge-cli documenta o envelope JSON. Quinta revisão endereçada + gaps remediados (2026-10-15): **crítico** — loop do bump `cryptography>=50,<51` fechado com evidência (`audit/api-forge.json` regenerado, zero CVEs, 110 testes keys/report, `security.md`/`open-gaps`/`readiness` sincronizados); **G-17 fechado** (22 arquivos reformatados, ruff format limpo, ui-kit+installkit re-sincronizados na frota); **G-04 fechado** (forge-portal 0.1.0 declarada); **G-20 fechado** (pin bump autorizado); **G-03 parcial** (emissores de receipt normalizam paths — `<repo>`/`~` — recorrência impedida; capturas históricas preservadas como evidência); homologação refresh (install.sh --dry-run 7/7, lifecycle isolado PASS); **ADR-0060 proposto** (Forge Lab agregador fino — aguarda aceite humano para desbloquear cyc9-01); sugestões: `installed_compat` tipado em query.ts, `readDeclaredVersion` escopo `[project]`, `$comment` documentando assimetria schema/dataclass; **cyc9-01 implementado (2026-10-15)** — ADR-0060 aceito pelo usuário (opção B, agregador fino); `forge/BenchmarkSuite/v1` + `forge/BenchmarkResult/v1` em `contracts/benchmark.py` + schemas publicados; `theforge lab list`/`lab collect` com guardrails §9.11 (env sanitizado, timeout/repeats/jobs limitados, modo C recusado sem `--allow-external`); estados honestos `declared`/`undeclared`/`none`/`invalid`/`unsupported-mode`; relatórios em `docs/programs/ecosystem-2026/benchmarks/`; primeiro cenário real `compat-manifest-parity` (the-forge, modo A, 9/9 componentes); 42 testes novos verdes; gate `check_gates.py --pytest` rodou 4986 testes — 3 falhas de docs-consistency (spec movida inbox→active, verbo `lab` não documentado) corrigidas via `regen_docs.py` + seção `## lab` em `docs/cli.md`. Em `active/` aguardando review. **Próxima spec: `cyc9-02`** (`factory/specs/inbox/cyc9-02-eval-integrity.md`, the-forge — métricas/ground truth/regression gates). Depois `cyc9-04..09` (emissores `BenchmarkResult/v1` nos especialistas — hoje reportam `undeclared`/`none`), `cyc9-10` (Portal lab UI), `cyc10-01..03`. Session esgotou contexto após cyc8-06 — retomar em sessão nova.
- **Regra:** specs ficam em `active/` após implementação+verificação; arquivamento só com review aceita humana. `⚠` em Pending = decisão de produto — registrar, não inventar (cyc9-01 exige ADR por feature freeze; licença/canais de publicação ficam abertos).
- **Runs:** `factory/runs/` no repo dono da spec.

## Notas

- `loop-factory` CLI **não instalado**: `factory/specs/` foi populada manualmente; `Loop-Factory/` não existe no workspace (referência obsoleta em `forge-doctor-api/AGENTS.md` → `../Loop-Factory/bin/loop-factory`).
- Feature freeze no the-forge: specs de subsistema novo (cyc9-01) pedem ADR — registrado em Pending, decisão do mantenedor.
- RC window em forge-doctor-api (`docs/rc-discipline.md`): mudança de surface/contrato exige exceção.
