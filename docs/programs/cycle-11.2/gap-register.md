# Cycle 11.2 — gap register

Estados: OPEN · IN_PROGRESS · FIXED_UNVERIFIED · VERIFIED · BLOCKED_EXTERNAL · NOT_APPLICABLE
Captura: 2026-10-17 ~19:40Z. SHAs de main no rodapé.

| ID | Prioridade | Problema | Evidência | Correção | Teste | Estado |
|---|---|---|---|---|---|---|
| P0-001 | P0 | Publicação npm sem OIDC | runs 39040262185 (E403 OIDC, sigstore assinado) + 39041701852 (publicado, verify falhou por lag → poll #28) | `publish-npm.yml` endurecido: env inputs, SemVer estrito, lock/tag/SHA/branch gates, tarball imutável anti-TOCTOU, attestation hard-fail, dist.integrity check | `tests/release-workflow.test.ts` 24 verdes; `npm view theforge-cli@0.2.0 dist.attestations` → SLSA v1 real | **VERIFIED** (OIDC+provenance publicaram de verdade); ressalva: a revisão endurecida ainda não rodou um dispatch |
| P0-002 | P0 | `--plan` mutava (cache PyPI) | snapshot sha256 por comando | `resolveRelease.ephemeral`; matriz ampliada p/ 18 cenários | `tests/plan-purity.test.ts` 18/18 em main | **VERIFIED**; sub-gap novo: `pin/unpin` sem `--plan` (mutam state sem honrar nem avisar a flag) → OPEN |
| P0-003 | P0 | Transações/rollback/integridade | `tests/fault-injection.test.ts` | download/pip-fail restauram instalação; `.rejected` quarentena; `.corrupt` backup; yanked só por pin | 17/17 verdes em main | **VERIFIED** para os 12/20 cenários do spec cobertos; 8 restantes (permissão, disco, concorrência, native, MCP-register, host-setup, contrato, kill mid-write) → OPEN |
| P1-001 | P1 | Registry-first UX | README/npm-first + catálogo registry + menu filtrado | mantido | e2e registry install real (portal#32) | VERIFIED |
| P1-002 | P1 | `mcp --verify` sem protocolo | `src/mcp/handshake.ts` | handshake stdio real até TOOLS_DISCOVERED | server fake ESM + 4 cenários; `forge-cli mcp` real nesta máquina | VERIFIED em main; extensão SAFE_TOOL_CALLED/HOST_VERIFIED + allowlist `mcp_safe_tools` → **IN_PROGRESS** (worker B, uncommitted) |
| P1-003 | P1 | Portal sem registry ops | `portal_core/registry_ops.py` + `/forges` panel | plan→confirm→execute one-time token, CSRF/origin, allowlist, pin offline-plan | E2E real Chromium+PyPI (forge-portal#32) | VERIFIED |
| P1-004 | P1 | Python floor vs CI matrix | patch plans por repo | matrix fechada em api-forge/spark-aws/spark-azure; classifier 3.13 em platform | CI legs declaradas + smoke local | VERIFIED (pisos + intermediárias onde prometido); legs 3.14 ausentes em platform/doctors → documentado, OPEN menor |
| P1-005 | P1 | Forge Lab interpreter/extras | the-forge#83 diff (+616 lab.py) | cadeia explicit→receipt→manifest→specialist-env→fallback; estados PASS/FAIL/SKIPPED/BLOCKED/ERROR | `test_lab_interpreter.py` 15 testes | **IN_PROGRESS** — PR OPEN, checks rodando |
| P1-006 | P1 | Patches 0.x.1 + provenance PyPI | `docs/releasing/pypi-patch-plan.md` ×6 | planos com smoke local + checklist do mantenedor | `Blockers: None` nos 6 | **FIXED_UNVERIFIED** — nada publicado; depende de release autorizado |
| P2-001 | P2 | Offline: deps transitivas sem pin | comentário `install.ts:543` + `src/registry/lock.ts` novo | `forge-cli-offline-lock/1`: fecho transitivo sha256+tags; `registry lock` + `--lock`; 9 LockError kinds | validação antes de mutação (design) + testes in-flight | **IN_PROGRESS** — uncommitted em feat/c11-2-bc |
| P2-002 | P2 | Native installer fora da wheel | ADR-0006 (opção B) | `forge-doctor-api install` + `_installkit` vendored byte-idêntico + boundary tests | 1863 pytest declarados no PR | **IN_PROGRESS** — forge-doctor-api#65 OPEN (era BLOCKED_EXTERNAL até a decisão do dono) |
| P2-003 | P2 | Hosts/skills/agents E2E | run real 2026-10-17: `hosts list`, `doctor --json`, `hosts validate/plan` | detecção real: claude 2.1.295, codex 0.159.0 (auth ✓), devin 3000.11.92, cursor 3.24.18, copilot | doctor report forge/DoctorReport/v1 score 88 | **IN_PROGRESS** — detecção/validate/plan reais; `register --yes` real + MCP vivo + skills/agents não exercitados |
| P2-004 | P2 | Polish TUI/preflight/.env/erros/a11y/perf | menu.ts (10 ações), wizard, bench | in-flight: `--no-color`/NO_COLOR, `--version` do CLI, `registry lock` UX | menu/wizard/tui-repos 37 testes verdes | **IN_PROGRESS** — parte em-flight; screen-reader MANUAL-NEEDED |
| P2-005 | P2 | GitHub metadata/docs finais | pyproject metadata + project.urls auditados nos 6 PRs | classifiers/urls corrigidos onde havia drift | patch plans auditam targets existem | VERIFIED para metadata de pacote; docs públicas finais → cobertas por este ciclo de relatórios |

## Novos gaps registrados neste ciclo

| ID | Problema | Evidência | Estado |
|---|---|---|---|
| C11.2-A | `pin/unpin` mutam `state.json` com `--plan` silenciosamente ignorado (sem ramo plan e fora de `REGISTRY_IGNORED_FLAGS`) | `runRegistryPin` em main; descoberto via portal#32 | OPEN |
| C11.2-B | Vocabulário MCP renomeado in-flight (MCP_INITIALIZED→INITIALIZED) pode quebrar parsers externos | diff worker B | IN_PROGRESS (resolver antes do merge) |
| C11.2-C | `publish-pypi.yml` dos repos Python sem revisão OIDC equivalente ao npm | não auditado neste ciclo | OPEN |

## Nota de honestidade

Publicação npm real, portal E2E real e detecção de hosts real **foram
observados**, não inferidos. O que está em working tree (worker B/C) é
reportado como IN_PROGRESS — nada uncommitted conta como VERIFIED.

## SHAs de main na captura

the-forge ba660e7 · forge-cli 6ea2e79 · forge-portal c1f8844 ·
spark-forge-aws 4a70021 · spark-forge-azure 3ed7e75 · api-forge cb13bdb ·
platform-forge 2a9bf44 · forge-doctor-data 3f2fe0e · forge-doctor-api
beb0e08
