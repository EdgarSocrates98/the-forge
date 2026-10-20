# Cycle 12.0 — Baseline do ecossistema (Discovery & Contracts)

Data: 2025-11 (sessão Devin CLI). Método: auditoria read-only por repositório (9 relatórios
de subagente) + verificação empírica wheel-only pelo agente principal.
Nada foi modificado durante a auditoria. `data-sentinel-forge` excluído por instrução do
dono (outro processo Devin evoluindo o checkout).

## 1. Estado dos checkouts (SHAs de baseline)

| Repositório | Branch | SHA local | SHA origin/main | Estado |
|---|---|---|---|---|
| spark-forge-aws | main | `12913ad8` | idem | limpo, sincronizado |
| spark-forge-azure | main | `7b13ed09` | idem | limpo, sincronizado |
| api-forge | main | `891ffc23` | idem | limpo, sincronizado |
| platform-forge | main | `25de19a2` | idem | limpo, sincronizado |
| forge-doctor-api | main | `345ae07` | idem | foi fast-forwarded de `9eec90d` |
| forge-doctor-data | main | `a447dfa7` | idem | limpo, sincronizado |
| the-forge | main | `b8df4acd` | idem | limpo, sincronizado |
| forge-cli | main | `bde6b0cd` | idem | limpo, sincronizado |
| forge-portal | `release/2.2.2-certification` | `2f98c640` | `7e6ec93c` (main) | branch de release, não trocada |
| data-sentinel-forge | — | — | — | **diferido; working tree sujo (mudanças de outro processo, preservadas)** |

## 2. Matriz de empacotamento (artefatos reais construídos)

Build com `python -m build` (build 1.6.1, venv `/tmp/forge-build`); wheel inspecionada
via `unzip -l`; instalação testada em venv limpo com `--no-cache-dir --only-binary=:all:`,
executando a partir de diretório vazio (`/tmp/empty-ws`).

| Repositório | Dist | Versão | Py | Backend | Wheel (MB / arq.) | Install wheel-only | CLI wheel-only |
|---|---|---|---|---|---|---|---|
| spark-forge-aws | `sparkforge-aws` | 0.5.2 | >=3.10 | hatchling | ~3.8 / 1045 | OK | OK (`sparkforge-aws`, `-tools`) |
| spark-forge-azure | `sparkforge-azure` | 0.1.2 | >=3.10 | hatchling | ~1.9 / 635 | OK | OK |
| api-forge | `apiforge-af` | 0.1.2 | >=3.12 | hatchling | ~1.7 / 747 | OK | OK (`apiforge`, `apiforge-mcp`, `apiforge-tui`) |
| platform-forge | `platformforge` | 0.1.2 | >=3.10 | hatchling | ~1.3 / 670 | OK | OK (`platformforge`, `-mcp`) |
| forge-doctor-api | `forge-doctor-api` | 0.2.2 | >=3.11 | poetry-core | ~0.55 / 272 | OK | OK |
| forge-doctor-data | `forge-doctor-data` | 1.0.2 | >=3.11 | poetry-core | ~1.5 / 445 | OK | OK |
| the-forge | `theforge-core` | 0.5.2 | >=3.11 | hatchling | ~1.2 / 320 | OK | OK (`theforge`, `forge`) |
| forge-cli | `theforge-cli` (npm) | 0.2.2 | node>=20 | tsup bundle | dist/index.js | n/a | bin `forge-cli` |
| forge-portal | `forge-portal-app` (privado) | 0.1.0 / PORTAL_VERSION 1.0.0 | node | Angular 22 | vendored SPA | n/a | servido por `<cli> portal` |

## 3. Verificação empírica wheel-only (executado nesta sessão)

- **spark-forge-aws** instalado do wheel, a partir de `/tmp/empty-ws`:
  - `sparkforge-aws knowledge path` → resolve `site-packages/sparkforge_aws/knowledge` (lista INDEX.md + dezenas de packs). **PASS**.
  - `sparkforge-aws knowledge drift` → executa e emite relatório de fontes. **PASS**.
  - `sparkforge-aws mcp verify` (após instalar extra `[mcp]` do PyPI) → **PASS**: handshake real, `146 tools`, invocação da tool segura `sparkforge_aws_runtime_detect` retornou resultado estruturado. Sem o extra: **FAIL honesto** com mensagem orientando `pip install 'sparkforge-aws[mcp]'`.
  - `python -m sparkforge_aws.evals` → CLI existe, mas resolve suites em `<cwd>/evals/agentic/` e `evals/agentic/` **não está no wheel** → degradado fora do checkout. **GAP confirmado**.
