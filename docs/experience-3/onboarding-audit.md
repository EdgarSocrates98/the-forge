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
verificada. `theforge setup` agora cobre a família registrada com um plano e
uma aprovação; `theforge` bare, o home textual e a TUI expõem a mesma entrada.

## Documentação de entrada

- `docs/installation/` ×12 guias por repo, quickstart pt+en,
  `portable-installation.md`, `workspace-installation.md`,
  `tutorials/first-run.md` ×7, troubleshooting pt+en.
- README com índice DX nos 7. `check_docs`: 0 problemas em ~2800 arquivos.

## Lacunas onboarding resolvidas nesta onda

- Wizard explica cada componente antes da seleção.
- Família de Forjas usa plano real → aprovação única → apply → saúde.
- Receipt textual aponta `specialists status`, `doctor` e `portal`.
- Portal recebe a mesma jornada por catálogo federado.

## Limites honestos

- Só Forjas registradas em `~/.forge/installations` entram na instalação
  automática; ausência do registro vira bloqueio explícito.
- Knowledge e evals permanecem nos pacotes/registro e entram por descoberta
  progressiva; não são copiados indiscriminadamente para projetos.
- Capacidades de host seguem evidência do instalador e do handshake de cada
  Forja; nenhum host é declarado equivalente sem verificação.
