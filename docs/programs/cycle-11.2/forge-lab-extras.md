# Cycle 11.2 — Forge Lab interpreter/extras (P1-005)

Escopo: the-forge#83 OPEN (`feat/c11-2-lab`) — resolução auditável de
interpretador para o coletor federado do Forge Lab.

## Comandos executados

```text
gh pr view 83 --json body,files,statusCheckRollup,mergeable
git diff origin/main...origin/feat/c11-2-lab --stat
git show origin/feat/c11-2-lab:src/theforge/lab.py | grep -n …
git show origin/feat/c11-2-lab:tests/test_lab_interpreter.py | grep -c "def test_"
```

## Cadeia de resolução (ordem fixa de autoridade — o primeiro candidato existente e compatível vence)

1. `explicit` — `theforge lab collect --python PATH` (operador; caminho
   ausente é registrado e rejeitado, nunca silencioso)
2. `managed-receipt` — receipt forge-cli
   `~/.forge-cli/forges/<forge>/install.json` → `venv`/sibling de `bin`
   (receipt inválido/ilegível pula o nível com warning)
3. `manifest` — `~/.forge/installations` (`<FORGE>_PYTHON` →
   `python.executable` → `venv`)
4. `specialist-env` — `.venv` repo-local do checkout
5. `fallback` — `sys.executable`, sempre último e documentado

Cada candidato é validado **antes** da seleção contra a spec declarada
(`python.satisfies` no manifest ou `"python": ">=3.11"` no forge.json do
checkout) e os `extras` declarados — leitura de `pyvenv.cfg`/
`sys.version_info` quando legível; senão um único probe `-c` bounded e
read-only (versão + extras faltantes num só spawn). Todos reprovados →
lab **BLOCKED** — nunca roda em interpretador não provado.

## Estados honestos

`LabOutcome` ganha `reason` + `interpreter`; `state` deriva
`PASS/FAIL/SKIPPED/BLOCKED/ERROR` de `status`+`reason` — SKIPPED nunca
vira PASS; BLOCKED não é rebaixado e falha o gate do `collect`. Mapa
`status→state` em `lab.py`: `undeclared`/`none`/`unsupported-mode` →
SKIPPED; `blocked` → BLOCKED. Relatórios JSON/Markdown carregam state,
reason, interpretador, fonte, versão, extras, candidatos rejeitados e
warnings; exit code 4 em falhas. `--python` também em `lab list`
(inspect-only, sem spawn).

## Diff

```text
scripts/lab/theforge_lab.py   |   4 +-
src/theforge/cli/commands.py  |  30 +-
src/theforge/cli/main.py      |  15 +
src/theforge/cli/render.py    |  12 +-
src/theforge/lab.py           | 616 +++-
tests/conftest.py             |   1 +
tests/test_lab.py             |   2 +
tests/test_lab_interpreter.py | 403 ++++ (15 testes)
```

Cobertura nova (15 testes): ordem de prioridade, sibling de bin no
receipt, python incompatível rejeitado, all-rejected → BLOCKED, explicit
ausente + manifest ausente, versão indeterminável em ambiente corrompido,
receipt inválido → warning + fall-through, venv sem interpretador →
warning, extras faltantes → BLOCKED, extras presentes → seleciona,
specialist-env vence fallback, states/reasons no relatório, probe
grátis vs. spawnado.

## Estado do PR (captura 2026-10-17)

`state: OPEN`, `mergeable: MERGEABLE`, `mergeStateStatus: BLOCKED`.
Checks: SUCCESS ×10 (gate/build, package ×2, gate/unit, gate/contract,
etc.) · SKIPPED ×6 (gates nightly/manual por desenho) · IN_PROGRESS ×4
(test ubuntu/windows × py3.11–3.14 parciais no momento da captura).

## Veredito

IN_PROGRESS — implementação e testes existem no PR; ainda não mergeado.

## Risco residual

Probe `-c` spawnado por candidato ilegível — bounded mas ainda subprocess
por candidato; receipts de forge-cli antigos sem `venv` caem para
warning+fall-through (comportamento correto, mas significa labs rodando
em fallback quando o managed install existe porém não declara).
