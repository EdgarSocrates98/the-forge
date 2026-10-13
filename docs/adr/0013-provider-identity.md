# ADR 0013 — Identidade local de provider

- Status: aceito (2026-10-03)

## Contexto
O `manifest_sha256` do receipt prova qual manifest foi usado, não qual código rodou: qualquer executável pode emitir o mesmo manifest. O cache (ADR 0009) precisa invalidar quando o provider muda, e o receipt precisa dizer o que foi observado.

## Decisão
- Fingerprint local (`registry/identity.py`): o executável resolvido (`shutil.which(argv[0])` ou o próprio `argv[0]`) e, para ele e para cada argumento de `argv` que é um arquivo existente, `(path, tamanho, mtime_ns)`. O digest é o sha256 desse conjunto.
- O cache guarda o digest. Se o executável ou um arquivo do `argv` mudar, a entrada é invalidada. Uma versão diferente aparece no manifest e é pega pelo hash do manifest no describe de revalidação.
- O receipt registra `executable`, `fingerprint` e `observed_version` (a versão reportada no describe anterior ao run), além de `manifest_sha256`.
- `load_entries` resolve argumentos relativos de `argv` contra o diretório do `providers.toml`, para que o fingerprint use caminhos absolutos e não dependa do cwd. Um argumento relativo com separador (`/` ou `\`) que não seja arquivo existente (diretório, URL, caminho inexistente) é erro de configuração (`UsageError`). Depois de `argv[0]`, um argumento relativo sem separador que exista como arquivo no diretório do `providers.toml` (por exemplo, `run.py`) também vira caminho absoluto. `argv[0]` sem separador, flags (`-m`) e os demais nomes simples (nomes de módulo) ficam como estão.

## Limitações
- O fingerprint não cobre código importado: em `python -m pkg`, ou num script que importa módulos, só o interpretador e os arquivos do `argv` entram. A revalidação pré-execute compensa isso para os candidatos: um describe divergente invalida o cache e refaz o routing.
- `mtime` e tamanho detectam mudança acidental, não adulteração deliberada por quem tem escrita no home.
- O hash do manifest não prova identidade.

## Evolução (fora deste ciclo)
Assinatura do executável ou do pacote, publisher declarado e verificado, e hash do pacote instalado (wheel ou RECORD). Nada disso é obrigatório agora. Candidato natural a requisito do nível `trusted` (ADR 0010).

## Consequências
O receipt diz o que foi observado localmente, sem prometer autenticidade.
