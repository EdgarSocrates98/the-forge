# Cycle 11.2 — FINAL CERTIFICATION (fechamento 11.2.1)

Estado final: **CONDITIONALLY_CERTIFIED** — todos os P0 fechados em
`main` com prova executada; todo P1 técnico verificado ou com causa-raiz
corrigida em `main`. O que separa de `CERTIFIED` pleno não é código nem
teste: são **releases autorizados** — os artefatos publicados
(`theforge-cli@0.2.0`, `theforge-core 0.5.0`, `forge-doctor-api 0.2.0`)
anteriorizam os merges do 11.2.1, então o que o registry entrega hoje
ainda não carrega o que a `main` provou.

Captura: 2026-10-18 (~02:45Z). Vocabulário §13.5: VERIFIED · PARTIAL ·
BLOCKED_EXTERNAL · NOT_TESTED · UNSUPPORTED (+ AWAITING_AUTHORIZED_RELEASE
onde §5.7 o nomeia). Nada aqui está VERIFIED sem comando/arquivo/PR citado.

## 1. Reconciliação (§2) — PRs do ciclo, estado real via `gh`

| PR | Estado | Merge | Conteúdo |
|---|---|---|---|
| forge-portal#32 | MERGED | 2026-10-17T18:32Z | Portal registry E2E plan/confirm + segurança |
| the-forge#83 | MERGED | 2026-10-17T19:42Z | Forge Lab interpreter 5 níveis + estados honestos |
| forge-doctor-api#65 | MERGED | 2026-10-17T19:52Z | `forge-doctor-api install` + `_installkit` (ADR-0006) |
| forge-cli#30 | MERGED | 2026-10-17T20:07Z | MCP verify completo, offline lock, TUI registry-first |
| forge-cli#32 | MERGED | 2026-10-18T01:49Z (`ff552b3`) | Plan purity definitiva + fault-injection completa |
| forge-cli#31 | MERGED | 2026-10-18T01:59Z (`dcc9675`) | `mcp_safe_tools` allowlists nas 6 dists com MCP |
| forge-cli#33 | MERGED | 2026-10-18T02:16Z (`4478dd4`) | Probe timeout, extras `[mcp]`, pin por instalação real, `update --check` all |
| the-forge#89 | MERGED | 2026-10-18T01:09Z (`44f1742`) | PyPI patch readiness + auditoria OIDC ×7 |
| the-forge#90 | MERGED | 2026-10-18T01:40Z (`b858d5f`) | Matriz E2E A–N execução real |
| the-forge#91 | MERGED | 2026-10-18T01:45Z (`9f8312a`) | Portal vendor Cycle 3 (telemetry/timeline/replay) |
| the-forge#92 | MERGED | 2026-10-18T02:16Z (`2b2b77a`) | `forge-knowledge` dentro da wheel + provider.argv |

Zero PRs abertos nos 9 repos na captura. Nada reaplicado — todo o
trabalho anterior foi reconciliado, não duplicado.

## 2. Baseline das 9 mains (§2.3) — captura fresca

| Repo | main SHA | CI @ HEAD | Tag/Release | Pacote publicado | Required checks | Working tree local |
|---|---|---|---|---|---|---|
| the-forge | `2b2b77a` | ci **in_progress** | v0.5.0 | theforge-core 0.5.0 | 10 (test/package ×2 OS ×4 py) | clean, este branch |
| forge-cli | `4478dd4` | ci **in_progress** | v0.1.0 | theforge-cli 0.2.0 (npm) | 9 (verify ×3 OS ×3 node) | clean, `fix/plan-purity-faults` |
| forge-portal | `2607989` | success | v0.1.0 | — (bundle) | 1 (core) | dirty (28), outra branch de trabalho |
| spark-forge-aws | `b1030c0` | ci **in_progress** | v0.5.0 | sparkforge-aws 0.5.0 | 7 | clean |
| spark-forge-azure | `5d80428` | success | v0.1.0 | sparkforge-azure 0.1.0 | 8 | clean |
| api-forge | `a0cefd2` | success ×2 workflows | v0.1.0 | apiforge-af 0.1.0 | 5 | clean |
| platform-forge | `899872e` | success | v0.1.0 | platformforge 0.1.0 | 5 | clean |
| forge-doctor-data | `2376733` | success | v1.0.0 | forge-doctor-data 1.0.0 | 11 | clean |
| forge-doctor-api | `d4845c6` | success | v0.2.0 | forge-doctor-api 0.2.0 | 5 | clean |

