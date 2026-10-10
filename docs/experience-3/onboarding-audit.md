# Onboarding Audit — Forge Experience 3.0

## Jornada medida (clone → primeira tarefa)

```text
git clone <forja>            1 comando
python forge_bootstrap.py    1 comando  → ambiente + launcher
<cli>                        0..1       → home/wizard (TTY)
wizard: scope→profile→hosts→components→review→confirm→apply→doctor
primeira tarefa              home → "run a task"/menu → execução real
```

Total medido: **2 comandos + ~6 decisões interativas** até instalação
verificada — já próximo do "one-command setup". O que falta é
descoberta *dentro* do produto: sem search, sem palette, sem help
contextual na TUI (GAP-006).

## Documentação de entrada

- `docs/installation/` ×12 guias por repo, quickstart pt+en,
  `portable-installation.md`, `workspace-installation.md`,
  `tutorials/first-run.md` ×7, troubleshooting pt+en.
- README com índice DX nos 7. `check_docs`: 0 problemas em ~2800 arquivos.

## Lacunas onboarding reais

- Wizard não lista **o que cada componente instala** antes de escolher
  (progressive disclosure parcial).
- Sem "próximos passos" pós-instalação direcionados (receipt mostra
  status; não guia para first task).
- `first-run.md` existe mas não é linkado pela TUI.
- Sem `--tutorial`/`walkthrough` verb; descoberta depende do README.
