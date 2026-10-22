# FORGE_CONTEXT_BASELINE — the-forge

Auditoria do ciclo 1 do Install 2.0 (spec `lf-0034`, spec-fonte
`prompt_evo_install2.0.md` §0–§3). Somente evidência: cada afirmação cita o
comando executado ou o arquivo/linha inspecionado. Nada neste documento
altera código de produção.

- **Repo:** `/home/edgar/Documentos/projetos/forjas/the-forge`
- **HEAD auditado:** `77654a54f7f188d20aff4600a0c5456b1f726821`
  (`fix: ecosystem compat matrix + version pins for 0.5.6`)
- **Versão:** `theforge-core 0.5.6` (`pyproject.toml [project] version`;
  `theforge --version` → `theforge 0.5.6`)
- **Python:** `>=3.11`; **deps de runtime:** `[]` (zero — stdlib-only;
  `pyproject.toml [project] dependencies = []`)
- **Data da auditoria:** 2026-10-22
- **Governança vigente:** Feature Freeze + dogfooding
  (`docs/feature-freeze.md`, `AGENTS.md`/`CLAUDE.md` invariantes)

---

## 1. Inspeção de arquitetura (§3.1)

### 1.1 Módulos

`src/theforge/` tem 192 arquivos `.py`
(`find src -name "*.py" | wc -l` → 192). Top-level: `cli/`, `contracts/`
(56 módulos), `install/` (4 módulos: `service.py` 888 linhas,
`providers.py` 353, `compatibility.py` 197, `render.py` 67), `protocol/`,
`registry/`, `routing/`, `providers/` (inclui `echo/`), `policy/`,
`workspace/`, `context/`, `planning/`, `excellence/`, `explain/`,
`environment/`, `interop/`, `forger/`, `ui/`, `runs/`, `security/`,
mais módulos soltos (`agents.py`, `knowledge.py`, `discovery.py`,
`orchestrate.py`, `portal_adapter.py`, `_installkit.py`,
`_forge_portal.py`, `_portal_telemetry.py`, …).

### 1.2 CLI

Entry points (`pyproject.toml [project.scripts]`): `theforge` e `forge`
→ `theforge.cli.main:main`. `.venv/bin/python -m theforge --help` lista 30
comandos: `init, doctor, setup, status, excellence, registry, economy,
knowledge, agents, capabilities, install, installations, graph, portal,
providers, specialists, hosts, task, orchestrate, provider, ask, plan,
workspace, explain, replay, resume, decisions, trace, memory, targets,
lab, remote`.

`theforge install --help` (wheel instalada, fora do checkout) expõe:
`plan, apply, status, doctor, repair, uninstall, update, auto,
mcp-verify`. Existe, portanto, um `theforge install` completo — ver §3.

### 1.3 Installkit

| Artefato | Papel | Evidência |
|---|---|---|
| `scripts/installkit/forge_installkit.py` | **Canônico** — "Forge Installation Contract v1 — reference engine" (1732 linhas) | docstring do arquivo |
| `scripts/installkit/forge_bootstrap.py` | **Canônico** — bootstrap de conta (1281 linhas): discover → resolve-python → create-venv → install-runtime → write-launcher → smoke-verify → register → report | docstring do arquivo |
| `scripts/installkit/vendor.py` | Vendora os dois para cada repo-Forge (427 linhas) | docstring |
| `src/theforge/_installkit.py` | Cópia vendored no wheel; `diff` com o canônico mostra só `_SOURCE_SHA256 = "bc189dd2ae0028ce"` vs `"canonical"` | `diff` executado |
| `scripts/forge_bootstrap.py` | Cópia vendored do bootstrap | `diff -q` = idêntico |
| `install.sh`, `install.ps1`, `install.windows.sh`, `setup.sh`, `setup.ps1` | Entry points de conta | root do repo |
| `forge.json` | Driver declarativo do bootstrap (`forge_id`, `package=theforge`, `distribution=theforge-core`, `cli=theforge`, `python>=3.11`, `lab.command`) | root do repo |

