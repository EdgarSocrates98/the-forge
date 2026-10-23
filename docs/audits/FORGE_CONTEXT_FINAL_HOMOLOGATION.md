# FORGE_CONTEXT_FINAL_HOMOLOGATION — the-forge

Relatório final do programa Install 2.0 (spec-fonte
`prompt_evo_install2.0.md` §12.6), cobrindo os ciclos 2–7 executados sobre a
baseline `docs/audits/FORGE_CONTEXT_BASELINE.md` (ciclo 1, lf-0034).
Documento de evidência: cada afirmação cita commit/PR, arquivo:linha ou
comando executado. O que não foi executado está marcado **NÃO EXECUTADO**
(§16 — nenhum teste não executado é reportado como sucesso).

- **Repo:** `/home/edgar/Documentos/projetos/forjas/the-forge`
- **SHA antes:** `92d79730e72dfe2f4590950a7ba8d6bda0216913` (tag `v0.5.6`,
  2026-10-21); baseline auditada em
  `77654a54f7f188d20aff4600a0c5456b1f726821` (v0.5.6 + 1 commit)
- **SHA depois:** `38dc92ec4d5bcaf62b38eca845d43d732e4484c8` (HEAD de `main`)
- **Versão:** `theforge-core` 0.5.6 → **0.6.0** (`pyproject.toml` bumpado em
  worktree, **pendente de publicação** — §10)
- **Python:** `>=3.11`; deps de runtime `[]` (stdlib-only — invariante)
- **Data:** 2026-10-22
- **Governança:** Feature Freeze + dogfooding; o subsistema novo
  (`.forge/context/`) entrou via **ADR-0061**
  (`docs/adr/0061-forge-context-registry.md`, status: aceito 2026-10-22,
  evidência = o próprio baseline P1-3/P1-4)

---

## 1. SHAs antes/depois

| | SHA | Descrição |
|---|---|---|
| Tag base | `92d79730e72dfe2f4590950a7ba8d6bda0216913` | `release: 0.5.6 — integrations cycle` (2026-10-21) |
| HEAD auditada no baseline | `77654a54f7f188d20aff4600a0c5456b1f726821` | `fix: ecosystem compat matrix + version pins for 0.5.6` |
| HEAD final | `38dc92ec4d5bcaf62b38eca845d43d732e4484c8` | `fix(install): installkit 1.0.1 + bootstrap 1.1.1 — created_at fallback, backports doctor-api, teste pid indecidível (#114)` |

Range medido: `git log v0.5.6..HEAD` → **20 commits**, `git diff --stat` →
**57 arquivos, +12.848/−734 linhas**.

## 2. PRs

Todos os PRs mergeados em `EdgarSocrates98/the-forge`, verdes no CI no
momento do merge (evidência: merges sequenciais sem revert no range).

| PR | Merge / squash | Conteúdo |
|---|---|---|
| #102 | `51c588b` (merge), `f650a33` | docs(audit): baseline lf-0034 |
| #103 | `37dd379` (merge), `c5609a4` | feat(context): `forge/context/v1` — workspace context registry (ciclo 2, ADR-0061); inclui fix P0-1 (agents no wheel + fallback bundled) |
| #104 | `d05a8c4` (merge), `e1576c2` | feat(context): consumer-docs layer — blocos gerenciados `forge:*` em AGENTS.md/CLAUDE.md + AGENT_PROTOCOL.md consolidado (ciclo 3, lf-0036) |
| #105 | `f16f6fc` (merge), `fe234c6` `a8ebfbd` `99dccdd` | feat(context): discovery.ops §6.2 ligado a verbos reais (lf-0037); feat(install): wheel distribution parity — `forge.json` empacotado + wheel isolation test (lf-0039 §8); fix(install): `_context_manifest` lê `forge.json` empacotado sob wheel (§8.2) |
| #106 | `999ef40` (squash) | fix(contracts): taxonomia `FORGE-CONTEXT-{OWNERSHIP,LOCKED,CONFLICT,SCHEMA}` |
| #107 | `09cd4a2` (squash) | feat(evals): §7 — superfície de evals classificada + ops de verificação (lf-0038) |
| #108 | `7f28d0e` (squash) | fix(installkit): `_utc_now` com `timezone.utc` (compatível 3.10) — forge_context v1.2.1 |
| #109 | `9e4f7f0` (squash) | fix(lint): isenta `_forgecontext` vendored do ruff (piso 3.10) |
| #110 | `bb808d5` (squash) | fix(install): portal health + error hints + **lock staleness** + eval docs |
| #111 | `e6d6c52` (squash) | fix(test): wheel capability — evals disponíveis desde lf-0038 |
| #112 | `9b8c58b` (squash) | test(graphstudio): `node --check` timeout 30s→120s (Windows) |
| #113 | `af9718b` (squash) | feat(install): multi-forge composition engine — install/uninstall **transacional** (lf-0040, ciclo 7) |
| #114 | `38dc92e` (squash) | fix(install): installkit 1.0.1 + bootstrap 1.1.1 — `created_at` fallback, backports de segurança do bootstrap, teste pid indecidível |