- **spark-forge-azure**: `rules.loader.catalog_dir()` resolve `site-packages/sparkforge_azure/rules/catalog` → **inexistente no wheel** (o wheel tem `_data/rules/catalog`); `knowledge_dir()` idem (`_data/knowledge` existe). `paths.data_root()` resolve corretamente. **P1 confirmado no wheel real**: `judge`, `case route`, ordering e tools de knowledge degradam.

## 4. Arquitetura já existente (não recriar)

- **Installkit compartilhado** (canônico `the-forge/scripts/installkit/`, vendido byte-idêntico
  em cada forge): `~/.forge/installations/<id>.json` (`forge/InstallationManifest/v1`),
  `~/.forge/installs/`, shims em `~/.local/bin`, lock com reclaim, ledger sha256 de posse,
  marker blocks, `.mcp.json` managed key, `plan→apply` com gate `--yes`, escopos
  project|workspace|user, `mcp_verify` = handshake JSON-RPC real, `env.sh` em
  `${XDG_CONFIG_HOME:-~/.config}/forjas/env.sh` via bootstrap, `FORGE_HOME_OVERRIDE` para testes.
- **forge-cli** (`theforge-cli` 0.2.2): dois métodos de instalação — `git` (default hoje) e
  `registry` (PyPI, resolução via API + sha256 verificado, venvs em `~/.forge-cli/forges/*/venv`,
  receipts, lock offline `forge-cli-offline-lock/1`, `forge-cli/RegistryState/v1`). Catálogo
  hardcoded: 8 repos + 7 dists PyPI com `mcp_safe_tools` allowlist. `mcp --verify` = handshake
  real com níveis INSTALLED→…→SAFE_TOOL_CALLED. Publicação npm OIDC com attestation.
- **the-forge**: federação data-driven (registry manifests → `forge-knowledge` → `forge.json`
  de checkouts), provider registry TOML, negociação de capacidades, `SubprocessTransport`
  JSON com allowlist de env (credenciais nunca propagadas), `install_auto` via
  `install_command` declarado. Zero deps de runtime por gate.
- **forge-portal**: backend stdlib vendido byte-idêntico (`_forge_portal.py`,
  `_portal_telemetry.py`) + SPA vendida com manifest sha256 (`forge/PortalAssets/1`);
  loopback-only, session token, plan tokens HMAC, rate-limit, scrub de segredos; lê
  `~/.forge/installations/*` e `~/.forge-cli/forges/state.json` read-only; honesty invariant
  (UNVERIFIED, nunca fabricar).

## 5. Gaps por repositório (severidade)

### spark-forge-aws (P1 = quebra wheel; P2 = degradado honesto; P3 = doc/UX)
- P1 `case/playbook.py:33-35` — `parents[2]/"agents"` → `site-packages` → `playbook` retorna
  coordenador desconhecido fora do checkout (não consulta `integrate/bundle/agents`).
- P2 `observability/surface.py:21` — mede `ROOT/skills|knowledge` → `economy report` reporta 0.
- P2 `economy/goldset.py` — globa `fixtures/` → vazio no wheel (módulo shipped).
- P2 evals: suites `<cwd>/evals/agentic` + não empacotadas (por design hoje; prompt exige
  smoke de eval sem cwd).
- P3 `install.sh` default `--editable` (dev flow); documentar/criar caminho não-editable.
- P3 `knowledge` expõe só `path|drift` (sem list/search/verify do contrato-alvo).

### spark-forge-azure
- P1 `rules/loader.catalog_dir()` e `knowledge_ref.knowledge_dir()` — fallback
  `sparkforge_azure/{rules/catalog,knowledge}` inexistente no wheel (`_data/` correto mas
  não migrado). **Confirmado empiricamente**.
- P2 `cmd_analyze._knowledge_roots`, `knowledge_engine/packs`, `lab/cli.py` ignoram `_data`.
- P3 `portal_assets` fora de `ASSET_GROUPS` (não hasheado); docstring stale em
  `knowledge_drift.py`; `test_installed_provenance.py` stale (`sparkforge`, `MANIFEST.in`).

