# Receita — instalação governada (plano antes de mutação)

**O quê:** `forge install` aplica integração nos hosts com plano → aprovação.
**Por que:** mutação nunca é surpresa; `--dry-run` é o padrão do ecossistema.
**Quando:** instalar/atualizar a integração Forge em Claude/Devin/Codex.
**Quando não:** quer só inspecionar — use `forge doctor`/`status` (read-only).

## Problema

"Quero ativar o Forge no meu host de IA sem scripts opacos."

## Passo a passo

```bash
forge install apply --dry-run     # plano: nada é escrito
forge install apply --yes         # aplica após aprovar o plano
forge doctor                      # verifica pós-instalação
```

Bare `forge install` abre o wizard guiado (só em TTY; em automação dá
`UsageError` pedindo `install apply`).

## Saída esperada / interpretação

Dry-run lista escopo (`project|workspace|user`), perfil, hosts e arquivos
que seriam escritos. Apply retorna recibo; `doctor` confirma `ok`.

## Verificação

`forge doctor --json` → checks de host/workspace/provider `ok` ou `warn`
com `unlock`/`detail` acionável.

## Limitações

Instalação global real e credenciais ficam fora do escopo — mutações
restritas ao disco local e aos arquivos de configuração do host.

## Erros comuns

| Sintoma | Causa | Ação |
|---|---|---|
| `FORGE-INSTALL-PLAN-NOT-APPROVED` | mutação sem `--yes` | `--dry-run` → `--yes` |
| `FORGE-INSTALL-LOCKED` | instalação concorrente | aguarde o lock expirar; repita |
| wizard não abre | não-TTY | use `install apply --dry-run` |

## Uso por agentes

Agente pode gerar o plano (`--dry-run`); a flag `--yes` é aprovação humana —
não emitir `--yes` autonomamente.