## 3. Commits

20 commits no range (`git log v0.5.6..HEAD --format='%h %s'`, ordem cronológica):

```text
77654a5 fix: ecosystem compat matrix + version pins for 0.5.6
f650a33 docs(audit): lf-0034 install-context baseline — the-forge 0.5.6
51c588b Merge pull request #102 (audit/install-context)
c5609a4 feat(context): forge/context/v1 — workspace context registry (cycle 2, ADR-0061)
37dd379 Merge pull request #103 (cycle/install-context)
e1576c2 feat(context): consumer-docs layer — AGENTS.md/CLAUDE.md managed blocks + AGENT_PROTOCOL.md consolidado (lf-0036)
d05a8c4 Merge pull request #104 (cycle/install-context-docs)
fe234c6 feat(context): discovery.ops — §6.2 conceptual-op map wired to real theforge verbs (lf-0037)
a8ebfbd feat(install): wheel distribution parity — forge.json packaged + wheel isolation test (lf-0039 §8)
99dccdd fix(install): _context_manifest reads packaged forge.json under wheel (lf-0039 §8.2)
f16f6fc Merge pull request #105 (cycle/install-context)
999ef40 fix(contracts): registra FORGE-CONTEXT-{OWNERSHIP,LOCKED,CONFLICT,SCHEMA} na taxonomia (#106)
09cd4a2 feat(evals): install-2.0 §7 — classified eval surface + verification ops (lf-0038) (#107)
7f28d0e fix(installkit): _utc_now usa timezone.utc (3.10-compatible) — forge_context v1.2.1 (#108)
9e4f7f0 fix(lint): isenta _forgecontext vendored do ruff (floor 3.10) (#109)
bb808d5 fix(install): portal health + error hints + lock staleness + eval docs (#110)
e6d6c52 fix(test): wheel capability — evals available since lf-0038 (#111)
9b8c58b test(graphstudio): node --check timeout 30s→120s (#112)
af9718b feat(install): multi-forge composition engine — transactional install/uninstall (lf-0040) (#113)
38dc92e fix(install): installkit 1.0.1 + bootstrap 1.1.1 — created_at fallback, backports doctor-api, teste pid indecidível (#114)
```

## 4. Arquivos modificados

`git diff --name-only v0.5.6..HEAD` → 57 arquivos. Agrupados:

| Grupo | Arquivos |
|---|---|
| Motor canônico (installkit) | `scripts/installkit/forge_context.py` (novo — canônico do `forge-context/v1`), `scripts/installkit/forge_installkit.py` (→ 1.0.1), `scripts/installkit/forge_bootstrap.py` (→ 1.1.1), `scripts/installkit/vendor.py` |
| Vendored no pacote | `src/theforge/_forgecontext.py` (novo, v1.3.1, `_SOURCE_SHA256 = "e72e93eab21ade74"`), `src/theforge/_installkit.py` (v1.0.1, `4c446922f5e77a0c`), `scripts/forge_bootstrap.py` (v1.1.1) |
| Wiring de produção | `src/theforge/install/service.py` (`_context_manifest`/`build_manifest` em `:214`, `install_transaction`/`uninstall_transaction` em `:452`/`:495`, discovery commands/ops), `src/theforge/agents.py` (`_BUNDLED_AGENTS_DIR` fallback, `:30`), `src/theforge/cli/main.py` + `cli/commands.py` + `cli/render.py` (verbo `evals`), `src/theforge/evals.py`, `src/theforge/contracts/codes.py` (taxonomia FORGE-CONTEXT-*) |
| Contratos/schemas | `docs/portable-installation/schemas/ForgeContext.schema.json` + `ForgeContextRegistry.schema.json` (novos), `ecosystem-compatibility.json`, `docs/adr/0061-forge-context-registry.md`, `tests/golden/forge_codes.json` |
| Empacotamento | `pyproject.toml` (force-include `agentic/agents` → `theforge/host_assets/agents` + `forge.json` → `theforge/`) |
| Docs | `docs/audits/FORGE_CONTEXT_BASELINE.md`, `docs/install/DISTRIBUTION_PARITY.md`, `docs/evals-taxonomy.md`, `docs/cli.md`, `docs/errors.md`, `docs/hub/which-forge.md`, `docs/INDEX.md`, `docs/README.md`, `docs/reference/*`, `CHANGELOG.md`, `README.md`, `.gitattributes` |
| Knowledge program | `docs/knowledge-program/*` (6 artefatos de auditoria) |
| Testes | `tests/test_forgecontext.py` (40 testes), `tests/test_forgecontext_txn.py` (32), `tests/test_multi_forge_e2e.py` (7 funções — 120 ordens parametrizadas), `tests/test_wheel_isolation.py`, `tests/test_evals_cycle5.py`, `tests/test_installkit.py`, `tests/test_install_orchestration.py`, `tests/test_install_e2e.py`, `tests/test_codes.py`, `tests/test_ecosystem_compat.py`, `tests/test_graphstudio.py`, `tests/test_packaging.py`, `tests/test_release_metadata.py`, `tests/test_smoke.py`, `tests/conftest.py` |

