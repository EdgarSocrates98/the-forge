# Cycle 10.3 — Wave 3: Forge CLI DevEx

Data: 2026-10-16. Ambiente: Linux, Node v22.23.2, `theforge-cli@0.1.0`
instalado do npm público, workspace descartável `/tmp/c103-devex/ws`.

## 1. Lifecycle medido (§5.5)

| Operação | Comando | Resultado | Tempo |
|---|---|---|---|
| Install (2 forjas) | `install forge-doctor-data forge-doctor-api --yes` | ✅ 2/2 | **23.0s** |
| Status | `status` | ✅ clonado/atualizado corretos | <1s |
| Update check | `update --check` | ✅ ambas "atualizado" | <2s |
| Reinstall | `reinstall forge-doctor-api --yes` | ✅ re-setup ok | ~10s |
| Uninstall | `uninstall forge-doctor-data --yes` | ✅ removida **com backup** `.forge-cli/backups/` | <1s |

Estado preservado corretamente: `ws/` contém só o clone restante +
`.forge-cli/` (logs, backups). Sem arquivos órfãos observados.

## 2. Superfície CLI (observada)

`forge-cli --help` expõe lifecycle completo: install, clone, update,
versions, reinstall, pin/unpin, rollback, uninstall, components, status,
discover, recommend, env (inspect|plan|init|validate|migrate|doctor),
hosts (list|plan|register|validate|rollback), self, ask, predict,
context, ai, bundle (export/import/verify), learning (opt-in).

Flags: `--dir` (workspace), `--profile`, `--scope`, `--components`,
`--clean`, `--report`, `--yes`, `--plan`, `--only`, `--all`.

## 3. Gaps reais (DevEx)

### G5 (confirmado) — caminho de instalação é clone-only
`install`/`clone`/`reinstall`/`update` operam sobre `git clone` +
native installer do source. **Não existe `--source pypi`** — pip só
aparece como prereq-check. §5.6 do prompt pede instalação pública sem
obrigatoriedade de clone. O registry já existe: `repos.ts` pode
acrescentar `pypi: {dist}` e planner ganhar step `pip install <dist>`
(venv gerenciada `~/.forge-cli/venvs/<forge>` ou `.venv` do target).
Clone permanece para `forge-portal` (sem dist PyPI) e devs.

### Fricções menores observadas
- `--dir` default `./forge-workspace` no cwd — aceitável, mas devia ser
  documentado na primeira execução interativa (verificar Wizard §5.2).
- Saúde `forge-health/v1` (doctor) funciona e dá score com evidência.

## 4. UX gates ainda a executar (§5.7)

- Fluxo interativo TUI (`forge-cli` sem args) — não exercitado aqui
  (headless); coberto pelo caminho `--yes` não-interativo.
- Offline mode / registry unavailable / invalid package — pendentes
  (precisam de simulação controlada; candidato a testes dedicados).

## 5. Evidência de instalação

Log real: `ws/.forge-cli/logs/forge-cli-20261016-210433.log`.
Backup de uninstall verificado em `.forge-cli/backups/`.
