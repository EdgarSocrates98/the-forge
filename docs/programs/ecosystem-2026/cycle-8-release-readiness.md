# Cycle 8 — Release readiness (RC evidence)

Spec: `factory/specs/active/cyc8-04-ci-release-gates.md` (§8.9–8.10).
Escopo desta RC: **the-forge 0.5.0** como primeiro artefato candidato;
demais componentes entram pelo manifesto da cyc8-01 em releases próprias.

## Escada de gates (§8.9) — estado por gate

| # | Gate | Implementado em | Estado 2026-10-15 |
|---|---|---|---|
| 1 | build | `release-gates.yml` job `build` + `python -m build` | ✓ executado local (7 wheels + npm + bundle) |
| 2 | unit | `ci.yml` (matriz PR) + job `unit` | ✓ suíte verde pós-fixes desta sessão |
| 3 | contract | job `contract` (regen `schemas/` limpo) + `test_*contract*` | ✓ `forge/EcosystemCompatibility/v1` adicionado + testado |
| 4 | integration | job `integration` (nightly/manual) | ⚠ marcadores `integration` existem; execução noturna pendente de agendamento real |
| 5 | package install | job `package-install` + evidência local | ✓ wheel instalada em venv limpa (cyc8-02) |
| 6 | smoke | job `smoke` (`--version`, `--help`) | ✓ |
| 7 | security | job `security` (pip-audit + SBOM, política em `security.md`) | ⚠ executado local; **F-01/G-20 resolvido 2026-10-15** (pin `>=50,<51` → 50.0.2, re-audit zero CVEs) |
| 8 | compatibility | job `compatibility` (`ecosystem-compatibility.json` validado) | ✓ manifesto real com 9 componentes |
| 9 | RC lifecycle | job `rc-lifecycle` + evidência local abaixo | ✓ lifecycle executado na wheel instalada |
| 10 | certification | job `certification` (agregador) | ⚠ aguardando execução noturna dos gates 4–9 |

## RC lifecycle — evidência real (wheel instalada, ambiente descartável)

Binário: `/tmp/pack-matrix/venvs/the-forge/bin/theforge` (wheel `theforge-0.5.0`,
não o checkout). Alvo: `/tmp/rc-lifecycle/proj` (dir descartável).

| Etapa | Comando | Evidência |
|---|---|---|
| fresh install | `install apply --scope project --yes` | receipt `forge/InstallReceipt/v1`; **328 managed writes**, 950 KiB de assets |
| status | `install status` | `forge/InstallationHealth/v1`; ledger **329 entradas**, drift `missing:[] modified:[]` |
| reinstall | `install apply` (2ª vez) | idempotente — completado sem erro |
| update | `install update` | receipt `operation: update`, `verification: PASS` — **requer manifesto bootstrap** (`~/.forge/installations/the-forge.json`); CI faz `forge_bootstrap.py --repo .` antes (fix pós-review 2026-10-15; verificado com `FORGE_HOME_OVERRIDE` isolado → `completed \| pip:PASS`) |
| repair | `install repair` | `0 restored` — sem drift (correto) |
| MCP | `install mcp-verify` | `NOT_APPLICABLE` (sem hosts no scratch — honesto) |
| uninstall | `install uninstall` | managed files removidos; estado `.forge/install` preservado (`--purge` remove tudo) |
| host assets | apply → `.agents`/`.claude`/`.devin` | `managed_bytes: 950036`, profile `recommended` |
| Portal | `status.forge_portal` | `state: "vendored"` (presence anexada ao health) |
| registry | `installations` manifest | `forge/InstallationManifest/v1` em `~/.forge/installations/` |

## Independência (§6) — prova

Cada wheel especialista instalada em venv isolado **sem theforge** e seu CLI
executa standalone: `apiforge`, `platformforge`, `sparkforge-aws`,
`sparkforge-azure`, `forge-doctor-data`, `forge-doctor-api` — `--version`
correto em 6/6 (evidência `packaging-matrix.md`). Nenhum especialista ganhou
dependência de the-forge/CLI/Portal.

## Bloqueios honestos antes de "release certificada"

- **G-01**: zero tags nos 9 repos — RC pode ser preparada, não publicada.
- **~~G-17~~**: `ruff format` drift pré-existente — **resolvido 2026-10-15**:
  22 arquivos reformatados, `ruff format --check` limpo (947 arquivos),
  suíte completa verde; vendored ui-kit re-sincronizado após reformat.
- **~~G-20~~**: api-forge `cryptography` — **resolvido 2026-10-15**: pin
  `>=43,<47`→`>=50,<51` (bump autorizado pelo usuário), resolve 50.0.2,
  re-audit zero CVEs (`audit/api-forge.json`), 110 testes keys/report verdes.
- **G-06 parcial**: lifecycle funciona no `theforge` via installkit; lifecycle
  **gerenciado pelo forge-cli** (install/update/rollback do ecossistema) é
  cyc8-05.
- CI noturno agendado: workflow criado, mas a primeira execução real só
  acontece em push/schedule — evidência de CI **pendente** (não simulada).
- Gates "obrigatórios" por repo: calibração com mantenedor (⚠ Pending da spec).

## O que esta RC **não** é

- Não é release publicada (sem tag, sem registry).
- Não certifica os outros 8 componentes individualmente — cada um precisa da
  sua própria escada (a matriz está em `packaging-matrix.md`).