### api-forge
- P1 `knowledge/` e `evals/` **não** force-included — `Distribution-v1.md` contrata packs
  mas build não copia. `knowledge list/select`, `migrate` (matrix via `parents[3]` que escapa
  o pacote) e ~24 comandos `evals *` com defaults `Path("evals/corpus/…")` degradam.
- P2 `cli.py` com defaults `Path("knowledge")` bypassam `default_root()`.
- P3 `.devin/mcp_config.example.json` usa `PYTHONPATH=src` (checkout-only);
  `tests/knowledge/test_packs.py` cwd-bound.

### platform-forge
- P1 `live/envelope.py:19` — `parents[2]/"contracts"` → validação de schema **silenciosamente
  pulada** no wheel (retorna `{}`). `bench.py`, `freeze/manifest.py`, `freeze/snapshots.py`
  idem (dev/UX).
- P3 `mcp/server.py` `serverInfo.version="0.1.0"` drift; launcher `python -m` vs shim
  `platformforge-mcp` inconsistente; extras `mcp`/`aws` inertes; sdist sem payload declarado.

### forge-doctor-api
- P2 YAMLs de knowledge via include implícito do Poetry — adicionar asserção de wheel.
- P2 `labs/` não vai no wheel — `lab` verb degrada fora do checkout.
- P3 drift de versão: metadata 0.2.2 vs docs/`forge.agentic.json` 0.2.0.
- P3 `render_assets={}` — docs de instalação portátil prometem hosts que não são emitidos.

### forge-doctor-data
- P1 `cli/misc.py:933-936` — `Path(str(importlib.resources.files(...)))` zip-inseguro;
  `knowledge scaffold|bump` escrevem em site-packages quando `--dir` omitido.
- P2 `golden/`+`labs/` não empacotados; `lab`/`golden` cwd-âncora por design (verificar
  honestidade das mensagens).
- P3 `portal_adapter` fallback `parents[1]` assume src-layout; `portal/` no repo só tem manifest.

### the-forge
- P1 `agentic/agents/*.toml` não vai no wheel → `agents list` vazio silencioso;
  `docs/` não vai → docs-search no portal vazio (graceful, mas diferente do checkout).
- P2 `install update` depende de checkout registrado (sem caminho pip-upgrade puro).
- P3 contratos `forge/RuntimeInstallation|RuntimeDistribution` não existem — modelo atual
  distribuído em InstallationManifest/Receipt/Health/WorkspaceInstall/InstallEnvironment.

### forge-cli (npm)
- P2 método default = `git` clone; `registry` existe mas é opt-in — prompt exige PyPI como
  preferência #1 e clone apenas `--dev`.
- P2 instalação registry não gera launchers/PATH (nota manual); `~/.config/forjas/` não usado;
  nenhuma ponte com `~/.forge/installations/` escritos pelos bootstrap das forjas
  (dois registros paralelos: `~/.forge/installations` vs `~/.forge-cli/forges/state.json`).
- P3 `system.runtime.node` evidencia min 18 vs engines>=20; doc `receipt.json` vs código
  `install.json`; doctor emite `DoctorReport/v1` enquanto `ForgeHealthReport/v1` canônico
  existe sem consumidor; `files` omite `contracts/`; README npm com logo quebrado.

### forge-portal
- P3 dual version track (`package.json` 0.1.0 vs `PORTAL_VERSION` 1.0.0); `dist/` não
  retido como artefato CI; `WORKSPACE=ROOT.parent` assume layout de checkouts irmãos.

## 6. Requisitos do prompt → estado atual

| Requisito (ciclo) | Estado baseline |
|---|---|
| Wheel sem checkout (12.1) | 7/7 instalam + CLI roda; degradações de recurso listadas acima |
| Knowledge pós-checkout (12.2) | AWS OK; Azure P1; API P1; plataforma OK; doctors P2; the-forge parcial |
| Evals sem cwd (12.3) | Não portáteis em AWS/Azure/API; platform-forge já bundla |
| Env vars + registry canônico (12.4) | Installkit + `~/.forge/installations` existe; vars `<FORGE>_HOME|INSTALL_ROOT|VENV|PYTHON|CLI|LAUNCHER` escritas pelo bootstrap; aliases legados por auditar; `RuntimeInstallation/v1` a definir |
| Forge CLI PyPI-first (12.5–12.6) | Registry path completo mas opt-in; falta launcher/PATH e integração com `~/.forge` |
| MCP portátil (12.7) | `mcp_verify` real já existe no installkit e no CLI; verificado no AWS wheel |
| Federação via registry (12.8) | Já data-driven no the-forge |
| Portal (12.9) | Existente e madura; gaps menores |
| Segurança/supply-chain (12.10) | sha256 artifacts, OIDC publish, plan-tokens, lock offline existem; SBOM parcial (doctor-api) |
| Homologação E2E (12.11–12.13) | A executar |