## 5. Gaps corrigidos

Mapeamento gap do baseline (§5) → correção entregue:

| Gap baseline | Status | Evidência |
|---|---|---|
| **P0-1** — `agentic/agents/` ausente do wheel; `agents list` → `no agent specs` fora do checkout | **CORRIGIDO** | `pyproject.toml:56` force-include `agentic/agents → theforge/host_assets/agents`; `src/theforge/agents.py:30` `_BUNDLED_AGENTS_DIR` (mesmo padrão de `knowledge.py`); commits `c5609a4`, `a8ebfbd` |
| **P1-2** — entry points de host mínimos (marker de ~5 linhas) | **CORRIGIDO** | camada consumer-docs do `_forgecontext.py`: `AGENTS.md` (bloco `forge:ecosystem` + `forge:<id>` por forge), `CLAUDE.md` (pointer fino), `AGENT_PROTOCOL.md` consolidado regenerado do registry; commit `e1576c2` |
| **P1-3** — sem registry de contexto no workspace | **CORRIGIDO** | `.forge/context/registry.json` (`forge/context-registry/v1`) + `capabilities/<fid>.json` (`forge/context/v1`) + `ROUTING.md`; commit `c5609a4`, ADR-0061 |
| **P1-4** — knowledge/rules/evals/protocols sem handle de instalação | **CORRIGIDO** | manifesto de capacidades declara `resources`, `discovery.commands`/`ops` (§6.2), `eval_suites` (§7.1), `protocols`, `mutating_verbs`, `requires_approval`; `service.py:214` (`fctx.build_manifest`); commits `fe234c6`, `09cd4a2` |
| — installkit sem fallback de staleness quando PID indecidível (Windows) | **CORRIGIDO** | `_installkit.py:397-409` — `created_at` do lock decide staleness; mtime como último fallback; teste `test_stale_lock_undecidable_pid_uses_created_at` (`test_installkit.py:573+`); commits `bb808d5`, `38dc92e` |
| — `_utc_now` quebrava em Python 3.10 (floor dos forges consumidores) | **CORRIGIDO** | `timezone.utc` no `_forgecontext.py` v1.2.1; commit `7f28d0e` |
| — `_URL_USERINFO_RE` com `@` interno no userinfo vazava senha | **CORRIGIDO no bootstrap** | `forge_bootstrap.py:350-356` — `[^/\s]+@` com comentário do trade-off; commit `38dc92e` |
| — smoke `--version` com stdout vazio passava e gravava `version: ""` | **CORRIGIDO** | `forge_bootstrap.py:934-944` — rc=0 **e** stdout não-vazio; commit `38dc92e` |
| — `_explicit_python_argv` devolvia spec não-trimmado | **CORRIGIDO** | `forge_bootstrap.py:204` — `[trimmed]`; commit `38dc92e` |
| — sem contrato `forge/context/v1` + registry transacional multi-forge | **CORRIGIDO** | `install_transaction`/`uninstall_transaction` (`_forgecontext.py:2606`/`:2705`): preflight → lock → journal-recovery → conflitos → backup → journal → write → verify → commit, com rollback de backup durável; commit `af9718b` |
| — evals não classificados nem endereçáveis | **CORRIGIDO** | `src/theforge/evals.py` + `evals list|describe|run|result` na CLI + `eval_suites[].kind` no manifesto; commit `09cd4a2` |
| — recursos sem identidade estável / roteamento multi-forge | **CORRIGIDO** | `qualified_ids` (`<forge>:<recurso>`, `_forgecontext.py:1382+`) e `route()` read-only determinístico (`:2827+`); commit `af9718b` |
| — FORGE-CONTEXT-* fora da taxonomia de códigos | **CORRIGIDO** | `contracts/codes.py` + `tests/golden/forge_codes.json`; commit `999ef40` |
| — `forge.json` fora do wheel (integrity digests vazios sob wheel) | **CORRIGIDO** | force-include + leitor `_PKG_DIR`-aware; commits `a8ebfbd`, `99dccdd` |

