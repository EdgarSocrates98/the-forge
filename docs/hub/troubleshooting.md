# Troubleshooting

## Primeira linha — sempre

```bash
<cli> doctor            # ou <cli> install doctor
```

Doctor é a superfície de diagnóstico: checks `ok`/`warn`/`fail` com
`unlock` acionável. Leia o `unlock` antes de qualquer outra coisa.

## Por sintoma

| Sintoma | Onde olhar |
|---|---|
| `command not found` | PATH/launcher — re-rodar `setup.sh`/`setup.ps1`; abrir shell novo |
| `*-LOCKED` | instalação concorrente — o lock expira sozinho |
| `*-PLAN-NOT-APPROVED` | mutação sem `--yes` — `--dry-run` primeiro |
| MCP `FAIL` | extra `mcp` ausente — `mcp-verify` mostra `stderr_tail` |
| `AF-*`/`PF-*` refusal | campo/ação fora de política — o `unlock` é o desbloqueio seguro |
| `unresolved` alto | evidência insuficiente — complemente facts/bundle, não force |
| adapter `describe` recusado | versão de Python (api-forge pede 3.12 exato) |
| TUI não abre | não-TTY ou `TERM=dumb` — é fallback por design, não bug |

## Por forja

`docs/installation/troubleshooting.md` em cada repo — erros canônicos em
`docs/errors.md` (the-forge).

## Escalonar

`forge explain <run>`/`trace` no the-forge; `.forge/runs/` tem o resultado
persistido com evidência.