## 7. Evidência complementar

- Wheels em `/tmp/cycle12-artifacts/<repo>/{*.whl,*.tar.gz}`; venvs de teste em
  `/tmp/forge-test-<repo>`; saídas brutas sob `/tmp/devin-overflows-1000/`.
- MCP verify AWS: handshake + `tools/list` (146) + `tools/call` segura — log em
  `/tmp/devin-overflows-1000/d3e45d7e/content.txt`.

## 8. Checkpoint — Fase C em andamento (doctor-data fechado)

Wheel-only verificado em `/tmp/fdd-ws` (venv `/tmp/fdd-venv`, wheel 1.0.2):

- `lab list` resolve `forge_doctor_data/_data/labs` (185 entradas) fora do checkout.
- `golden list`/`run` resolvem `_data/golden` (188); `golden update` (escrita)
  recusa root packaged com exit 2 e pede `--root` gravável.
- `knowledge new` sem `--dir` recusa escrita em site-packages (exit 2) quando o
  bundle está sob `purelib`; `--dir` grava normalmente (`myk/snowflake/versions.json`).
- Falha pré-existente (sem relação): `test_public_api_freeze` registra
  `package_version 1.0.0` vs pyproject `1.0.2` — reproduz na árvore limpa.

Pendentes Fase C→D: api-forge eval loaders (auditoria final de call sites),
registry `RuntimeInstallation/v1`, install.sh/ps1 canônicos, Forge CLI
PyPI-first + launchers, hosts/MCP/federation (12.7-12.8), portal (12.9),
security/test-matrix/homologação (12.10-12.13), data-sentinel-forge por último.

### api-forge — fechado (wheel 0.1.2, venv `/tmp/af-venv2`, ws `/tmp/af-ws2`)

- `evals list` resolve `apiforge/_data/evals/cases/platform.yaml` (4 casos).
- `evals economy` lê corpus empacotado (12 cases) e recusa honestamente
  `AF-EVALS-ECONOMY-BASELINE-MISSING` + unlock — baseline é estado do workspace.
- `resolve_evals_path` ganhou fallback de checkout (`pyproject.toml` marker)
  para editable install a partir de qualquer cwd; `field/export.EXPORT_DIR`
  auditado = destino de escrita, correto.
- Testes: 142 pass (k evals/paths/knowledge/matrix).

### 12.4/12.6 — env contract + bootstrap PyPI path

- `docs/cycle12/env-contract.md`: tabela canônica install-vars vs
  resource-overrides + semântica de raízes (§6.1/6.2/6.5).
- Resolvers AWS/Azure aceitam alias `SPARK_FORGE_*` (canonical prefixo do
  contrato de install); nome documentado continua `SPARKFORGE_*`.
- `forge_bootstrap.py --dist <spec>`: instala distribuição publicada
  (PyPI/wheelhouse), `source.kind="pypi-wheel"` +
  `installation_method` no manifesto; `--editable` continua dev-only e é
  mutuamente exclusivo com `--dist`.
- `forge/InstallationManifest/v1` ganhou `installation_method` — evolução do
  registry existente, não contrato paralelo (§6.3 cobre o papel de
  RuntimeInstallation).
- Gates: 72 installkit tests pass; evals/artifact AWS 20 pass; loader Azure
  43 pass.

### Review remediation — installkit/vendoring discipline

- `_installkit.py`: edição movida para o canônico `forge_installkit.py`,
  re-vendored com `_SOURCE_SHA256` novo — gate `test_vendored_kit_matches_canonical` verde.
- `InstallationManifest.schema.json`: `source.spec` + `installation_method`
  (enum `git-checkout|wheel|pypi|pypi-wheel`); emitters usam `kind:"pypi"`,
  `installation_method:"pypi-wheel"`.
- `forge_bootstrap.py` + `install.sh`/`install.ps1` (wheel-default agora nos
  TEMPLATES `INSTALL_SH`/`INSTALL_PS1`) re-vendored para os 6 repos;
  `vendor.py --check` = CLEAN em todos (incl. the-forge).