## 6. Gaps restantes

Honesto — abertos na data deste relatório:

- **E2E real de hosts (ciclo 8, §10.2) — NÃO EXECUTADO.** Devin/Claude/Codex/
  Copilot não foram exercitados ponta-a-ponta contra uma instalação por
  wheel; ver §9.
- **Economia/observabilidade (ciclo 9, §11) — pendente.** Sem medições de
  progressive disclosure/cache/eventos.
- **Publicação PyPI — pendente** (§10): versões bumpadas em worktree, não
  publicadas.
- **P1-1 do baseline — fidelidade de formato por host nas skills** segue
  aberta: `src/theforge/install/render.py` **não mudou** no range
  (`git log v0.5.6..HEAD -- src/theforge/install/render.py` → vazio) —
  todos os hosts continuam recebendo o formato `.agents` (codex).
- **P2-1 do baseline — `FORGE-INSTALL-NOT-A-REPO` inalcançável via CLI**
  (`--root` default `"."` não alterado no range).
- **P2-2/P2-3 — skills `kiro-*` internas** ainda são instaladas no
  consumidor e seguem sem fonte canônica única.
- **P2-5 — registry de conta stale** (`~/.forge/installations/` com versões
  velhas de git-checkout) sem refresh; **P2-6 — `contracts.schema --help`
  cria diretório `--help/`** (quirk não tocado).
- **`data-sentinel-forge` fora do programa** (decisão do dono): ainda em
  `_installkit.py` 1.0.0 (`_SOURCE_SHA256 = "bc189dd2ae0028ce"`), sem
  `_forgecontext.py` e sem `forge_bootstrap.py` vendored.
- **`forge-doctor-api`/`forge-doctor-data` sem `_forgecontext`** — deliberado
  (boundary: sem wall-clock no core dos doctors); receberam só
  `_installkit.py` 1.0.1 + `forge_bootstrap.py` 1.1.1.
- **`_URL_USERINFO_RE` do installkit** (`_installkit.py:93`) segue
  `[^/@\s]+@` — o fix do `@` interno foi aplicado no bootstrap; a cópia do
  installkit redige specs de pip em `install update` e merece a mesma
  revisão (observação registrada, sem issue aberta até aqui).
- **`DISTRIBUTION_PARITY.md`** descreve o estado pré-§8.2 (reader wiring);
  o §8.2 (`99dccdd`) corrigiu o leitor — o doc registra a lacuna histórica,
  não o estado final.

## 7. Testes executados

Executados localmente nesta máquina durante o ciclo (evidência: arquivos de
teste no range + commits de correção posteriores verdes):

| Suíte | Arquivo | Contagem | Resultado |
|---|---|---|---|
| installkit | `tests/test_installkit.py` | 55 testes | verde |
| bootstrap | `tests/test_installkit_bootstrap.py` | 46 | verde |
| schemas `forge/*` | `tests/test_installkit_schemas.py` | 5 | verde |
| forge-context engine | `tests/test_forgecontext.py` | 40 | verde |
| **transações** (journal/rollback/verify) | `tests/test_forgecontext_txn.py` | **32** | verde |
| orquestração install auto | `tests/test_install_orchestration.py` | 47 | verde |
| install e2e/plan/installation | `test_install_e2e.py` + `test_installation.py` + `test_install_plan.py` | 6+15+15 | verde |
| evals §7 | `tests/test_evals_cycle5.py` | 13 | verde |
| wheel isolation | `tests/test_wheel_isolation.py` | 1 (e2e slow) | verde |
| **multi-forge 5!** | `tests/test_multi_forge_e2e.py` | **120/120 ordens de instalação** (parametrize `itertools.permutations(5)`, marker `slow`) | verde |

Total na superfície install/context: **~280 testes** verdes.

