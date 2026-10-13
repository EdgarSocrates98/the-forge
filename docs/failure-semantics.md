# Semântica de falha (Cycle 3 Wave U)

Cada modo de falha do sistema é definido aqui com cinco elementos: **código de erro**,
**família**, **mensagem humana**, **resultado machine-readable** e **dica de recuperação**.
Nenhum caminho usa uma exceção genérica como protocolo: erros esperados são `ForgeError`
com código da taxonomia única ([`errors.md`](errors.md)); o inesperado sai como
`FORGE-INTERNAL` com um `Diagnostic` redigido sob `--debug`.

As dicas de recuperação vivem na fonte única `CODE_HINTS`/`hint_of`
(`src/theforge/contracts/codes.py`): toda linha de erro da CLI termina com
`theforge: hint: <hint>` quando o código tem uma, e `Diagnostic.hint` carrega a mesma
dica. `tests/test_failure_semantics.py` garante que todo código tem hint e que cada modo
abaixo mapeia para código e superfície reais.

## Matriz dos modos

| Modo | Códigos (família) | Mensagem humana | Resultado machine-readable | Recuperação |
|---|---|---|---|---|
| **provider failed** | `FORGE-PROTO-*` (protocol), `FORGE-RESULT-*`, `FORGE-PROVIDER-*` (provider), refusal do provider | `theforge: error: <detalhe> [<code> · <family>]` + linha `hint:` | nó `provider_failure` no `plan-result`; run `partial`/`failed`; `detail` do `NodeOutcome` carrega o código | corrigir o provider (`provider check`), ajustar timeout/perfil; `theforge resume` reexecuta só o nó |
| **planner unavailable** | `FORGE-PLAN-ESTIMATE` e códigos `PROTO-*`/`PROVIDER-*` embrulhados na limitação `proposal: FORGE-…` | limitação no `plan`: `proposal: FORGE-PLAN-ESTIMATE: …` | `plan.limitations`; proposta ausente ou `semantic-proposal` rejeitada | planejamento **degrada para o decompositor determinístico** — nunca levanta; corrigir o planner restaura o caminho semântico |
| **planner invalid** | `FORGE-PLAN-INVALID`, `FORGE-PLAN-CAPABILITY`, `FORGE-PLAN-LIMIT` (plan) | `violations` renderizadas com node+detail | `plan.status="rejected"` + `plan.violations[]`; nenhum nó executado | corrigir a proposta/plan file; a validação estrutural é soberana sobre o raciocínio |
| **verifier unavailable** | — (desfecho, não erro) | `independent: not_performed: <razão>` no explain | `verification.independent.status="not_performed"` + `basis` com a razão (`no provider declares can_verify`, …) | registrar um provider com `can_verify`/`verify`, ou aceitar o nível `minimal` |
| **budget exhausted** | — (orçamento é enforcement, não erro) | `truncated: true` / exclusões `reason=budget` | `context.truncated`, `excluded[].reason="budget"`, `budget` artifact com os tetos | subir o perfil (`--profile max`) ou restringir os targets; limites do `RunBudget` estão no artifact |
| **context exhausted** | `FORGE-CONTEXT-REQUEST-LIMIT`, `FORGE-CONTEXT-REQUEST-UNSUPPORTED`, `FORGE-CONTEXT-REQUEST-INVALID` (context) | `error`/`provider_failure` com o código no detalhe | `NodeOutcome`/`ExecutionResult` com o código; `excluded[]` registra cada item recusado | declarar `context.requests`, subir `negotiation_rounds` via perfil, ou reduzir os itens |
| **partial evidence** | — (evidência é epistêmica) | itens `unresolved`/`inferred` rotulados no explain/result | `evidence[].epistemic`, `limitations`, `unknowns`, status `partial` | declarado, nunca escondido: produzir mais evidência ou reexecutar; `not_performed` é sempre explicado |
| **handoff incomplete** | — (limitação, não erro) | limitação `handoff-input-missing: <nó>` / `handoff-filtered: …` | `handoff.limitations`, `truncated`, itens efetivamente entregues | corrigir o produtor/upstream; `resume` reexecuta o nó se o estado gravado for inválido |
| **resume incompatible** | `FORGE-USAGE` (usage) | `run <id> has no resumable plan` + `hint:` | exit 2; `Diagnostic` com `stage=cli:resume` | estado ausente/inválido nunca é reusado: o nó reexecuta (`resume: node <n> re-executed`); sem plano nenhum, refaça `theforge plan` |

## Garantias transversais

- **Nada genérico na superfície**: exceções esperadas mapeiam para código+família; a
  exceção inesperada sai `FORGE-INTERNAL` (exit 70) com `Diagnostic` redigido — um
  traceback nunca é impresso.
- **Degradação explícita**: planner e resolver semânticos falham para *limitação* e o
  caminho determinístico assume; verificação indisponível vira `not_performed`
  justificada; evidência parcial vira epistemic status, nunca sucesso inflado.
- **Integridade primeiro**: qualquer dúvida sobre estado persistido (hash, identity,
  handoff) faz o resume reexecutar o nó — a recusa é barata, o reúso errado não.
