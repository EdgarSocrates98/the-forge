# Cycle 2.1 — Closure & Proof (relatório de trabalho)

- Branch: `feat/cycle2.1-cycle3`
- Início: 2026-10-05
- Status: IN PROGRESS
- Fonte de requisitos: `prompt_evo_cycle2_cycle3.md` (arquivo local, fora do git por `.gitignore`).

Este documento acompanha o Cycle 2.1 onda a onda. Cada onda registra: objetivo, arquivos
alterados, contratos criados/evoluídos, decisões arquiteturais, testes adicionados, testes
executados, resultados, benchmarks, security findings, limitações, dívida criada e próximos
passos.

## Reality check da `main` (Fase 1)

Auditoria feita em 2026-10-05 sobre `main` = `1eaa285` (merge do PR #4), Windows,
Python 3.14.6, antes de qualquer alteração. Fontes: leitura do código, `git log`,
`gh run view`, execução da suíte offline.

| Requirement | Claimed state (cycle-2.md, 2026-10-04) | Actual implementation | Tests | Remote evidence | Gap | Required action |
|---|---|---|---|---|---|---|
| Waves B–E na `main` | branches só locais, `main` em `b1d9ec7` | mergeadas no PR #4 (`1eaa285`) | — | `gh pr view 4`; run 37255244389 | relatório desatualizado | Wave A |
| CI pós-merge | "nenhum run depois da Wave A" | verde: 10 jobs (Ubuntu+Windows × py3.11–3.14, package ×2) | — | runs 37254645706 (PR), 37255244389 (main) | relatório desatualizado | Wave A |
| Suíte offline | 2719+5 (Wave D) | 2859 passed, 5 skipped, 0 failed | 77 arquivos | — | contagem desatualizada | Wave A |
| `real-providers.yml` | nunca executado | workflow completo; `THEFORGE_REAL_PROVIDERS_REQUIRED=1`; seleção vazia falha (exit 5 propaga) | `test_real_providers*.py` | dispatch 37260501716 em `main` | prova remota pendente | Wave B |
| `compat.yml` | nunca executado | `workflow_dispatch`, macOS × py{3.11, 3.14} | `test_compat_matrix.py` | dispatch 37260503904 em `main` | prova remota pendente | Wave B |
| `RunStore.read_optional` | "segue `<name>.json` simbólico" (follow-up aberto) | confirmado: `path.is_file()` segue symlink; `persisted_sha256`/`read`/`read_contract` idem | nenhum sobre symlink | — | escape de leitura via symlink | Wave C1 |
| `_finish` duplo | follow-up aberto | confirmado: erro não-persistência dentro de `_finish` (ex.: `IntegrityError` do `validate_receipt`) reentra `_finish` via `except Exception` | nenhum | — | re-terminalização | Wave C2 |
| Verification pós-erro interno | follow-up aberto | confirmado: exceção entre execute e `_record_verification` deixa run sem `verification` apesar de provider ter executado | nenhum | — | evidência perdida | Wave C3 |
| Artifacts declarados | "só conferido de forma léxica" (follow-up) | parcial: `explain` usa `lexists` (`hashcheck.work_artifacts`), mas `diverged_artifacts` do execute só compara hash | `test_verification.py` | — | classificação física (missing/broken/escape) | Wave D |
| Explain de `installation` | "falta teste" (follow-up) | `PlanSection.installation` existe e `hashcheck` cobre `plan.installation_sha256` | sem teste dedicado | — | só teste | Wave E1 |
| Drift live no cenário cross | follow-up aberto | `test_cross_forge_real` compara gravações parcialmente; sem check de drift live dedicado | — | — | Wave E2 | Wave E2 |
| Consumo de handoff | "adapters não declaram `accepts_handoff`" | confirmado: `execute_reply` do `theforge_apiforge` ignora `payload["handoff"]` | `test_cross_forge_replay.py` (limitação esperada) | — | transporte sem consumo | Wave F |
| `record_execute` do API Forge | "gravações montadas à mão" | `theforge_apiforge.record` só grava snapshot; cenários de execute são hand-built (`"provenance": "hand-built"`) | — | — | gravador ausente | Wave G |
| Follow-ups listados | 15+ itens abertos | confirmados por leitura: taskkill fallback, `GetLastError` ordering, cache pruning, policy flatten warning, `gethostbyname*`, `lexists` de artifacts, normcase macOS, pipe helpers, `hash_file`, `#L2`, `and/or`, verification pós-erro, `_finish` duplo, explain de installation, drift cross, symlink de artifact | — | — | classificação pendente | Wave H |
| Gate final do ciclo | STATUS CLOSED ausente | — | — | — | relatório final | Wave I |

Itens fora do escopo do Cycle 2.1 (pertenecem ao Cycle 3): routing semântico, execução
`delegate`/`parallel`/`debate`, scheduler/resume, verificação independente (`verify`),
economy avançada, `.forge/` project intelligence, tracing, provider SDK.

## Gap matrix → ondas

| Gap | Onda | Tipo |
|---|---|---|
| Documentação pós-merge desatualizada | A | docs |
| `real-providers.yml`/`compat.yml` sem run remoto | B | evidência CI |
| `RunStore` segue symlink | C1 | segurança |
| `_finish` reentrante | C2 | invariante |
| Verification ausente em erro pós-execute | C3 | integridade |
| Classificação física de artifacts declarados | D | integridade |
| Explain/cross-drift sem cobertura | E | testes |
| Handoff transportado mas não consumido | F | feature delimitada |
| `record_execute` do API Forge ausente | G | tooling |
| Follow-ups não classificados | H | processo |
| Gate final + relatório de fechamento | I | processo |

## Wave A — Post-Merge Validation Update

- **Objetivo:** registrar em `cycle-2.md` o estado pós-merge sem apagar o histórico.
- **Arquivos alterados:** `docs/reports/cycle-2.md` (nota de estado na geração + seção
  `Post-Merge Validation Update`), `README.md` (linha de status aponta o encerramento),
  `docs/reports/cycle-2.1.md` (este documento).
- **Contratos:** nenhum.
- **Decisões arquiteturais:** a atualização vive numa seção nova no fim do relatório, com
  tabela "estado na geração × estado validado"; o README deixa de dizer "concluído" até a
  Wave I declarar CLOSED.
- **Testes adicionados:** nenhum (mudança documental coberta pelos checkers existentes).
- **Testes executados:** `python -m pytest tests/test_docs_consistency.py`.
- **Resultados:** a preencher após a execução.
- **Benchmarks:** n/a.
- **Security findings:** nenhum.
- **Limitações:** os runs de `real-providers.yml`/`compat.yml` despachados sobre `main`
  provam a funcionalidade do workflow no estado mergeado; a prova sobre o conteúdo final da
  branch fica para a Wave B/relatório final.
- **Dívida criada:** nenhuma.
- **Próximos passos:** Wave B recolhe os resultados dos dispatches e reexecuta os workflows
  sobre a branch.
