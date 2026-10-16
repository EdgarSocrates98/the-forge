# Linux Acceptance — Cycle 10.1

Data: 2026-10-16 · Ambiente: Linux x86_64, bash 5, Python 3.12.3, Node v22.23.2
Baseline: `audit/baseline/` recolhido em `origin/main` de cada repo (SHAs em baseline.md).

## Gates reexecutados neste ambiente

| Gate | Comando | Resultado | Evidência |
|---|---|---|---|
| H0 baseline | `audit/tooling/collect_baseline.py --ref origin/main` | PASS — 9 repos, SHAs reais | `audit/baseline/*.json` |
| H1 installers | `audit/tooling/run_installers.py` (dry-run, sem mutação) | **7/7 linux-bash PASS**; powershell-5.1 e git-bash BLOCKED (shells Windows-only) | `audit/reports/installer-matrix.json` + `audit/artifacts/installers-2026-10-16/` |
| H2 contratos | `audit/tooling/validate_contracts.py` | PASS | `audit/reports/contract-validation.json` |
| H2/H4 MCP local | `audit/tooling/run_mcp_handshakes.py --timeout 90` | **6/6 PASS** — aws 146, azure 18, apiforge 154, platform 39, doctor-api 17, doctor-data 14 tools | `audit/reports/mcp-handshake.json` |
| H5 cenários | `audit/tooling/run_scenarios.py` | **19/19 PASS** nos SHAs atuais | `audit/reports/evidence-index.json` |
| Forge Lab | `theforge lab collect --mode A` | **7/7 labs ok, 203 cenários, 0 falhas de coleta** | `docs/programs/ecosystem-2026/benchmarks/2026-10-16-A.md` + `results-2026-10-16-A.jsonl` |
| H7 regressão CI | `gh run list` por repo | **9/9 success** no HEAD de main | baseline.md |

## Correções feitas durante a reexecução

1. `audit/tooling/run_installers.py` — `linux-bash` era hardcoded `command=None` (runner
   era Windows-only). Agora em POSIX executa `bash install.sh --dry-run` nativo e marca
   powershell/git-bash BLOCKED (shells inexistentes). PR the-forge#62.
2. `audit/tooling/run_mcp_handshakes.py` — fallback POSIX para `repo/.venv/bin/<cli>`
   quando o binário declarado não está no PATH. Destravou api-forge (154 tools) e
   platform-forge (39 tools). PR the-forge#62.
3. `forge-doctor-api` — `discover_scenarios` varria `.pytest-tmp/` como corpus e
   quebrava `run_labs`. Skip de dot-directories + teste de regressão. PR
   forge-doctor-api#56.
4. `api-forge` `.venv` local sem extra `mcp` — `apiforge-mcp` falhava no import.
   Instalado `-e .[mcp]` localmente (fix de ambiente, não de código).
5. `forge-doctor-api mcp` `tools/call` leva ~30–60s (scan do repo) — timeout default
   8s do runner era insuficiente; reexecutado com `--timeout 90`, PASS.

## Limitações remanescentes (honestas)

- Shells Windows (powershell-5.1, git-bash) não existem neste host → BLOCKED aqui;
  evidência complementar permanece a auditoria Windows anterior.
- pwsh não instalado → powershell-7 não executado.
- Hosts externos: claude/codex/devin CLI instalados (detectados no install receipt);
  GitHub Copilot ausente → NOT_TESTED até cyc101-05.