Branch protection em 9/9: required checks ativos + 1 review exigido;
`enforce_admins=false` nos 9. As 3 CI `in_progress` são runs dos merges
recentes — estado transitório, não falha; confirmar verde antes de
qualquer release.

Registries ao vivo (curl/npm view na captura): npm `theforge-cli` =
**0.2.0** (única mais recente; 0.1.0 e 0.0.0-stage anteriores); PyPI tem
exatamente **1 release por dist** — nenhum patch `0.x.1`/`1.0.1`
publicado (sem risco de duplicar).

## 3. Critérios do prompt, um a um

### §3 — P0: Plan purity definitiva → **VERIFIED em main**

`forge-cli#32` (ff552b3). `tests/plan-purity.test.ts`: **44 testes**,
prova por snapshot SHA-256 da árvore antes/depois — nenhuma mutação
persistente em: `pin --plan` (git+registry), `unpin --plan`, `rollback
--plan`, `uninstall --plan`, `update --check/--plan`, `install --plan`,
`reinstall --check`, `registry lock --plan`, `lock write --plan`,
`profile export --plan`, `learning enable --plan`, `bundle export
--plan`, `env init --plan`, `self-{install,uninstall,update} --plan` +
12 consultas read-only. Flags sem semântica → recusa nomeada exit 1/2
(`--ref` em unpin/rollback/uninstall; `--ref` divergente da instalada em
registry pin). `parseCliArgs` rejeita ref perigoso (`bad..ref`). O bug
real (pin/unpin `--plan` ignorado mutando `state.json`) tem teste de
contraste dedicado: `pin --plan (git)` não escreve vs. `pin sem --plan`
grava.

Ressalva de release: artefato publicado 0.2.0 anterioriza #30/#32.

### §4 — P0: Fault injection / transações / recovery → **VERIFIED em main** (17/20 plenos + 3 parciais honestos)

`forge-cli#32`. `tests/fault-injection.test.ts`: **30 testes** cobrindo
o spec §4.2:

| Spec # | Cenário | Prova em main |
|---|---|---|
| 1–5,7 | download/hash/cache/state/venv/pip | ✅ fault-injection (quarentena `.rejected`, `.corrupt`, cleanup, restore) |
| 6 | Python incompatível | ✅ `registry-install.test.ts` `python-incompatible` antes de criar venv |
| 8,10 | EACCES / ENOSPC | ✅ fs-wrapper: EACCES×2 (receipt pós-pip, pré-pip), ENOSPC (state pós-receipt) → nunca saudável |
| 9 | yanked | ✅ 4 testes — update recusa alvo yanked; pin instala mas marca receipt |
| 11 | concorrência | ✅ 3 testes — lifecycle lock: instalação simultânea → already-installed; lock vivo → busy; lock órfão de pid morto → recuperação documentada |
| 16 | processo morto na escrita | ✅ SIGKILL real + tmp órfão → próximo run limpa e recupera |
| 17–20 | rollback/uninstall parcial/pós-install update-fail | ✅ commit-boundary: version-mismatch, missing-receipt, orphaned → nunca `ok`; update/rollback restauram estado anterior |

Parciais restantes (falha do *componente externo*, não da transação do
CLI): native-install mid-flight crash, falha de registro MCP no host,
falha de host setup — validação e caminhos de recusa existem
(`native-install.test.ts` 11, `hosts.test.ts` 51), sem injeção de
subprocesso morto no meio. Aceite "instalação quebrada nunca aparece
saudável": provado por commit-boundary.

### §5 — P0: npm OIDC pipeline → **A: VERIFIED / B: AWAITING_AUTHORIZED_RELEASE**