- `--dist` valida contra `forge.json.distribution` (recusa
  `FORGE-INSTALL-DIST-MISMATCH`); smoke: dry-run plana 6 estágios, mismatch recusa.
- AWS: guard `pyproject.toml` em `catalog_dir`/`knowledge_dir`; `AGENTS`/`EXECUTORS`
  lazy em `case/playbook.py`; docstring `evals/cli.py` com a cadeia de precedência;
  `PerguntaDeOuro.raiz_fixtures` propaga o `raiz` resolvido.
- api-forge: `resolve_evals_path` não remapeia absolutos inexistentes
  (typo honesto); 6 testes novos (packaged, checkout+marker, absoluto, não-evals).
- Ruff limpo nos 3 repos; gates: AWS 109, Azure 48, the-forge 146, api-forge 6 novos.

### Review remediation 2 — `--dist` correctness + packaged-asset reachability

- **C1 `compose_dist_req`**: extras entram entre nome e specifier —
  `sparkforge-aws[mcp]==0.5.2`, nunca `==0.5.2[mcp]` (specifier inválido que
  o `packaging` resolve para nenhuma versão). Extras já declarados no spec
  são mesclados com os do `forge.json` (`[old]` + `mcp` → `[mcp,old]`).
  Verificado com `packaging.Requirement`: `specifier.contains("0.5.2")`=True
  nos 5 casos (pin, extras declaradas, sem extras, range, merge).
- **C2 testes `--dist`**: 10 novos em `test_installkit_bootstrap.py` —
  split/compose do spec, dry-run, mode-conflict, dist-mismatch,
  `installation_method` e contrato de env publicado. 21 pass.
- **W1 HOME**: `environment_contract(has_checkout=False)` sob `--dist` —
  `<FORGE>_HOME` só é emitido com checkout real (env-contract.md §3).
- **W2** `load_packaged_packs` → `apiforge/_data/knowledge` (estava no layout
  pré-`_data`).
- **W3** `knowledge list|show|check|freshness|drift|impact` + MCP
  `knowledge_list` roteiam por `default_root()` — wheel-only:
  `knowledge list`=40 packs, `check`/`show`/`impact` OK de cwd vazio;
  `--root` explícito e `./knowledge` local continuam vencendo.
- **W4** `tests/test_artifact_contents.py` no api-forge — gate das 6
  force-includes; wheel real inspecionado: agents 31, skills 24,
  AGENT_PROTOCOL 1, portal_assets 44, `_data/knowledge` 411, `_data/evals` 349.
- **W5** `packaged_dir()` em `cli/common.py` — `importlib.resources.as_file`
  com `ExitStack` de vida-do-processo (materializa zipimport, no-op em
  wheel desempacotada); substitui `Path(str(files(...)))` em `_golden_root`,
  `_default_labs`, `_bundled_knowledge_root`. Guards de escrita intactos.
- Docstring `load_cases` reerguida; `forge-doctor-api lab` normaliza
  `target_path == Path("labs")` — `labs`, `labs/`, `./labs` caem no packaged
  (52 cenários, verificado na wheel 0.2.2 reinstalada).
- `env-contract.md`: emissão real `source.kind="pypi"` +
  `installation_method="pypi-wheel"` (doc estava `"pypi-wheel"` no kind).
- Re-vendor limpo: `vendor.py --check` CLEAN nos 7 repos (paths de
  `--installkit-pkg` agora relativos ao repo; dirs `repo/repo/` espúrios
  de um run anterior removidos).
- Gates: the-forge 61 (bootstrap+orchestration+schemas), api-forge
  knowledge 44 pass, ruff limpo nos 4 repos tocados.
- Reds pré-existentes inalterados: freeze 1.0.0/1.0.2 (doctor-data),
  0.2.1/0.2.2 (forge-cli).

### Review remediation 3 — gates do próprio repo verdes de novo

- **forge-doctor-api `test_package_carries_install_surface`**: repo carrega
  DOIS artefatos vendored do installkit (`src/.../_installkit.py` +
  `scripts/forge_installkit.py`); a re-vendorização só tocava o primeiro.
  `vendor.py` agora emite `scripts/forge_installkit.py` em lockstep quando o
  repo já o possui; os 6 especialistas sincronizados, `--check` CLEAN ×7.
