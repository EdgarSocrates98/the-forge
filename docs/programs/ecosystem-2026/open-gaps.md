# Open gaps — ecosystem-2026 (Wave 0)

Classificação P0 (bloqueia release) / P1 (bloqueia claims) / P2 (adoção). Critério §7: nenhum P0 aberto para release.

## P0

| # | Gap | Evidência | Spec |
|---|---|---|---|
| G-01 | Zero tags/releases em todos os 9 repos — nada é versão identificável instalável | `git tag -l` = 0 | cyc8-01, cyc8-04 |
| ~~G-02~~ | ~~Nenhum artefato verificável~~ **parcialmente fechado por cyc8-02** — 9/9 artefatos buildáveis + instaláveis em ambiente limpo (packaging-matrix.md); publicação em registries continua pendente (decisão ⚠) | `python -m build` ×9 OK | cyc8-02, cyc8-03 |
| G-03 | platform-forge: 9 arquivos `/home/edgar` hardcoded — **reclassificado**: só em `docs/` (receipts/SBOM/dogfood), wheel é limpo; higiene de docs, não bloqueio | `git grep` | cyc8-04 (lint de docs) |
| ~~G-04~~ | ~~forge-portal `version: 0.0.0` placeholder~~ **fechado 2026-10-15** — `package.json` e manifesto declaram `0.1.0` (teste de paridade 9/9 re-verificado) | package.json | cyc8-01 |
| ~~G-05~~ | ~~Sem manifesto de compatibilidade~~ **fechado por cyc8-01** — `ecosystem-compatibility.json` + `forge/EcosystemCompatibility/v1` criados (aguarda review) | `ecosystem-compatibility.json` | cyc8-01 |
| G-06 | Lifecycle (update/rollback/uninstall) não gerenciado | **parcialmente fechado por cyc8-05** (2026-10-15): CLI ganhou compat check contra `forge/EcosystemCompatibility/v1` no `update --check`; install/update/rollback já existiam; install-por-tag segue bloqueado por G-01 | cyc8-05 |
| ~~G-17~~ | ~~`ruff format --check` falha em 22 arquivos~~ **fechado 2026-10-15** — reformat aplicado, `ruff format --check` limpo (947 arquivos), suíte verde; ui-kit re-sincronizado pós-reformat | `ruff format --check` = 0 drift | cyc8-04 |
| ~~G-18~~ | ~~api-forge `ui/wizard.py` diverge do kit~~ **fechado por cyc8-02** — drift era em 6 repos (edições locais "native &lt;Product&gt; commands"); re-vendored do canônico, `test_experience_parity` 4/4 verde | pytest 2026-10-15 | cyc8-02 |
| G-19 | Vendored portal assets estavam stale nos 7 siblings — **fechado por cyc8-02** (`vendor.py` re-sync; `forge/PortalAssets/1` manifest) | `vendor.py --check` | cyc8-02 |
| ~~G-20~~ | ~~api-forge `cryptography>=43,<47` = 46.0.7 com 4 CVEs~~ **fechado 2026-10-15** — bump autorizado pelo usuário: `>=50,<51` → 50.0.2, re-audit zero CVEs, 110 testes keys/report verdes | `audit/api-forge.json` | cyc8-04 |
| G-21 | the-forge declara MIT sem `LICENSE`; forge-portal e forge-doctor-api sem licença alguma — decisão de dono (não inventar) | LICENSE scan | cyc10-02 |

## P1

| # | Gap | Evidência | Spec |
|---|---|---|---|
| ~~G-07~~ | ~~Forge Lab coordenador federado inexistente~~ **parcialmente fechado por cyc9-01** (2026-10-15): coordenador + harness entregues (`theforge lab collect`, guardrails §9.11, relatórios em `benchmarks/`); emissores `forge/BenchmarkResult/v1` por especialista pendentes (cyc9-04..09) | `theforge lab collect` live | cyc9-01 |
| ~~G-08~~ | ~~Sem contrato de métricas~~ **parcialmente fechado por cyc9-01** (2026-10-15): `forge/BenchmarkSuite/v1` + `forge/BenchmarkResult/v1` + schemas publicados; ground truth por `sha256` declarado — suites por especialista pendentes (G-09 (fechado 2026-10-15: emissores BenchmarkResult/v1 nos 6 especialistas — lab collect 7/7, 203 cenários)) | `contracts/benchmark.py` | cyc9-01, cyc9-02 |
| G-09 (fechado 2026-10-15: emissores BenchmarkResult/v1 nos 6 especialistas — lab collect 7/7, 203 cenários) | Cenários versionados por especialista ausentes (the-forge `compat-manifest-parity` é o primeiro; suites por domínio pendentes) | ausente | cyc9-04..09 |
| G-10 | Supply chain: sem SHA-256/SBOM/proveniência publicados | ausente | cyc8-03 |
| G-11 | Gates CI desiguais; sem escala smoke-PR vs full-noturno | workflows | cyc8-04 |
| G-12 | RC windows ativas (doctor-data 1.0.0rc1, doctor-api 0.2.0) — requer disciplina de exceções | pyproject, rc-discipline.md | cyc8-04 |