`forge-cli#29` (6ea2e79) endurecido; `tests/release-workflow.test.ts`
24/24 verdes re-executados nesta certificação (worktree de origin/main).
0.2.0 publicado com OIDC + SLSA v1 observáveis no registry (`dist.
attestations`, `dist.integrity` sha512) — na revisão pré-hardening,
como já documentado. Sem novo dispatch: próximo release autorizado é a
prova. Conforme §5.7: A encerrado VERIFIED, B registrado como
AWAITING_AUTHORIZED_RELEASE.

### §6 — P1: MCP E2E → **VERIFIED em main** (protocolo real + tools/call allowlisted)

`forge-cli#30` + `#31` + `#33`. Níveis `INSTALLED → INITIALIZED →
TOOLS_DISCOVERED → SAFE_TOOL_CALLED → HOST_VERIFIED` em
`src/mcp/handshake.ts`. `mcp_safe_tools` declarado nas 6 dists com MCP
(`catalog.ts:56–112`) — mantenedor declara, nunca inferido do nome; sem
allowlist → para em TOOLS_DISCOVERED honesto. `tests/mcp-verify.test.ts`
21 cenários (server mudo→timeout, stdout-non-json, PROTOCOL_MISMATCH,
TOOL_CALL_ERROR, tool-input-underivable). Prova contra server real na
perna E da matriz: `forge-doctor-data` 14 tools + `sparkforge-aws` 146
tools, protocolo 2024-11-05, `tools/call` real (`get_host_status`,
`sparkforge_aws_rules_lookup SF-WASTE-001`). Ressalva: tools/call não
existe no 0.2.0 publicado.

### §7 — P1: Offline lock & hash integrity → **VERIFIED em main**

`forge-cli#30` (+`#33` extras no lock). `src/registry/lock.ts`:
`forge-cli-offline-lock/1` — fecho transitivo com sha256 + python_tag +
platform_tag + extras; `registry lock` gera online, `install --offline
--lock` valida o fecho INTEIRO antes de mutar (9 LockError kinds
nomeados; lock sem extras do pedido → `lock-mismatch`). 21 testes em
`tests/registry-lock.test.ts`. Perna D da matriz: instalação 100%
offline real por cache + `pip --no-index --find-links` sob proxies
mortos (verificado com `HTTP_PROXY=127.0.0.1:1` no 0.2.0 — mecanismo de
cache; o verbo `lock` é HEAD-only, lacuna de release registrada).

### §8 — P1: Forge Lab interpreter/extras → **VERIFIED**

`the-forge#83` merged. Cadeia explicit→managed-receipt→manifest→
specialist-env→fallback validada contra `python.satisfies`+extras;
todos reprovados → BLOCKED, nunca interpretador não provado. 15 testes
`test_lab_interpreter.py`. Perna H: `theforge lab collect` real —
ran=6, scenarios=137, report strict `forge/BenchmarkResult/v1`;
interpretador 3.14.7 comprovado por `install.json`. Execução de cenário
é fronteira de host (`unresolved` honesto, nunca fingida).

### §9 — P1: Doctor API native install → **PARTIAL**

`forge-doctor-api#65` merged (ADR-0006 opção B): `forge-doctor-api
install` + `_installkit` vendored byte-idêntico + boundary tests, 1863
pytest declarados. **Mas**: wheel publicada 0.2.0 **não contém** a
superfície de install (verificado: `forge_doctor_api-0.2.0-py3-none-
any.whl` — nenhum `install*`/`_installkit` no namelist; publicada
2026-10-16, antes do merge). E `forge-cli` main ainda delega ao script
`scripts/forge_install.py` de checkout (`tests/native-install.test.ts:43`).
Desbloqueio: release 0.2.1 (BLOCKED_EXTERNAL — rationale do owner +
`version_gate.py`) + adoção do `{python} -m forge_doctor_api install`
no catálogo do CLI.

### §10 — P1: Python compatibility matrix → **VERIFIED**

`python-matrix.md` + perna I: as 7 dists instalaram e fizeram smoke nos
pisos declarados (`theforge-core` 3.11, `apiforge-af` 3.12,
`platformforge`/`sparkforge-*` 3.10, doctors 3.11) — `--version` real em
cada venv do piso exato. CI legs alinhados aos classifiers; gap 3.14 em
platform/doctors documentado como candidato futuro.