- **platform-forge `test_economy_closure`**: `VALIDATION-RECEIPT.json`
  regerado via `scripts/validate.py --economy-receipt` — `validated_sha`
  volta a ∈ {HEAD, HEAD~1}; commit funcional → rebind commit é o ritual.
- **AWS `knowledge list|search`** implementados de verdade (o commit anterior
  alegava; só existiam `path|drift`): `list` projeta `available` de
  `knowledge_path`; `search` varre conteúdo offline com hits bounded.
- **api-forge `resolve_evals_path`**: fallback ancorado só no PRIMEIRO
  segmento — `mydata/evals/x` não remapeia mais (teste novo).
- Ambientais resolvidos: doctor-data `.venv` tinha dist-info 1.0.0 (reinstall
  editable → freeze 6/6 verde, red pré-existente eliminada);
  `ecosystem-compatibility.json` forge-cli 0.2.1 → 0.2.2 (seu package.json
  já era 0.2.2).
- Gates re-rodados: doctor-api 13, platform-forge 33, the-forge 45,
  AWS knowledge 11, api-forge 7 — todos verdes; worktrees limpos.
- Resta ambiental não-causada: `test_codeintel_security` no AWS falha sob
  Python 3.13 builtin `resource` (design de teste dependente de plataforma).

### Review remediation 4 — `forge.json.distribution` apontava para pacote errado

- **Crítico**: `api-forge/forge.json` dizia `apiforge` (dist real:
  `apiforge-af`); `the-forge/forge.json` dizia `theforge` (dist real:
  `theforge-core`). Com o valor stale, `--dist` recusava o pacote real
  (`FORGE-INSTALL-DIST-MISMATCH`) e aceitaria um homônimo estrangeiro —
  a ameaça §12.1/§13.5 que o guard existe para impedir. Corrigidos.
- **Gate novo** (`test_forge_json_distribution_matches_pyproject_name` em
  `test_ecosystem_compat.py`): `forge.json.distribution` ≡
  `pyproject [project].name` (PEP 503) para todo sibling com checkout —
  impede a classe de erro de voltar.
- **PEP 503**: `canonical_dist_name()` (stdlib `re`, sem dep em `packaging`)
  nas duas pontas do check — `apiforge_af==0.1.2` agora equivale a
  `apiforge-af`. Verificado: aceita os dois, recusa `apiforge==9.9`.
- **`suite_dir(nome)`** (AWS): sanitizado — separadores/`..`/absoluto viram
  `EvalsError`; callers CLI/MCP não atravessam mais as raízes de eval.
- **doctor-data scaffold**: guard de escrita agora sonda se o traversable
  bundled É um `Path` real (`isinstance(t, Path)`) — sob zipimport a
  materialização cai fora de `purelib` e o check de contenção falharia;
  agora recusa também por "não é fs real". 29 testes knowledge/scaffold verdes.
- **`knowledge_search`**: `truncated` só quando há hits não reportados;
  `matched` capped em 100 + `matched_total`.
- **ADR-deviation registrada**: `forge/RuntimeDistribution/v1` (§3.1) NÃO é
  contrato nomeado — a evolução foi absorvida em `InstallationManifest/v1`
  (`installation_method`, `source.spec`), decisão tomada no ciclo e aqui
  formalizada: novo contrato adiaria a homologação sem ganho semântico, e o
  schema já evoluiu de forma compatível.
- `vendor.py --check` CLEAN ×7 após re-vendor do bootstrap canônico.

### Review remediation 5 — eval loaders e gates do api-forge

- **api-forge ruff**: `PLW1510` (`check=False` no subprocess do wheel test),
  `PIE810` (tuple `endswith`), `ruff format` — `check` e `format --check`
  limpos em `src`/`tests` (1018 arquivos).
- **`knowledge-drift` vacuous-pass**: `run_knowledge_drift` agora chama
  `resolve_evals_path` e recusa corpus vazio com `AF-EVALS-INVALID` — antes
  retornava `{"cases": [], "passed": true}` wheel-only. Verificado em venv
  limpo de cwd vazio: 5 casos do `_data`, `passed: true` real.
- **`graph-quality`/`economy-matrix`**: `run_graph_quality` e `run_matrix`
  resolvidos; `verdict_for` resolve refs `tests/fixtures/…` via novo
  `resolve_task_resource` (workspace → `_data/tests` → checkout com
  pyproject) e `tests/fixtures` virou force-include
  (`apiforge/_data/tests/fixtures`). Wheel-only: graph-quality emite
  casos/precision reais; economy-matrix `passed:true` (16 tasks, mutação
  10/10).