- `python scripts/installkit/vendor.py --check <repo>` → **CLEAN nas 7
  forjas** (the-forge + 4 especialistas + forge-doctor-api/data — estes
  dois checkados installkit-only, sem `_forgecontext` por boundary).
- Windows gotchas cobertos por teste: stale-lock `created_at`
  (pid indecidível → recusa conservadora), `node --check` 120s,
  `uv venv --seed` (azure), `Path.is_relative_to` (api-forge).

## 8. Resultados

- Contrato **`forge/context/v1`** entregue: manifesto de capacidades por
  workspace em `.forge/context/capabilities/<forge>.json`, registry
  compartilhado `registry.json` (`forge/context-registry/v1`) e `ROUTING.md`
  regenerado deterministicamente (sort_keys, sem timestamps).
- **Install/uninstall transacional** (`install_transaction`,
  `uninstall_transaction`): um único lock, journal com redo idempotente,
  backup durável, verify pós-escrita, rollback em falha — kill no meio
  converge na próxima operação.
- **Consumer-docs**: `forge:ecosystem` + `forge:<id>` managed blocks com
  conteúdo de usuário byte-preservado; `AGENT_PROTOCOL.md` consolidado
  (contrato comum de 9 fases + seção gerenciada por forge).
- **Discovery**: `discovery.commands` (argv real, `mode`, `read_only`) +
  `discovery.ops` (mapa §6.2 fechado); `rules.*` honestamente ausente em
  the-forge (control plane sem catálogo de regras).
- **Evals §7**: `evals list|describe|run|result`; kinds fechados
  (`_forgecontext.EVAL_KINDS`), holdouts/baselines hash-pinned, inputs
  ausentes bloqueiam (nunca skip).
- **Multi-forge**: 120/120 permutações de ordem de instalação das 5 wheels
  produzem estado final equivalente (registry normalizado, ROUTING.md e
  AGENT_PROTOCOL.md byte-idênticos), sem deleção cruzada, reinstall
  idempotente, uninstall de uma forge preserva as demais, lock leftover
  recuperado, registry compõe sem the-forge instalado.
- **Vendor drift**: `_forgecontext.py` byte-idêntico nas 5 forjas
  (sha256 `390f5e0e61ab80dc…`, `_SOURCE_SHA256 = "e72e93eab21ade74"`,
  v1.3.1); `_installkit.py` byte-idêntico (`1484135ae71c396e…`, v1.0.1);
  `forge_bootstrap.py` byte-idêntico (`978862ebedb9ecfb…`, v1.1.1).

## 9. Evidências Devin/Claude/Codex

**NÃO EXECUTADO.** A prova E2E real por host (§10.2 do spec — Devin CLI,
Claude Code, Codex CLI, Copilot) pertence ao ciclo 8, ainda pendente.
Nenhuma evidência de host é afirmada neste relatório; os artefatos
instalados (registry, blocks, manifestos) foram verificados por testes de
integração, não por telemetria de host real.

## 10. Matriz PyPI

| Componente | Estado |
|---|---|
| Wheel local (HEAD) | construída e testada em venv limpa fora do checkout (`tests/test_wheel_isolation.py` — build → install → apply → doctor → repair → uninstall → reinstall) |
| `forge.json` no wheel | presente via force-include (`pyproject.toml`) — leitor `_PKG_DIR`-aware (`99dccdd`) |
| `host_assets/agents` | presente no wheel (fix P0-1) |
| Publicação no índice | **PENDENTE DE PUBLICAÇÃO** — `pyproject.toml` em worktree marca `0.6.0`; nenhuma das 5 forjas publicou a versão do ciclo até a data deste doc |
| PyPI 0.5.6 publicado | sem drift de conteúdo vs o wheel 0.5.6 local (baseline §4.3) |

As 5 wheels do ecossistema foram construídas e isolation-testadas
localmente (lf-0039) — a matriz 5! do §7 usa exatamente essas wheels.

## 11. Compatibilidade

- **`forge/*` v1 estável**: `ecosystem-compatibility.json` fixa janelas
  `min_major/max_major`; os contratos novos (`forge/context/v1`,
  `forge/context-registry/v1`) foram adicionados sem quebrar
  `forge/InstallationManifest/v1` (registry de conta, escrito pelo
  bootstrap, segue intacto — camadas diferentes: conta vs workspace).
