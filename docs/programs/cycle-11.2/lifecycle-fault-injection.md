# Cycle 11.2 — lifecycle fault injection (P0-003)

Escopo: `tests/fault-injection.test.ts` em `forge-cli@origin/main =
6ea2e79` vs. os 20 cenários obrigatórios do spec (prompt_evo_cycle11.2 §5).

## Comandos executados

```text
npx vitest run tests/fault-injection.test.ts   # worktree /tmp/forge-cli-main @ origin/main
```

Saída real (2026-10-17):

```text
✓ tests/fault-injection.test.ts (17 tests) 241ms
```

## Spec → cobertura

| # | Cenário do spec | Estado | Teste |
|---|---|---|---|
| 1 | Download interrompido | ✅ | `download interrompido → stage download + venv removida + sem state` |
| 2 | Hash incorreto | ✅ | `hash divergente → quarentena .rejected + venv removida + sem state` |
| 3 | Cache adulterado | ✅ | `cache adulterado (offline) → hash-mismatch + quarentena + sem venv` |
| 4 | State.json corrompido | ✅ | `parse falha → .corrupt preserva evidência` + `install sobre state corrompido → novo state válido sem perder .corrupt` |
| 5 | Venv incompleta | ✅ | `venv incompleta (sem bin) → verify falha nomeado + receipt auditável` |
| 6 | Python incompatível | ❌ não coberto | — |
| 7 | Falha do pip | ✅ | `pip fail → stage pip + cleanup total + state de outras Forjas intocado` |
| 8 | Permissão negada | ❌ não coberto | — |
| 9 | Disco cheio | ❌ não coberto | — |
| 10 | Processo interrompido | ✅ parcial | `retry após download interrompido` + `retry após hash-mismatch` (recovery pós-falha; SIGKILL no meio do write não é simulado) |
| 11 | Falha durante native install | ❌ não coberto | — |
| 12 | Falha no registro MCP | ❌ não coberto | — |
| 13 | Falha no host setup | ❌ não coberto | — |
| 14 | Rollback sem histórico | ✅ | `rollback sem history → erro nomeado + nada muda` |
| 15 | Rollback interrompido | ✅ | `rollback interrompido (pip fail) → versão corrente restaurada` |
| 16 | Uninstall parcial | ✅ | `uninstall parcial: alvo conhecido removido, desconhecido é erro nomeado` |
| 17 | Operação concorrente | ❌ não coberto | — |
| 18 | Versão yanked | ✅ | `versão yanked: só instala por pin explícito e marca o receipt` + `update para versão yanked → resolve ignora yanked` |
| 19 | Pacote indisponível | ✅ | `pacote 404 no PyPI → resolve not-found + zero escrita` |
| 20 | Incompatibilidade de contrato | ❌ não coberto | — |

Cobertura: **12/20** do spec (10 plenos + itens 10 parcial coberto por
recovery, contado no 12). Lifecycle interrompido tem prova de
restauração: update download-fail/pip-fail restauram a instalação
anterior; rollback pip-fail restaura a versão corrente — sem half-state.

## Não coberto — honesto

Permissão negada e disco cheio exigem injeção de falha de FS (chmod/ulimit)
que os testes não fazem; operação concorrente exige dois processos (não há
lock de state testado); native install / registro MCP / host setup são
falhas de subprocesso de outros componentes; incompatibilidade de contrato
não tem fixture de receipt malformado de versão futura.

## Veredito

FIXED_UNVERIFIED contra o spec completo — a suíte existe, é real e verde,
mas cobre 12/20 cenários. Os 8 restantes ficam OPEN sem disfarce.

## Risco residual

Falhas de FS (ENOSPC/EACCES) e concorrência são exatamente as classes que
corrompem state em produção real — o mecanismo (write atômico + `.corrupt`
backup + recovery marker) existe, mas sem prova sob essas falhas.