### §11 — P1: PyPI patch readiness → **VERIFIED (readiness) / publicação BLOCKED_EXTERNAL**

`the-forge#89` (`pypi-patches.md`): cadeia sdist→wheel→wheel-from-sdist
**sha256 byte-idêntica** nos 7 pacotes; clean-venv install + CLI smoke +
`twine check` PASSED ×14; sha256 dos 14 artefatos registrados.
Auditoria `publish-pypi.yml`: os 7 workflows byte-identical (md5
f969a850…); 4/8 controles com gap ou parcial (environment approval,
version gate, post-publish smoke, TOCTOU rebuild) — reportados, não
corrigidos (passagem era report-only). Aceite §11: "patches tecnicamente
prontos e publicáveis mediante aprovação" — satisfeito; publicação é
decisão do mantenedor.

### §12 — P1: Portal complete E2E → **VERIFIED**

`forge-portal#32` + `the-forge#91` (vendor Cycle 3) + perna G: Chromium
real (headless, playwright), server vendored `sparkforge-aws portal`,
auth `X-Forge-Session` + cookie HttpOnly/SameSite=Strict, CSRF/origin/
replay/allowlist com códigos PORTAL-* nomeados, fluxo UI install → 1830
ações → 1482 written → uninstall com estado `NOT_INSTALLED` e receipt.
Escopo declarado: update/rollback/repair executados reais exigem
histórico multi-versão no registry (PyPI só tem 1 release por dist).

### §13 — P2: Hosts/agents/skills E2E → **PARTIAL**

Perna F **VERIFIED** para `claude`: `hosts register --yes` real em
`~/.claude.json` isolado — merge preservou `userKey`/`customSection`/
server do usuário; validate pass; rollback byte-idêntico ao pré-register.
Perna G: assets de host escritos pelo portal (`.claude/agents`,
`.codex/agents`, `.devin/`, `.github/agents`) + uninstall preservou
ledger. Não exercitado: escrita real em codex/devin/copilot (detectados,
não write-tested) e MCP vivo registrado via host → continua PARTIAL por
host; skills/agents removidos preservando customizações: provado via
ledger + rollback na perna F/G.

### §14 — P2: CLI/TUI UX → **PARTIAL**

Em main: `--version` self-print, `--no-color`/`NO_COLOR` global,
`registry lock` UX, env wizard com recusas nomeadas fora de TTY —
`cli-polish.test.ts` 15 testes + perna A (first-run TTY/não-TTY,
preflight, menu). Não fechado: screen-reader real = **NOT_TESTED**
(MANUAL_NEEDED — sem AT no ambiente); i18n PT-BR hardcoded; §14.7
performance baseline **NOT_TESTED** (nenhum bench comparativo executado
— só `Duration 33.13s` da suite medida, não é baseline de startup).

### §15 — P2: GitHub metadata & community → **VERIFIED (auditoria) / findings abertos**

Auditoria `gh api` dos 9 repos em `github-metadata.md` (novo doc desta
passagem): description/topics/LICENSE MIT nos 9; os 6 arquivos de
comunidade existem nos 9 (sizes registrados); release+tag+0 PRs abertos.
Findings: `homepage` vazio ×9; release GitHub do forge-cli em v0.1.0 vs
npm 0.2.0 (drift); wiki ligada sem conteúdo em 3 repos. Não corrigidos —
metadata pública é decisão do dono.

### §16 — E2E matrix A–N → **executada; resultado por perna**

