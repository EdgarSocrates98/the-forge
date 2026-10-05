# ADR 0016 — Sinais git somente leitura

- Status: aceito (2026-10-04)

## Contexto
Arquivos alterados no git são um sinal forte de relevância para o contexto (ADR 0015), e branch e HEAD ajudam a explicar um run. Mas o repositório analisado está no modelo de ameaça: a configuração local de um repositório pode fazer o `git` executar programas (`core.fsmonitor`, filtros `clean`/`smudge`/`process`) e, num clone parcial, até buscar objetos pela rede usando um transporte escolhido pelo repositório (`ext::<comando>`, `core.sshCommand`). Um `git status` comum também pode reescrever o índice (`index.lock`).

## Decisão
- Consulta em `context/git.py`, executada só depois da policy, com o `git` do `PATH` (opcional). 5 processos, cada um como `git -c core.fsmonitor=false …`, com um orçamento **total** de 5 s e kill da árvore (`protocol.proctree`):
  1. `rev-parse --show-toplevel --absolute-git-dir`;
  2. `symbolic-ref -q --short HEAD`;
  3. `rev-parse --verify -q HEAD`;
  4. `config --list --show-scope --includes -z`;
  5. `status --porcelain=v1 -z --untracked-files=all --ignore-submodules=all --no-renames`.
- Ambiente: `safe_env()` (sem credenciais, sem `GIT_*` herdado) mais `GIT_OPTIONAL_LOCKS=0`, `GIT_TERMINAL_PROMPT=0`, `GIT_PAGER=cat`, `LC_ALL=C`, `GIT_NO_LAZY_FETCH=1` e `GIT_ALLOW_PROTOCOL=none` (nenhum transporte, nem os que o repositório libera em `protocol.*.allow`).
- O `status` é recusado, com limitação, quando a configuração de escopo `local` ou `worktree` define `core.fsmonitor` (qualquer valor) ou `filter.<driver>.clean|smudge|process`, quando o git não reporta escopos (< 2.26) ou quando a configuração não pode ser inspecionada.
- `safe.directory` nunca é alterado: um repositório recusado pelo git é limitação.
- Toda falha (git ausente, não repositório, timeout, ownership, configuração executável, versão antiga) vira limitação `git: …`; a consulta nunca levanta exceção e nunca falha o run. O git não entra no routing.
- Semântica: `available` = repositório localizado; `dirty` = qualquer entrada do `status` no repositório inteiro; `changed_files` = alterados dentro da raiz do workspace (então `dirty` com 0 alterados é possível). Estados (`merge`, `rebase`, `cherry_pick`, `bisect`, `no_commits`, HEAD destacado) não falham o run.
- Quem precisar de HEAD e estado sujo (por exemplo, o descritor de workspace de `cross-forge-foundation`) reutiliza `read_git_state` em vez de executar o git por conta própria.

## Errata do design
- O design previa "até 4 processos git" e `rev-parse --abbrev-ref HEAD` para o branch. `--abbrev-ref HEAD` sai com 128 num repositório sem commits, então o branch passou para `symbolic-ref` e a consulta tem 5 processos.
- O design afirmava que `core.fsmonitor` e os filtros eram as únicas chaves que fazem o `status` executar um programa. Isso está errado: num clone parcial, o lazy fetch de objetos ausentes executa o transporte do remoto configurado no repositório. A correção é o ambiente sem transporte (`GIT_NO_LAZY_FETCH=1`, `GIT_ALLOW_PROTOCOL=none`), coberta por teste de regressão.

## Alternativas
- **Biblioteca git em Python (dulwich, pygit2)**: dependência de runtime, proibida.
- **Ler `.git` diretamente** (índice, refs): reimplementar o formato do índice e de packs é frágil e não detecta alterações sem comparar o worktree.
- **Recusar qualquer repositório com configuração local**: perderia o sinal em quase todo repositório real.
- **Sobrescrever `safe.directory`**: confiaria num repositório que o próprio git recusou.

## Limitações
- Filtros, hooks e `fsmonitor` da configuração **global** ou de **sistema** do usuário (por exemplo `git-lfs`) não são detectados e podem rodar durante o `status`: são configuração do próprio usuário.
- `GIT_NO_LAZY_FETCH` exige git ≥ 2.44; antes disso a proteção contra lazy fetch depende só de `GIT_ALLOW_PROTOCOL=none`, que vale em qualquer versão.
- O executável `git` do `PATH` é confiado.
- Custo: quando o workspace está dentro de um repositório, cada run paga 5 processos `git` (observado em ~0,7–1,3 s por run nos testes no Windows).

## Consequências
O contexto ganha o sinal `git:changed` e o resumo `workspace.git` sem nenhuma escrita no repositório (o git dir fica idêntico antes e depois, testado) e sem executar programas definidos pelo repositório. Mudança na lista de chaves executáveis, nos argumentos ou no ambiente da consulta exige reexecutar os testes de não escrita e não execução.
