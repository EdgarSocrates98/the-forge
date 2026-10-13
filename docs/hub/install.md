# Install & Configure

## O modelo único

Toda forja segue o mesmo contrato (`forge/* install lifecycle`):

```bash
./setup.sh            # ou setup.ps1 no Windows — venv + wheel + launcher
<cli> doctor          # verificação honesta com unlock por check
<cli> install apply --dry-run   # plano de integração nos hosts
<cli> install apply --yes       # aplica após aprovação
<cli> install status / doctor / repair / uninstall
```

Escopos: `project` (`.claude/` etc no repo), `workspace` (`.forge`),
`user` (`~/`). Perfis por forja — `install apply --help` lista.

## Por forja

| Forja | CLI | Notas de instalação |
|---|---|---|
| the-forge | `forge`/`theforge` | adapters instalados no venv: `pip install -e ./adapters/*` |
| api-forge | `apiforge` | **Python 3.12 exato** — o adapter recusa outras versões com razão nomeada |
| spark-forge-aws | `sparkforge-aws` | extras `[aws,parquet]` para collectors; doctor mostra `unlock` |
| spark-forge-azure | `sparkforge-azure` | `--format json` é o default de saída |
| platform-forge | `platformforge` | offline core — nenhum SDK de provider no core |
| forge-doctor-data | `forge-doctor-data` | knowledge packs + suppressions via config |
| forge-doctor-api | `forge-doctor-api` | extra `mcp` para o servidor MCP |

## Fontes canônicas

`<repo>/docs/installation/quickstart.md` (+ `.en.md`) por forja;
`<repo>/docs/installation/troubleshooting.md` para os modos de falha.