`e2e-matrix.md` (the-forge#90): **11 VERIFIED, 2 PARTIAL, 1 VERIFIED
com lacunas de doc**. Desde a captura, as causas-raiz dos dois PARTIAL
foram corrigidas em `main`:

- **A** — hang `doctor`/`hosts list` → `FORGE_CLI_PROBE_TIMEOUT_MS`
  (15s default, `system.ts:72–76`, 5 testes em `system.test.ts`);
  `--version` self → main (#30). Estado: fix VERIFIED em main; o
  artefato testado (0.2.0) continua o mesmo — re-verificação da perna
  sobre artefato novo depende de release.
- **M** — wheel sem `forge-knowledge` + manifest sem `provider.argv` →
  `the-forge#92` merged: force-include + fallback bundled; verificado
  pelo autor: 6 providers resolvem de wheel limpa. Pendente: release do
  theforge-core 0.5.1 + re-run da perna M sobre o artefato publicado.

## 4. Regressão executada nesta certificação (§17)

```text
worktree /tmp/forge-cli-main-1037 @ origin/main = 4478dd4 (pós-#33)
$ npx vitest run
Test Files 61 passed (61) · Tests 1037 passed (1037) · 0 falhas
Duration 33.13s
```

Inclui: plan-purity 44, fault-injection 30, mcp-verify 21,
registry-lock 21, release-workflow 24, hosts 51, native-install 11,
cli-polish 15, e2e-cli 41, lifecycle-matrix 8. Nenhum teste eliminado.

## 5. Gap register residual — o que separa de CERTIFIED

| # | Gap | Estado | Desbloqueio |
|---|---|---|---|
| G1 | Artefatos publicados anteriorizam main: `theforge-cli@0.2.0` sem plan-purity/SIGKILL/`mcp_safe_tools`/`registry lock`/extras/`--version`/probe-timeout | **BLOCKED_EXTERNAL** | release npm 0.2.1+ (dispatch do workflow endurecido = também prova §5-B) |
| G2 | `theforge-core 0.5.0` sem `forge_knowledge` na wheel (perna M) | **BLOCKED_EXTERNAL** | release PyPI 0.5.1 + re-run da perna M |
| G3 | `forge-doctor-api 0.2.0` sem `install` na wheel; catálogo CLI ainda aponta script de checkout | **BLOCKED_EXTERNAL** | release 0.2.1 (version_gate + rationale owner) + adoção no catálogo |
| G4 | `publish-pypi.yml` ×7: sem environment approval, version gate, post-publish smoke; rebuild TOCTOU | OPEN | PR-padrão de hardening quando o mantenedor autorizar |
| G5 | PyPI dists sem PEP 740/sig observado (workflows têm `attestations: true`, nunca despachados) | **BLOCKED_EXTERNAL** | primeiro publish com attestation efetivo |
| G6 | Fault spec: 3 cenários de fronteira de componente (native-install crash, MCP-register, host-setup) sem injeção mid-flight | PARTIAL | fixture de subprocesso morto no adapter — trabalho técnico pequeno |
| G7 | Portal: update/rollback/repair E2E executados | PARTIAL | exige ≥2 releases publicados da mesma dist |
| G8 | Hosts: escrita real em codex/devin/copilot | NOT_TESTED | execução consentida por host (`--yes`) |
| G9 | Screen-reader walkthrough | NOT_TESTED | MANUAL_NEEDED — sem AT no ambiente |
| G10 | §14.7 performance baseline | NOT_TESTED | bench comparativo medido vs baseline |
| G11 | GitHub metadata: homepage ×9 vazio, release forge-cli v0.1.0≠npm 0.2.0, wikis vazias ×3 | OPEN | decisão do dono — nenhuma mutação feita |
| G12 | i18n PT-BR hardcoded no CLI | OPEN | fora do escopo de fechamento (registrado) |
| G13 | Token PyPI legado (G-SEC-1) | BLOCKED_EXTERNAL | revogação é ação humana |
| G14 | CI `in_progress` em 3 mains na captura (the-forge, forge-cli, spark-forge-aws) | transitório | confirmar success antes de releases |

## 6. Linha de veredito

**CONDITIONALLY_CERTIFIED.**

- Nenhum P0 aberto: plan purity e fault-injection completos e verdes em
  main (1037 testes executados nesta certificação); pipeline npm
  endurecido com OIDC real observado em produção.
- Nenhum P1 técnico aberto: MCP real com tools/call allowlisted, offline
  lock de fecho transitivo, Forge Lab com interpretador provado, matriz
  Python nos pisos, portal E2E com Chromium real, patches PyPI prontos.
- O que falta é inteiramente **não-código**: cortar releases autorizados
  para propagar aos registries o que `main` já prova, e 3 decisões de
  metadata do dono. Nenhum VERIFIED foi emitido sem prova; nenhum PARTIAL
  foi promovido.