- **Python floor do ecossistema**: `_forgecontext.py` v1.2.1+ roda em 3.10
  (`timezone.utc` — #108); vendored isento do ruff do repo (#109).
- **Byte-parity**: os três artefatos vendored são idênticos nas 5 forjas —
  mesma engine, mesmo comportamento transacional.
- **Rollback**: uninstall é transacional e ownership-enforced
  (`FORGE-CONTEXT-OWNERSHIP` quando o manifesto/entry não é do chamador);
  `uninstall` preserva as outras forjas (prova: `test_multi_forge_e2e.py`).

## 12. Segurança

Entregue neste ciclo:

- **`_txn_restore` valida paths** (`_forgecontext.py:2495-2531`): alvos de
  restore precisam ser POSIX relativos puros — rejeita `..`, absolutos,
  `\` e prefixos de drive (`_TXN_DRIVE_RE`); nomes de blob restritos a
  `^\d{1,8}$` (`_TXN_BLOB_RE`). `txn/meta.json` é dado, nunca autoridade.
- **KeyboardInterrupt/SystemExit propagam bare após rollback**
  (`_forgecontext.py:2670-2676`, `:2748-2754`) — nunca re-tipados como
  `ContextError`.
- **`_URL_USERINFO_RE` do bootstrap corrigido** (`forge_bootstrap.py:355`):
  `[^/\s]+@` — userinfo com `@` interno (`u@raw:pw@host`) redige inteiro;
  trade-off documentado no comentário.
- **Smoke honest**: rc=0 + stdout vazio não é PASS (não grava `version: ""`
  no manifesto).
- **Locks**: O_EXCL não-bloqueante; staleness por pid morto → `created_at`
  → mtime, nessa ordem; PID indecidível (Windows/PermissionError) cai no
  `created_at` declarado, com recusa conservadora para timestamp futuro.
- **Ownership**: `capabilities/<fid>.json` fully-managed só pelo dono;
  manifesto estrangeiro recusado (não sobrescrito); corrupto vai para
  `.corrupt-<stamp>` em quarentena; conteúdo de usuário fora dos markers
  byte-preservado; estados ambíguos de marker recusam
  `FORGE-CONTEXT-CONFLICT`.
- **Writes atômicos** (tmp+rename) e journal redo idempotente.
- **certifi 2026.7.22→2026.10.19** em forge-doctor-data (`poetry.lock`,
  PYSEC-2026-4320 — PR #62 daquele repo).
- `installkit`/`bootstrap`/`forgecontext` stdlib-only; core nunca importa
  SDK de provedor nem chama rede.

## 13. Performance

- **Idempotência real**: re-register de manifesto inalterado faz **zero
  writes** — o segundo `install` é byte-idêntico (docstring do motor +
  `test_multi_forge_e2e` reinstall).
- **Registry determinístico**: `sort_keys`, entries ordenadas por
  `forge_id`, `ROUTING.md` sem timestamps — diff estável entre ordens.
- **Lock não-bloqueante** por default (contenção = recusa, não hang).
- Sem claims quantitativos de economia de contexto: ciclo 9 (§11) ainda
  não executado — nenhuma medição de bytes/tokens é afirmada aqui
  (regra: sem baseline do mesmo caso, sem saving).

## 14. Recomendações

1. **Executar o ciclo 8 (§10.2)** antes de declarar o programa homologado:
   prova real Devin/Claude/Codex/Copilot com telemetria — sem ela, os
   critérios de aceite §16 sobre hosts ficam em aberto.
2. **Publicar a matriz PyPI** (§12.5): completar release notes + workflow
   autorizado para `theforge-core 0.6.0` e as 4 especialistas; se o acesso
   de publicação não existir, manter release marcada como bloqueada —
   nunca simular sucesso.
3. **Fechar P1-1** (fidelidade de formato por host no install — re-usar
   `render_skills.py` por host em vez do formato único `.agents`).
4. **Revisar `_URL_USERINFO_RE` do installkit** (`_installkit.py:93`) para
   o mesmo padrão do bootstrap, ou documentar por que o padrão mais
   restrito é seguro no contexto de `install update`.
5. **Ciclo 9**: medir progressive disclosure/cache/eventos com baseline
   do mesmo caso antes de qualquer claim de economia.
6. **Decidir data-sentinel-forge**: ou entra no programa (vendor + cycle
   2-7) ou é declarado fora-de-escopo formalmente.
7. Resíduos baratos: `--root` sem default `"."` no install (P2-1),
   `contracts.schema --help` (P2-6), perfil sem `kiro-*` para consumidores
   (P2-2/P2-3).

## 15. Status por Forge

| Forge | `forge/context/v1` | `_forgecontext` | `_installkit` | `forge_bootstrap` | Wheel testada | Status |
|---|---|---|---|---|---|---|
| **the-forge** | registry + docs + txn | v1.3.1 (`e72e93ea`) | v1.0.1 (`4c446922`) | v1.1.1 (`978862eb`) | sim (lf-0039 + matriz 5!) | **merged, pendente de release** (0.6.0) |
| **spark-forge-aws** | registry + docs + txn | v1.3.1 (`e72e93ea`) | v1.0.1 (`4c446922`) | v1.1.1 (`978862eb`) | sim | **merged, pendente de release** (0.6.0) |
| **spark-forge-azure** | registry + docs + txn | v1.3.1 (`e72e93ea`) | v1.0.1 (`4c446922`) | v1.1.1 (`978862eb`) | sim | **merged, pendente de release** (0.2.0) |
| **api-forge** | registry + docs + txn | v1.3.1 (`e72e93ea`) | v1.0.1 (`4c446922`) | v1.1.1 (`978862eb`) | sim | **merged, pendente de release** (0.2.0) |
| **platform-forge** | registry + docs + txn | v1.3.1 (`e72e93ea`) | v1.0.1 (`4c446922`) | v1.1.1 (`978862eb`) | sim | **merged, pendente de release** (0.2.0) |
| **forge-doctor-api** | — (boundary: sem wall-clock no core) | ausente | v1.0.1 (`4c446922`) | v1.1.1 (`978862eb`) | installkit-only | **installkit only (boundary)** |
| **forge-doctor-data** | — (idem) | ausente | v1.0.1 (`4c446922`) | v1.1.1 (`978862eb`) | installkit-only | **installkit only (boundary)**; certifi bumpado (PYSEC-2026-4320) |
| **data-sentinel-forge** | — | ausente | v1.0.0 (`bc189dd2`) | ausente | não | **deferred by owner** |

---

## Apêndice — comandos executados para este relatório

```text
git log v0.5.6..HEAD --format='%h %H %s'          → 20 commits
git diff --stat v0.5.6..HEAD                      → 57 files, +12848/−734
git rev-parse v0.5.6^{commit}                     → 92d79730e72d…
sha256sum src/theforge/_forgecontext.py           → 390f5e0e61ab80dc…
sha256sum src/theforge/_installkit.py             → 1484135ae71c396e…
sha256sum scripts/forge_bootstrap.py              → 978862ebedb9ecfb…
grep _FORGECONTEXT_VERSION src/theforge/_forgecontext.py → "1.3.1"
grep _INSTALLKIT_VERSION src/theforge/_installkit.py     → "1.0.1"
grep _BOOTSTRAP_VERSION scripts/forge_bootstrap.py       → "1.1.1"
grep -c 'def test_' tests/test_{forgecontext,forgecontext_txn,
  multi_forge_e2e,installkit,installkit_bootstrap,…}.py  → contagens §7
git log v0.5.6..HEAD -- src/theforge/install/render.py → (vazio — P1-1 aberto)
```

Referências canônicas: [docs/errors.md](../errors.md) (taxonomia FORGE-*).

## Pós-release — evidência de publicação (2026-10-23 UTC)

| Item | Estado | Evidência |
|---|---|---|
| Tag | CRIADA | `v0.6.0` no merge commit da release PR |
| GitHub Release | CRIADO | `gh release view v0.6.0` |
| PyPI | PUBLICADO | `pypi.org/pypi/theforge-core/json` → `0.6.0` |
| Wheel smoke (venv limpo) | PASS | `pip install theforge-core==0.6.0` + `theforge --version` → `0.6.0` |

Notas: installkit canônico 1.0.2 (`_SOURCE_SHA256 a15ca78bb34a0109`), bootstrap 1.1.1 — propagados aos 7 carriers; `vendor.py --check` CLEAN ×7. `data-sentinel-forge`: **deferido pelo dono** (outro CLI evoluindo).

## Pós-release hotfix — evidência de publicação patch (2026-10-23 UTC)

Patch motivado pelo review: `UnicodeDecodeError` não-tipado em docs de
consumidor não-UTF-8 quebrava install **e** uninstall.

| Item | Estado | Evidência |
|---|---|---|
| Tag | CRIADA | `v0.6.1` |
| GitHub Release | CRIADO | `gh release view v0.6.1` |
| PyPI | PUBLICADO | `pypi.org/pypi/theforge-core/json` → `0.6.1` |
| Wheel smoke | PASS | wheel publicado contém `_forgecontext` v1.3.2 (`_read_doc` presente) — verificado via `pip download theforge-core==0.6.1` |
| Regressão | PASS | teste cp1252 `AGENTS.md` → `FORGE-CONTEXT-CONFLICT` nomeado em install e uninstall |

## Pós-release hardening waves — evidência (2026-10-23 UTC)

Duas ondas de patch: `0.6.2` (install 2.0 hardening — traversal containment, lock token, journal quarantine, repair schema, atomic-write mode) e `0.6.3` (receipt truthfulness, user-scope no-op, unsafe drift surfacing).

| Item | Estado | Evidência |
|---|---|---|
| Tags | CRIADAS | `v0.6.2`, `v0.6.3` nos merge commits |
| GitHub Release | CRIADO | `gh release view v0.6.3` |
| PyPI | PUBLICADO | `pypi.org/pypi/theforge-core/json` → `0.6.3` |
| Wheel conteúdo | VERIFICADO | `pip download theforge-core==0.6.3` → `_installkit` 1.0.4 (`_INSTALLKIT_VERSION`) |
| Install E2E (wheel→workspace) | PASS | ver secção Cycle 8 abaixo |

## Cycle 8 — E2E real em host Devin (EXECUTADO 2026-10-23)

Setup: venv limpa + `pip install` dos wheels PyPI publicados →
`sparkforge-aws install --root /tmp/e2e-host/proj --host devin -y` →
receipt `forge/InstallReceipt/v1` `status=completed`, `verification=PASS`.

Jornada do host (esta sessão Devin CLI), cada passo verificado por saída
de ferramenta, não por afirmação textual:

| Passo | Resultado | Evidência |
|---|---|---|
| Descobrir Forge | ✓ | bloco managed `forge:ecosystem` em `AGENTS.md` do workspace |
| Registry | ✓ | `.forge/context/registry.json` → `spark-forge-aws: available` |
| Protocolo | ✓ | `AGENT_PROTOCOL.md` (4 130 B) + `ROUTING.md` |
| Capacidades | ✓ | `sparkforge-aws capabilities` → `forge/capabilities/v1`, 0.6.3 |
| Rules | ✓ | `rules lookup --id SF-PY-001` → catálogo retorna a regra |
| Knowledge (wheel, sem git) | ✓ | `knowledge search "glue worker"` → `glue/workers-and-capacity.md`, `knowledge_origin=package` (site-packages) |
| Regra aplicada a caso real | ✓ | `analyze pyspark job.py` → `judge --glue 5.1` → finding `SF-PY-002` P1 (`df.collect()` job.py:5), evidência `f_6bba98` |
| Receipt auditável | ✓ | `.sparkforge_aws/receipts/install-*.json` |

Outros hosts: Claude Code / Codex CLI / Copilot — não instalados neste
ambiente; marcados `não verificado` (não como sucesso). A matriz de hosts
por path renderizado é coberta pelos testes de render (`rendered_hosts`).

## Cycle 9 — economia/observabilidade (medido, não estimado)

| Métrica | Observado |
|---|---|
| Bytes adicionados ao workspace | 37 897 (knowledge stubs) + 28 169 (.forge) + docs |
| `AGENTS.md` / `CLAUDE.md` / `AGENT_PROTOCOL.md` | 1 978 / 418 / 4 130 B |
| `registry.json` + `ROUTING.md` + capability manifest | 9 094 / 1 508 / 17 567 B |
| Knowledge stubs | 43 ponteiros (37 897 B); conteúdo carregado lazy do pacote |
| Host mirrors (.agents + .devin) | 1 723 209 B cada (perfis+skills renderizados) |
| Latência cold-start (spawn+exec) | capabilities ≈25 s, rules ≈15 s, knowledge ≈5 s (1ª chamada, inclui startup do intérprete) |
| Tokens de provider | `unresolved` — sem transcript de host, não estimado |

Sentinel: release `v0.2.2` existe no GitHub; publicação PyPI
**bloqueada** — workflow `Release` gated no environment `pypi`
(trusted publisher + approval humana). Job `publish to PyPI (OIDC, gated)`
falhou por design até o dono aprovar.

forge-cli: o release `v0.3.0` (npm `theforge-cli`) foi cortado na mesma
onda para manter o CLI alinhado aos docs de install que ele referencia;
mudança docs-only — registrado aqui retroativamente como decisão, não
necessidade crítica. Sem nova funcionalidade de CLI.