- **`the-forge update()` pypi**: manifest `source.kind="pypi"` segue
  `pip install -U <spec>` (dry_run → UNVERIFIED), sem spec/dist → BLOCKED;
  `_run_pip` fatorado. Testes novos cobrem os dois ramos.
- **`manifest_for` fallback alinhado**: aceita `installation_method`
  explícito; sem ele deriva `pypi→pypi-wheel`, `editable→git-checkout`,
  wheel-build→`wheel` — mesma semântica do bootstrap.
- **platform-forge `data_path`**: `as_file` + `ExitStack` ate `atexit` —
  zip-safe igual ao `_packaged_dir` do doctor-data.
- **doctor-data resolver tests** (`test_packaged_resolvers.py`): 9 testes
  cobrindo `_packaged_dir`, `_golden_root` (+ refusal `for_write` rc=2),
  `_default_labs` (cwd vence + fallback packaged) e o guard de escrita do
  `knowledge_new` (purelib e traversable-não-Path); 6 pass / 3 skip fora
  de wheel.
- **AWS**: mensagem de override nomeia a var realmente usada
  (`SPARKFORGE_AWS_EVALS` ou alias `SPARK_FORGE_AWS_EVALS`); regressão do
  `knowledge drift`/`list` retornando `None` corrigida (`return 0`) —
  `test_fixtures_golden_knowledge_drift` 11/11.
- **Re-vendor**: `_installkit.py` + `scripts/forge_installkit.py` em
  lockstep novo (`29a1d628` ×12); `--check` silencioso nos 7.

### Review remediation 6 — update --to, --allow-url, hardening fina

- **`update --to` pypi**: compoe `distribution==<to>` (era `pip install -U
  <to>` solto — requirement invalido). Sem `distribution` no manifesto →
  BLOCKED. `_run_pip` recusa `venv` inexistente com FAIL nomeado em vez de
  FileNotFoundError (cobre checkout e pypi).
- **`--dist` URL gate**: referencia direta `name @ URL` agora exige
  `--allow-url` (`FORGE-INSTALL-DIST-URL` sem ele) — o escape-hatch de
  wheelhouse fica opt-in. Testes cobrem recusa e aceite.
- **`register()` fallback**: `installation_method` alinha com bootstrap —
  `editable→git-checkout`, wheel-build→`wheel`.
- **AWS**: `--limit >= 1` via `_positive_int` (negativos invertiam o
  slicing); `matched_files` dedupado entre core e packs; `playbook()`
  captura `SourcesError` no envelope `AdapterError`.
- **Re-vendor**: `forge_bootstrap.py` `02a8ef29` ×8 byte-identico.

### Review remediation 7 — Refusal fora do envelope, CI gate, `..`

- **`Refusal` fora do try (canonico)**: `split_dist_spec` corria antes do
  bloco que envelopa erros em JSON — `--dist '==1.0'` virava traceback rc=1
  sem recibo. Agora capturado no mesmo formato (envelope + rc 2) dos
  siblings. Teste `test_dist_malformed_spec_returns_json_refusal`. Hash
  `811b31f3` re-vendored ×8.
- **CI gate do api-forge**: `build>=1.0` entra nos dev extras —
  `test_artifact_contents` nao mais pula silenciosamente no job de unit
  (`.[dev,mcp]` passa a trazer `python -m build`).
- **`..` nos resolvers**: `resolve_evals_path` e `resolve_task_resource`
  rejeitam `..` em parts — paridade com `suite_dir` do AWS; paths ficam
  intactos e o caller reporta ENOENT honesto. Teste
  `test_dotdot_never_remaps`.
- **update() refinado**: `--to X` preserva os extras do spec registrado
  (`theforge-core[mcp]==X`); spec divergente do `distribution` → BLOCKED;
  `_run_pip` honra `verb` (era literal `"update"`).
- **AWS**: `evals list` liga `suites_disponiveis` a `python -m
  sparkforge_aws.evals list` (4 suites). `doctor-api lab` migrado de
  `Path(__file__)` para `as_file`+`ExitStack` (zipimport-safe, paridade
  com doctor-data).
- Nota de precedencia env>workspace registrada no env-contract como
  divergencia deliberada vs §4.3.
