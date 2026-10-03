# ADR 0009 — Cache do registry no diretório de cache do usuário

- Status: aceito (2026-10-03)

## Contexto
No ciclo 1, o cache ficava em `.forge/registry/<id>.json`, dentro do workspace analisado, e era verificado por um sha256 gravado no próprio arquivo. Isso detecta corrupção, mas não falsificação: um repositório malicioso podia escrever um manifest com capabilities extras e o hash correspondente.

## Decisão
- O cache fica fora do projeto, em `user_cache_dir()`: `THEFORGE_CACHE_DIR` se definido; senão `%LOCALAPPDATA%\theforge\Cache` (Windows), `~/Library/Caches/theforge` (macOS) ou `$XDG_CACHE_HOME/theforge` (se absoluto) ou `~/.cache/theforge` (Linux).
- Arquivo por entrada: `<cache>/registry/<id>-<digest12>.json`, onde `digest12` são os 12 primeiros hex do sha256 da entrada (`ProviderEntry`). O documento (`RegistryCacheEntry`) é relido com `strict=True` e guarda a entrada, o digest dela, o fingerprint local (ADR 0013), o manifest e o seu hash.
- Só manifests `ready` de providers não `unverified` são gravados (ADR 0006). Divergência de entrada, digest ou fingerprint é um miss silencioso (o provider é descrito de novo). Hash do manifest, id ou protocolo negociado divergentes, ou documento inválido, descartam o cache com aviso.
- Antes da decisão final de routing, todo candidato pontuado passa por describe de novo. Divergência invalida a entrada e refaz o routing uma única vez; uma segunda divergência é falha do provider (`REGISTRY_MANIFEST_CHANGED`).
- Escrita atômica (`mkstemp` + `os.replace`); falha de escrita vira aviso, nunca erro.
- Não há migração: o cache é regenerado. `init` e `refresh` removem o legado `.forge/registry` com aviso; se for symlink, só o link é removido, nunca o alvo.

## Alternativas
- **HMAC com chave local:** quem escreve no home também lê a chave.
- **TTL:** não detecta adulteração dentro da janela.
- **Manter no workspace com hash mais forte:** o conteúdo do projeto continua gravando o cache.

## Consequências
- O conteúdo do projeto não grava mais o cache. Fora do modelo: usuário local com escrita no próprio home.
- Arquivos de digests antigos não são podados, porque o cache é compartilhado entre workspaces e configurações. O custo é só disco.
- No Windows, `os.replace` concorrente sobre o mesmo arquivo pode falhar (`WinError 5`). A escrita perdida vira aviso, e o cache é regenerado na próxima leitura.
- Testes isolam o cache com `THEFORGE_CACHE_DIR` por teste.