**O que `theforge install` escreve** (verificado em `/tmp/lf0034/consumer-repo`,
repo git vazio, wheel instalada em venv limpa):
`theforge install apply --yes` → `status: completed`, **336 managed_files
(todos kind=skill)**, 1 marker em `AGENTS.md` com bloco
`<!-- the-forge:managed:begin -->…:end -->`, ledger
`.forge/install/install-ledger.json` com 337 entradas
(336 skill + 1 marker), receipts em `.forge/install/receipts/`.
`theforge install doctor --json` → `status: healthy`,
`ledger PASS 337 managed entries`. `install uninstall` →
`removed: 337, kept: 0` — removeu somente o que o ledger possui.
Nenhum `.mcp.json` é escrito: `mcp_server_name=None` no `ForgeSpec`
(`src/theforge/install/service.py:39-40`) — the-forge não tem servidor
MCP próprio.

### 1.4 Integração com hosts

- **Fonte canônica de skills:** `agentic/skills/*.md` — 17 skills
  `forge-*` com frontmatter `+++` TOML
  (`scripts/agentic/render_skills.py` docstring).
- **Fonte canônica de agents:** `agentic/agents/*.toml` — 8 AgentSpec
  (`bootstrap-installation`, `capability-negotiator`, `cross-forge-planner`,
  `ecosystem-debugger`, `ecosystem-router`, `execution-orchestrator`,
  `forge-discovery`, `verification-orchestrator`), carregados por
  `src/theforge/agents.py` (`DEFAULT_AGENTS_DIR = parents[2]/agentic/agents`,
  linha 26).
- **Mirrors gerados e rastreados:** `.claude/skills` (50 arquivos git),
  `.devin/skills` (50), `.agents/skills` (84), `.codex/agents` (9),
  `.kiro` (28) — `git ls-files` por diretório.