## P2

| # | Gap | Evidência | Spec |
|---|---|---|---|
| G-13 | Onboarding/golden paths não documentados | ausente | cyc10-01 |
| G-14 | GitHub Experience heterogêneo (licença/templates/security por repo) | não auditado | cyc10-02 |
| G-15 | Sem modelo de contribuição/confiança para Forjas externas | ausente | cyc10-03 |
| G-16 | Sem mecanismo opt-in de feedback | ausente | cyc10-03 |

## Resolvidos após baseline (sweep 2026-10-15, "trate todos os gaps")

- **G-17** reformat aplicado (22 arquivos) — `ruff format --check` limpo.
- **G-20** pin `cryptography` bumped `>=50,<51` → 50.0.2, audit zero CVEs.
- **G-04** forge-portal declarada `0.1.0`.
- **G-03 parcial**: emissores de receipt (`validate.py`,
  `freeze_validation_receipt.py`) normalizam paths via `_display_cmd`;
  capturas históricas preservadas como evidência point-in-time.
- **Homologação refresh**: `install.sh --dry-run` 7/7, lifecycle isolado PASS.
- **ADR-0060** aceito (2026-10-15, opção B — agregador fino) — desbloqueou cyc9-01.
- **Design pendente**: branding por produto na mensagem do wizard (ui-kit
  canônico usa "native Forge commands"; asserts dos siblings alinhados).
  Requer placeholder no template canônico — decisão, não bug.

## Bloqueios externos (registrados, não resolvíveis em código)

- Publicação em registries (PyPI/npm), releases públicas, hosts pagos/cloud real: exigem autorização — §9 política de git. Specs preparam, não publicam.
- `Loop-Factory/` não está no workspace: specs operam manualmente até o CLI ser clonado/instalado (ou a referência em `forge-doctor-api/AGENTS.md` ser corrigida).

## Homologação anterior — status dos bloqueios

Fonte: `docs/homologation/FINAL-ECOSYSTEM-CERTIFICATION.md` (2026-10-14, `CERTIFICATION_BLOCKED`). Comparação contra evidência fresca de 2026-10-15.

| Bloqueio anterior | Status | Evidência fresca |
|---|---|---|
| Linux real / instaladores em Linux (7 casos BLOCKED) | **nova evidência parcial** | `.forge-cli/state.json`: 8 repos "validated" via setup.sh em Linux em 2026-10-15; matriz de instaladores **não re-executada**, lifecycle não testado |
| Hosts externos (Claude, Devin, Copilot) | **persiste** | Não verificado. Nota: esta sessão roda via Devin CLI no Linux — evidência informal parcial, não homologação |
| Runner Portal cross-forge reproduzível | **persiste** | Sem nova execução |
| Deep scan (permission profile) | **persiste** | Ausente |
| Findings Snyk `UNVERIFIED_FOR_RELEASE` | **persiste** | Sem novo scan |
| E2E P0 contra SHAs H0 estritos | **obsoleto → nova baseline** | SHAs mudaram nos 9 repos (ver `baseline.md`); E2E precisa re-rodar contra os novos heads |
| Ciclo install/update/rollback/uninstall homologado | **persiste** | Equivale a G-06 (P0) |
| Handshake MCP local (6/6, 388 tools) | **persiste** (não re-verificado) | Não re-executado nesta captura |
| Divergência runtime baseline↔checkout | **persiste** | Mesmo risco vale para a nova baseline — evidências citam checkout local |
| Gates P0: remoção do orquestrador, Portal cross-forge, hosts | **persiste** | Sem prova nova |

**Resumo:** 0 resolvidos · 9 persistem · 1 nova evidência parcial · 1 obsoleto por mudança de SHAs. Nenhum bloqueio anterior pode ser declarado resolvido com a evidência atual.
