# ADR 0012 — Sandbox de SO: pesquisa, sem dependência no ciclo

- Status: aceito (2026-10-03)

## Contexto
Providers são código de terceiros chamados por subprocess (ADR 0001). O core controla o ambiente (allowlist e filtro de credenciais), o cwd (diretório temporário por chamada) e o encerramento da árvore de processos. Nada disso é sandbox.

## Limitações atuais
- O cwd controlado não é sandbox. O provider lê e escreve no home e no filesystem com as permissões do usuário, incluindo arquivos de credenciais (`~/.aws`, `~/.ssh`), mesmo sem as variáveis de ambiente.
- `operation_class` é uma declaração do provider, não enforcement. A policy (ADR 0010) confia nela.
- O fingerprint não cobre código importado (ADR 0013).
- O bloqueio de rede dos testes não cobre processos filhos.
- POSIX: um descendente que sai do grupo de processos (`setsid`, daemonização) escapa do kill.
- Windows, modo degradado: se o Job Object não puder ser criado ou atribuído, o kill usa `taskkill /T /F`, que não alcança um neto órfão cujo pai já terminou. O neto sobrevive, mas a chamada continua limitada a timeout + graça (2 s) + join das pipes (5 s).

## Pesquisa
- **Linux:** bubblewrap (binário externo, namespaces; o mais prático); `os.unshare` (3.12+, depende de user namespaces habilitados); Landlock (kernel 5.13+, via `ctypes`; restringe filesystem sem root); seccomp (filtra syscalls; complexo de manter).
- **macOS:** `sandbox-exec` com perfil SBPL. Está marcado como deprecated, mas ainda funciona. Não há alternativa stdlib.
- **Windows:** Job Objects (limites e kill de árvore, sem isolamento de filesystem ou rede; já usados só para kill); AppContainer (isolamento forte, complexo de configurar); restricted tokens (isolamento moderado).

## Decisão
Nenhum sandbox de SO neste ciclo, e nenhuma dependência nova. Job Object fica restrito ao kill de árvore. As limitações acima são documentadas em `docs/security.md`.

## Consequências
A proteção real vem do trust (ADR 0006/0010): só providers configurados pelo usuário roteiam. Um sandbox futuro deve ser opcional e por plataforma, com degradação explícita e registrada no receipt.

## Reavaliar quando (gatilho obrigatório)
Reabrir este ADR — e o sandbox deixa de ser opcional — quando **qualquer** uma destas condições se tornar verdade:

- uma wave permite **mutação externa** ou **ação destrutiva** por providers (hoje os `operation_class` expostos são declarados e a policy confia na declaração, sem enforcement de SO);
- um provider passa a **portar credenciais** (variáveis de ambiente fora da allowlist, segredos em payload ou acesso esperado a `~/.aws`, `~/.ssh` e similares);
- providers de **terceiros sem revisão** passam a executar sem o passo manual de registro/trust do usuário (hoje: `providers.toml` do usuário é o único caminho para trust > `unverified`).

## Reavaliação — ciclo 3 (2026-10-06)
O ciclo 3 foi avaliado contra o gatilho e **não o disparou**: as adições foram superfícies consultivas (`plan`, `resolve`, `verify` — todas com a superfície endurecida de `describe`/`health`), execução paralela com workdir por nó, caches relidos estritamente e memória de decisões sem poder de routing. Os adapters reais continuam read-only e offline; nenhum provider porta credenciais; trust continua manual. A decisão permanece: sem sandbox de SO, sem dependência nova, Job Object restrito ao kill de árvore.