- **kiro-\*:** 17 skills de workflow Kiro, **sem fonte canônica única** —
  mirrors hand-edited por host, drift auditado por
  `scripts/agentic/audit_assets.py` (docstring: "kiro-* hand-edited
  mirrors and forge-* rendered").
- **Gates:** `render_skills.py --check` (drift dos mirrors renderizados),
  `audit_assets.py` (perfil semântico das skills, suporte, invariantes de
  instruções — saída 1 com achados falhantes).
- **Destinos no consumidor** (`src/theforge/install/render.py:16-22`):
  `claude → .claude/skills`, `devin → .devin/skills`,
  `copilot → .github/skills`, `codex → .agents/skills`,
  agents `codex → .codex/agents`. Quando devin/codex/copilot presentes,
  `.agents/skills` também é escrito.

### 1.5 MCP

The-forge **não publica servidor MCP** (`ForgeSpec.mcp_command=()`,
`mcp_server_name=None`, `install/service.py:39-40`). O installkit suporta
chave gerenciada em `.mcp.json` (`mcp_set`/`mcp_unset`,
`forge_installkit.py:459-488`) e `install mcp-verify` faz handshake
JSON-RPC real initialize → tools/list → tools/call
(`forge_installkit.py:1499-1680`) — usado por forges que declaram
`mcp_server_name` (evidência: `forge_doctor_data` declara
`mcp_verify_tool="get_execution_baseline"`).

### 1.6 Empacotamento (pyproject.toml)

- Build: `hatchling>=1.25`; wheel `packages = ["src/theforge"]`.
- `[tool.hatch.build.targets.wheel.force-include]`:
  `.agents/skills → theforge/host_assets/skills`,
  `portal/assets → theforge/portal_assets`,
  `forge-knowledge → theforge/forge_knowledge` (comentário ADR-0058 /
  ciclo 11.2.1 E2E-M no próprio pyproject).
- `[tool.hatch.build.targets.sdist].exclude`: `/adapters`, `/.claude`,
  `/.devin`, `/.codex`, `/.kiro`, `/.tokensave`, `/CLAUDE.md`, `/AGENTS.md`.
- Adapters são distribuições separadas (`adapters/*/pyproject.toml`,
  ex.: `theforge-sparkforge-aws-adapter 0.3.0`, python `>=3.10`).

### 1.7 Schemas e manifestos

- `schemas/` — **74** JSON Schemas `theforge/<Name>/v1`
  (`ls schemas/*.json | wc -l` → 74), incl. `SpecialistCapability`,
  `SpecialistDelegation`, `EvidenceHandoff`, `AgentSpec`,
  `InstallationPlanV2`, `ForgeKnowledge`, `ForgeManifest`,
  `McpRegistryDocument`. Regenerados por
  `python -m theforge.contracts.schema schemas` (invariante AGENTS.md).
- `docs/portable-installation/schemas/` — 8 schemas da família `forge/*`:
  `InstallationManifest`, `InstallReceipt`, `InstallationHealth`,
  `WorkspaceInstall`, `EcosystemCompatibility`, `BenchmarkResult`,
  `BenchmarkSuite`, `MultiForgeScenario`; emitidos pelo installkit e
  validados por `tests/test_installkit_schemas.py`.
- `contracts/experience/` — 7 schemas (`agent-catalog`,
  `documentation-review`, `experience-parity`, `experience-state`,
  `host-integration`, `installation-state`, `task-invocation`).
- `ecosystem-compatibility.json` — `forge/EcosystemCompatibility/v1`,
  release `2026.10`, 9 componentes com dist/versão/scheme + 6 famílias de
  contratos com janelas `min_major/max_major`
  (`src/theforge/install/compatibility.py` valida).
- `~/.forge/installations/the-forge.json` — `forge/InstallationManifest/v1`
  escrito pelo bootstrap (registry de instalações de conta).

### 1.8 Knowledge / Rules / Evals / Protocols / Políticas

- **Knowledge:** `forge-knowledge/*.json` — 7 pacotes (um por
  especialista + data-sentinel). Carregados por `src/theforge/knowledge.py`
  com **fallback bundled** (`_BUNDLED_KNOWLEDGE_DIR =
  theforge/forge_knowledge`, linhas 24-30) — funciona fora do checkout:
  `theforge knowledge list` na wheel lista as 7 forjas e famílias.
- **Rules:** não existe catálogo `rules/` como dado; roteamento e política
  vivem em código (`src/theforge/routing/`, `src/theforge/policy/`) e nos
  contratos.
- **Evals:** não existe diretório `evals/`; testes (`tests/`, incl.
  `test_installkit*` 743+632+86 linhas, `test_packaging.py`,
  `test_install_e2e.py`), `e2e/` e `audit/` (scenarios + tooling:
  `collect_baseline.py`, `run_installers.py`, `run_mcp_handshakes.py`,
  `run_scenarios.py`, `validate_contracts.py`).
- **Protocols:** Forge Protocol v1 — `src/theforge/protocol/transport.py`
  (subprocess + JSON stdin/stdout, `MAX_STDOUT_BYTES=8MiB`,
  `safe_env`, `redact_text`); `forge/*` install contracts;
  `theforge/<Name>/v1`. `docs/protocol.md`.
- **Verificadores:** `scripts/check_gates.py`, `scripts/agentic/
  audit_assets.py`, `render_skills.py --check`, zero-deps gate +
  fresh-install gate (`tests/test_packaging.py:191-216`), `doctor`,
  `conformance.py`, `lab_gate.py`.
- **Políticas:** `src/theforge/policy/` (engine), `remote-policy.toml`
  (remote), `security/redact`, `docs/feature-freeze.md`, `docs/security.md`.
- **Templates:** `templates/` — 7 diretórios (`api-apiforge`,
  `custom-specialist`, `mcp-host-config`, `multi-repo-theforge`,
  `pyspark-aws`, `pyspark-azure`, `terraform-platform`), cada um com
  `check.sh` + `README.md`.
- **Docs de instalação:** `docs/installation/` (16 arquivos: quickstart,
  account/workspace/global/family-onboarding, por host, mcp, uninstall,
  update-and-repair, troubleshooting) e `docs/portable-installation/`
  (README + contract-v1 + bootstrap + audit + matrices + risk + reports/).
- **CI/CD:** `.github/workflows/` — `ci.yml`, `compat.yml`,
  `release-gates.yml`, `release-compat.yml`, `publish-pypi.yml`,
  `ecosystem-real.yml`, `provider-surface-drift.yml`.
- **PyPI:** `theforge-core` publicada; 0.5.6 baixada e comparada (§4).

### 1.9 Canônico vs derivado

| Canônico | Derivado | Gerador / gate |
|---|---|---|
| `agentic/skills/*.md` | `.claude/skills/forge-*`, `.devin/skills/forge-*`, `.agents/skills/forge-*` | `render_skills.py --check` |
| `agentic/agents/*.toml` | `.codex/agents/*.toml` | `render_agents.py` |
| `scripts/installkit/*` | `src/theforge/_installkit.py`, `scripts/forge_bootstrap.py` (+ cópias nos repos-Forge) | `vendor.py --check`, `_SOURCE_SHA256` |
| `src/theforge/contracts/*` | `schemas/*.schema.json` | `python -m theforge.contracts.schema schemas` |
| `portal_core/forge_portal.py` (forge-portal) | `src/theforge/_forge_portal.py`, `_portal_telemetry.py` | `forge-portal/scripts/vendor.py --check` |
| `.claude/skills/kiro-*`, `.devin/…`, `.agents/…` (hand-edited) | os outros mirrors kiro | `audit_assets.py` |
| `forge-knowledge/*.json` | `theforge/forge_knowledge/` no wheel | `test_built_wheel_carries_forge_knowledge` |

---

## 2. Matriz de recursos (§3.2)

Colunas preenchidas só com evidência executada nesta auditoria.
"Alvo" = `/tmp/lf0034/consumer-repo` (git init vazio, install via wheel
em venv limpa). "Host" = convenção de diretórios + markers; o bloco
gerenciado de `AGENTS.md` foi de fato injetado como instrução ativa no
contexto de um agente lendo aquele diretório (prova de descoberta).

| Recurso | Existe na fonte | Está no wheel | Instalado no alvo | Descoberto pelo host | Utilizável | Verificado |
|---|---|---|---|---|---|---|
| Skills | Sim — 34 (17 `forge-*` canônicas em `agentic/skills/` + 17 `kiro-*` mirrors) | Sim — `theforge/host_assets/skills/` = 84 arquivos (mirror `.agents`) | Sim — `install apply --yes` escreveu 336 arquivos (84×4 hosts; `--host claude` sozinho: 84 em `.claude/skills`) | Sim — dirs por host + marker em `AGENTS.md` | Parcial — todos os alvos recebem o **formato codex** (`<background_information>`/`<instructions>`), sem `allowed-tools`/`argument-hint` (§3.3.4) | `test_install_e2e.py` + execução real desta auditoria |
| Agents | Sim — 8 `agentic/agents/*.toml` | **Não** — `unzip -l` mostra 0 `host_assets/agents` | **Não** — `--components agents` escreveu 0 arquivos a partir da wheel | Não | **Não via PyPI** — `theforge agents list` → `no agent specs`; em checkout funciona | Execução real (§4.3) |
| MCP | N/A — the-forge não tem servidor MCP (`mcp_server_name=None`) | N/A | N/A — nenhum `.mcp.json` escrito | N/A | N/A | `install mcp-verify` → NOT_APPLICABLE |
| Knowledge | Sim — `forge-knowledge/` 7 pacotes | Sim — `theforge/forge_knowledge/` (7 JSONs) | Não copiado — fica bundled no pacote, alcançável por `theforge knowledge list` | Só via CLI — nenhum handle instalado no alvo | Sim via CLI | `test_built_wheel_carries_forge_knowledge` + execução real |
| Rules | Não como catálogo (`routing/`, `policy/` em código) | Como código, não como dado | Não | Não | N/A | — |
| Evals | Não como artefato instalável; `tests/`+`e2e/`+`audit/` | Não (tests fora do wheel) | Não | Não | N/A | — |
| Protocols | Sim — Forge Protocol v1 (`protocol/`), contratos `theforge/*`+`forge/*`, `docs/protocol.md` | Como código; `docs/` e `schemas/` **fora** do wheel | Não | Não | Sim (runtime) | `python -m theforge.contracts.schema` |
| Verificadores | Sim — `check_gates.py`, `audit_assets.py`, `render_skills --check`, gates de wheel, `doctor` | Não (`scripts/` fora do wheel); `doctor` sim (CLI) | `install doctor` disponível no alvo | N/A | Sim | Execução real (`doctor → healthy`) |
| Políticas | Sim — `policy/`, `remote-policy.toml`, `security/redact`, feature-freeze | Parcial (engine em código; docs fora) | Não | Não | Sim (runtime) | — |

---

## 3. Análise do instalador (§3.3)

`theforge install` **existe e cobre o ciclo inteiro**. Respostas às
perguntas do spec, com evidência:

### 3.3.1 Resolução do alvo e scopes

- `scope=project` (default): `resolve_scope` (`forge_installkit.py:547-563`)
  resolve `explicit > _find_vcs_root > _find_state_root(.forge/install)`,
  recusando `FORGE-INSTALL-NOT-A-REPO` sem nenhum.
  **Ressalva (gap §5):** a CLI passa `--root` com **default `"."`**
  (`cli/main.py:117`), então `explicit=cwd` sempre — a recusa E_NOTREPO é
  inalcançável via CLI. Evidência: em `/tmp/lf0034/no-repo3` (sem `.git`),
  `theforge install apply --yes` → `completed`, `target_root=no-repo3`;
  `service.install()` no mesmo dir → `InstallError
  FORGE-INSTALL-NOT-A-REPO`.
- `scope=workspace`: `_find_workspace_root` procura
  `forge.workspace.yaml|json`, `.forge-workspace`, `pyproject.toml` com
  `tool.forge.workspace|tool.uv.workspace`; fallback `explicit > vcs > cwd`.
  `install auto --scope workspace` descobre membros = checkouts `.git`
  até profundidade 2 (`discover_projects`, `:1425-1451`), com
  precedência: membro já instalado em project-scope mantém o seu
  (`_member_state` em `install/service.py:743-754`); `--member` faz
  fan-out por membro; manifest `forge/WorkspaceInstall/v1` em
  `<ws>/.forge/workspace-install.json` com merge por
  `(path, forge_id)` preservando `created_at`.
- `scope=user`: `root=$HOME`, `state_dir=~/.forge`
  (`user_state_dir="~/.forge"`, service.py:51), dirs de host `~/.claude/…`
  (`_host_dirs`, `:578-586`).

### 3.3.2 Copiados / referenciados / ignorados

- **Copiados:** assets renderizados (`render_assets` → skills e, quando a
  fonte existe, agent TOMLs), blocos de marker, chave `.mcp.json`
  gerenciada (não se aplica a the-forge), estado (ledger, components.json,
  receipts).
- **Referenciados:** nenhum asset é referenciado — tudo é copiado como
  bytes gerenciados com sha256 no ledger.
- **Ignorados (sem handle de instalação):** `forge_knowledge` (fica no
  pacote; `theforge knowledge` alcança), `agentic/agents` (deveria ser
  copiável mas falta no wheel — §5 P0), knowledge/rules/evals/protocols
  do spec (não existem como artefatos de consumidor), portal (assets só
  no pacote, servidos por `theforge portal`).
- **Merge:** `apply_marker_block` (`:427-437`) — bloco delimitado, conteúdo
  do usuário preservado; `AGENTS.md` é criado se ausente, `CLAUDE.md`
  recebe bloco **só se já existir** (`:808-809`); `.mcp.json` via
  `mcp_set` — chave gerenciada em `mcpServers` + trilha `_forge_managed`.
- **Ownership:** ledger sha256 `.forge/install/install-ledger.json`
  (`forge/InstallLedger/v1`): `entries[path]={sha256,kind,action,managed}`;
  arquivos pré-existentes idênticos viram `adopted` (rastreados, nunca
  deletados); pré-existentes diferentes são pulados como "user-owned"
  (`:785-796`); edição manual de arquivo gerenciado é tratada como
  user-owned no uninstall (`:1213-1220`).
- **Uninstall:** remove só `managed`, excisa blocos de marker, unset da
  chave MCP, prune de dirs vazios, `--purge` apaga o state_dir.
  Verificado: `removed:337 kept:0`.
- **Repair:** re-escreve conteúdo canônico dos drifted (`missing`/
  `modified`) com re-heal kind-aware (marker/mcp/asset), backup prévio em
  `state_dir/backups/` (`:1115-1192`).
- **Update:** só para runtime instalado pelo bootstrap (`install update`):
  `pip install -U <dist>[extras]==<to>` na venv registrada; `latest` é
  recusa nomeada; `--to` com referência direta PEP 508 recusado; specs
  redigidos (`***@`) recusados; `--repo` em instalação pypi recusado
  (`service.py:218-361`).
- **Host selection:** `--host claude|devin|codex|copilot|all|none`
  (`_hosts()`, service.py:97-112); `none`/ausente = opt-out explícito.
- **Perfis:** `minimal` (config,mcp,marker,state) /
  `recommended`,`full` (+skill,agent) (`:595-600`);
  `--components skills,agents,mcp,tui,graph-studio` filtra kinds e grava
  `components.json`; `--gateway-profile economy|balanced|deep` vira
  `options.execution_profile`.
- **Governança:** `--yes`/`--approve` ou `--dry-run` obrigatórios
  (`FORGE-INSTALL-PLAN-NOT-APPROVED`, exit 4 — `test_install_e2e.py:41-45`);
  lock O_EXCL com reclaim de lock velho (`_Lock`); journal com rollback
  de writes em falha (`_rollback_writes`); `redact_url_userinfo` em
  specs/paths; atomic writes em todo o estado.

### 3.3.3 Delegação (`install auto`)

`install_auto` (`service.py:495-712`) lê `~/.forge/installations/*.json`
e delega `<cli> install --scope S --root R --host H --profile P
[--components] --yes|--dry-run` (ou `install_command` argv-template do
manifest com `{python}`/`{checkout}`/`{install_root}`) a cada forge —
**a própria forge se instala**; the-forge coordena e roda
`sync_provider_registry` (approval-gated, `install/providers.py`).
`--forge` restringe a uma; sem registros → `BLOCKED` honesto.
Nesta máquina: `ls ~/.forge/installations/` → 7 manifests
(the-forge, api-forge, platform-forge, spark-forge-aws/azure,
forge-doctor-data/api).

### 3.3.4 Fidelidade por host (evidência negativa)

`install/render.py` usa **uma única fonte** (`.agents/skills` do checkout
ou `host_assets/skills` do wheel) e copia bytes idênticos para
`.claude/skills`, `.devin/skills`, `.github/skills` e `.agents/skills`.
Prova: `install apply --yes --host claude` em consumer-repo3 gravou em
`.claude/skills/forge-routing/SKILL.md` o corpo com
`<background_information>`/`<instructions>` (formato codex) e sem
`allowed-tools`/`argument-hint` — `diff` com o `.claude/skills/`
canônico do repo → **DIFFERENT**. O render por host
(`render_skills.py`) existe mas não é usado pelo instalador.

---

## 4. Diagnóstico PyPI (§3.4)

Comandos executados (nenhum `pip install -e` usado como prova):

```text
.venv/bin/python -m build --outdir /tmp/lf0034/dist-fresh
  → Successfully built theforge_core-0.5.6.tar.gz e .whl
  (wheel construída A PARTIR do sdist — prova de completude do sdist)
python3 -m venv /tmp/lf0034/venv-clean
venv-clean/bin/pip install dist-fresh/theforge_core-0.5.6-py3-none-any.whl
venv-clean/bin/pip download theforge-core==0.5.6 --no-deps -d pypi056
```

### 4.1 Conteúdo real do wheel (local, HEAD)

`unzip -l dist-fresh/theforge_core-0.5.6-py3-none-any.whl` →
**334 arquivos, 3.905.699 bytes**. Recorte:

| Presente | Ausente |
|---|---|
| `theforge/` inteiro (código) | `host_assets/agents/` (0 arquivos) |
| `theforge/_installkit.py` (63.534 B) | `scripts/` (sdist-only) |
| `theforge/host_assets/skills/` (84 arquivos) | `agentic/`, `docs/`, `schemas/` |
| `theforge/portal_assets/` (46) | `templates/`, `tests/` |
| `theforge/forge_knowledge/` (7 JSONs) | `forge.json`, `install*.sh/ps1` |
| `dist-info` c/ `entry_points.txt` | `ecosystem-compatibility.json` |

sdist: 1763 membros — inclui `src/`, `scripts/`, `.agents/skills`
(necessário p/ rebuild do wheel — test gate em `test_packaging.py:296-301`),
`docs/`, `tests/`, `forge.json`, `install.sh`, `ecosystem-compatibility.json`;
exclui `adapters`, `.claude`, `.devin`, `.codex`, `.kiro`, `CLAUDE.md`,
`AGENTS.md` (conforme exclude declarado + gate `test_packaging.py:237-245`).

### 4.2 Instalação em venv limpa + execução fora do checkout

```text
/tmp/lf0034/venv-clean/bin/theforge --version        → theforge 0.5.6
cd /tmp/lf0034/consumer-repo && git init
theforge install apply --yes --json
  → status=completed, managed_files=336 (todos skill),
    markers=[AGENTS.md], context.skills_bytes=968144
theforge install doctor --json   → status=healthy (337 ledger entries)
theforge install uninstall --json → removed=337 kept=0
theforge install apply --dry-run --json → status=planned, 336 planned_files
theforge agents list             → "no agent specs"
theforge knowledge list          → 7 pacotes listados (bundled funciona)
```

### 4.3 Comparação com PyPI 0.5.6

`diff` das listas de arquivos do wheel local vs o wheel publicado
(`pypi056/theforge_core-0.5.6-py3-none-any.whl`, 1,3 MB comprimido):
**vazio — conteúdo idêntico** (mesmos 334 nomes; RECORD com o mesmo
tamanho 31.633). Não há drift entre HEAD local e a versão publicada.

### 4.4 Falhas observadas na wheel

1. `agentic/agents/` não é empacotado → `theforge agents list` retorna
   `no agent specs` e `install apply --components agents` escreve
   **0 arquivos** (`agents_bytes: 0`). `render._agents_src()` já procura
   `host_assets/agents` (render.py:41) — falta só o force-include; e
   `agents.py:26` não tem fallback bundled (o fix que
   `knowledge.py:24-30` recebeu no ciclo 11.2.1 não foi aplicado aqui).
2. Skills instaladas em formato único (§3.3.4).
3. `python -m theforge.contracts.schema --help` interpreta `--help` como
   diretório de saída e **cria `--help/`** com os schemas (quirk de UX;
   removido o artefato criado nesta auditoria).

---

## 5. Gaps, causas-raiz, riscos, decisões e migração

### P0

**P0-1 — `agentic/agents/` ausente do wheel: registry de agents e
componente `agents` quebrados fora do checkout.**
- Evidência: `unzip -l` (0 `host_assets/agents`); `theforge agents list`
  → `no agent specs`; `--components agents` → 0 writes.
- Causa-raiz: (a) falta `agentic/agents → theforge/host_assets/agents`
  no `force-include` (e no sdist, p/ wheel-from-sdist); (b)
  `agents.py:26 DEFAULT_AGENTS_DIR` aponta só para o repo — sem o
  fallback bundled que `knowledge.py:24-30` já tem.
- Risco: hosts que consultam `check_authority`/`agents` numa instalação
  PyPI veem ecossistema vazio silenciosamente.
- Decisão proposta: empacotar os TOMLs + fallback bundled (mesmo padrão
  de `knowledge.py`) + gate de wheel (`test_built_wheel_carries_agents`).

### P1

**P1-1 — Skills instaladas sem fidelidade por host.**
- Causa-raiz: `install/render.py` usa só `.agents/skills`; o renderer
  multi-formato (`render_skills.py`) não participa do install.
- Risco: Claude perde `allowed-tools`/`argument-hint`; corpo leva markup
  codex; hosts não-codex recebem envelope estranho.
- Decisão proposta: render por host no install (consumir
  `agentic/skills` canônico via render_skills ou bundle multi-formato).

**P1-2 — Entry points de host mínimos (ciclo 3 do install-2.0).**
- Hoje: marker de ~5 linhas em `AGENTS.md` (+ `CLAUDE.md` só se existir).
  Spec pede templates AGENTS.md/CLAUDE.md/AGENT_PROTOCOL.md com
  descoberta de forjas, registry pointer, protocolo operacional e merge
  seguro. A mecânica de merge (marker blocks) já existe — falta conteúdo.
- Decisão: templates em `install/` renderizados por perfil/host,
  mantendo o contrato "nunca criar CLAUDE.md sem existir / nunca
  sobrescrever conteúdo do usuário".

**P1-3 — Sem registry de contexto no workspace (ciclo 2).**
- Hoje existem: ledger de arquivos `.forge/install/` (por alvo),
  `~/.forge/installations/` (conta, escrita pelo bootstrap) e
  `workspace-install.json` (fan-out). O spec pede
  `.forge/context/registry.json` + `capabilities/<forge>.json` +
  `ROUTING.md` — **subsistema novo** → exige ADR sob Feature Freeze
  (`docs/feature-freeze.md`): evidência de dogfooding e justificativa de
  por que o registry atual não cobre o caso.

**P1-4 — Knowledge/rules/evals/protocols sem handle de instalação.**
- `forge_knowledge` é bundled e alcançável por CLI, mas nada no alvo
  aponta para ele; rules/evals/protocols não existem como artefatos
  instaláveis/referenciáveis (não são catálogos de dados em the-forge).
- Decisão: publicar handles (manifest de capacidades → o
  `forge-context/v1` do ciclo 2) em vez de copiar conteúdo — coerente
  com o modelo "referenciar" do prompt §2.3.

### P2

- **P2-1 — E_NOTREPO inalcançável na CLI** (`--root` default `"."`):
  o contrato documentado ("no VCS root → recusa") não é exercido via
  CLI; instalar num diretório errado despeja 336 arquivos. Decisão:
  default `--root=None` no subparser de install ou confirmação explícita
  quando não há `.git`.
- **P2-2 — kiro-\* instaladas no consumidor**: 17 skills internas de
  workflow Kiro vão junto (metade do payload). Decisão: perfil
  `forge-*`-only para consumidores ou componente separado.
- **P2-3 — kiro-\* sem fonte canônica única** (mirrors hand-edited;
  `audit_assets.py` audita, `render_skills.py` não gera).
- **P2-4 — Sem servidor MCP próprio** (por design: the-forge é o
  configurador, não um servidor). Installs não escrevem `.mcp.json`;
  descoberta depende de markers/CLI.
- **P2-5 — Estado de dogfooding local velho**: `~/.forge/installations/
  the-forge.json` registra `theforge 0.5.0` git-checkout `d405e55`
  (`distribution: "theforge"`, sem `installation_method`) — drift do
  registry, não do produto; `install update` cobre só wheel/pypi, não
  refresh de manifest git-checkout.
- **P2-6 — `contracts.schema --help` cria dir `--help/`** (ferramenta de
  regen sem flag de help).

### Consideração de governança (Feature Freeze)

O install-2.0 (ciclos 2–8 do spec-fonte) introduz subsistemas novos —
`.forge/context/*`, contrato `forge-context/v1`, templates de entry
points, classificação de evals. Pela fase atual
(`docs/feature-freeze.md`): permitido sem ADR = bugfix, segurança,
compatibilidade, performance, docs, testes, pequenas correções CLI/UX.
Mapeamento sugerido: **P0-1 é bugfix puro** (empacotamento + fallback
espelhando `knowledge.py`); **P1-1 é bugfix/compatibilidade** de
renderização; **P1-2/P1-3/P1-4 são features novas → ADR com evidência
de dogfooding antes de implementar** (o ciclo de auditoria em si é o
artefato de evidência).

### Plano de migração proposto

1. **Bugfix de empacotamento (sem ADR):** force-include `agentic/agents`,
   fallback bundled em `agents.py`, gate de wheel; (opcional) `--root`
   sem default `"."` no install; help flag em `contracts.schema`.
2. **Fidelidade de host no install:** render_skills por host dentro do
   install (mesmo gerador, fonte canônica única).
3. **ADR → entry points + registry de contexto:** templates
   AGENTS.md/CLAUDE.md/AGENT_PROTOCOL.md gerenciados por marker;
   `.forge/context/registry.json` como projeção do ledger +
   installations, `forge-context/v1` como manifesto de capacidades com
   handles para knowledge/CLI.
4. **Compatibilidade retroativa:** `forge/*` v1 é estável
   (`ecosystem-compatibility.json` fixa janelas); evoluir por adaptadores,
   não substituir manifestos (spec §4.4).

---

## Apêndice — comandos executados

```text
# inspeção
git log -1 --format='%H %s'
find src -name "*.py" | wc -l                 → 192
ls schemas/*.json | wc -l                     → 74
git ls-files .claude .devin .agents .codex .kiro → 50/50/84/9/28
diff scripts/installkit/forge_installkit.py src/theforge/_installkit.py
  → só _SOURCE_SHA256 ("canonical" → "bc189dd2ae0028ce")
.venv/bin/python -m theforge --help | install --help
ls ~/.forge/installations/                    → 7 manifests

# build + prova PyPI
.venv/bin/python -m build --outdir /tmp/lf0034/dist-fresh   → OK (wheel from sdist)
unzip -l dist-fresh/theforge_core-0.5.6-py3-none-any.whl    → 334 files
tar -tzf dist-fresh/theforge_core-0.5.6.tar.gz | wc -l      → 1763
python3 -m venv /tmp/lf0034/venv-clean && pip install <wheel>
pip download theforge-core==0.5.6 --no-deps -d pypi056       → OK
diff <(unzip -l pypi056/...) <(unzip -l dist-fresh/...)      → (vazio — idêntico)

# execução fora do checkout (venv limpa)
cd /tmp/lf0034/consumer-repo && git init
theforge install apply --yes --json            → completed, 336 skill files
theforge install doctor --json                 → healthy, 337 entries
theforge install uninstall --json              → removed 337, kept 0
theforge install apply --dry-run --json        → planned, 336 planned_files
theforge install apply --yes --host claude     → 84 files só em .claude/skills
theforge install apply --yes --components agents → 0 files (gap P0)
theforge agents list                           → "no agent specs" (gap P0)
theforge knowledge list                        → 7 pacotes (bundled OK)
diff .claude/skills/forge-routing/SKILL.md <repo>/.claude/.../SKILL.md → DIFFERENT
service.install() em dir sem .git              → FORGE-INSTALL-NOT-A-REPO
theforge install apply --yes (mesmo dir, CLI)  → completed (--root default ".")
```
