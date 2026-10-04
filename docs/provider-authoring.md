# Escrevendo um provider

Um provider é qualquer executável que implementa o [Forge Protocol v1](protocol.md). A linguagem é livre.

## Mínimo
1. Ler `argv[-1]` como op e o request JSON do stdin.
2. `describe`: responder com o `ForgeManifest` (`id` igual ao id registrado; `version` em SemVer 2.0.0; `ops` contendo `describe` e `health`, e `execute` se o provider executa algo).
3. `health`: responder `{"status":"ok","checks":[]}`.
4. `execute`: ler `payload.capability`, `payload.action` e `payload.context.files` (paths relativos a `payload.task.workspace_root`) e responder com um `ExecutionResult`.
5. Capability desconhecida → `status: "refused"` com `error.code` e, se fizer sentido, `unlock`.
6. Sempre exit 0 com uma response válida. Crash vira `provider_failure` no core.
7. Em toda response: ecoar `request_id`, emitir `"op"` igual à op pedida e `producer` com `id` igual ao id registrado e `version` igual à `version` do manifest.

Exemplo completo e standalone: `tests/fixtures/providers/fixture_forge.py`. Exemplos reais, que traduzem um Forge especialista existente: `adapters/sparkforge` e `adapters/apiforge` ([ADR 0014](adr/0014-provider-adapter-location.md), guia em [real-providers.md](real-providers.md)).

## Versão
`version` precisa ser [SemVer 2.0.0](https://semver.org/): `1.2.3`, `0.1.0-rc.1`, `1.0.0+build.5`. Versão malformada deixa o provider `invalid` com `FORGE-MANIFEST-VERSION` ([versioning.md](versioning.md#versão-de-provider)).

## Capabilities e sinais
- Formato do id: `namespace.subject[.qualifier]` (2 a 3 segmentos), único no manifest. `actions` não pode ser vazio e `default_action` precisa estar em `actions`. As regras de nome, ação, granularidade e sobreposição estão em [capabilities.md](capabilities.md) e no [ADR 0017](adr/0017-capability-taxonomy.md). Uma capability fora das regras mecânicas é excluída com aviso `FORGE-MANIFEST-TAXONOMY`; as demais continuam.
- Evolução: uma capability publicada não muda de significado. Mudança incompatível vira capability nova; a antiga recebe `deprecated = true` e, se houver substituta, `replaced_by`. Renomeação usa `aliases` (o ID antigo continua atendendo `--capability`). Alias repetido ou igual a um ID do mesmo manifest deixa o provider `invalid` ([protocol.md](protocol.md#taxonomia-aliases-e-depreciação)).
- O que o provider não expõe (ferramenta que pede rede, credenciais ou escrita) vai para `limitations` do manifest com o motivo, como fazem os adapters reais.
- Os sinais (`keywords`, `file_globs`, `dependencies`) são a única fonte de conhecimento do router. A decisão usa só a **presença por tipo** de sinal casado (0 a 3): declarar mais sinais do mesmo tipo não aumenta o score. Com menos de 2 tipos casados, ou empate, o resultado é `ambiguous` e nada executa.
- Um sinal casado por todos os candidatos (mesmo glob, dependência ou keyword) não discrimina: não conta e aparece nas `limitations` do routing. Declare sinais específicos do seu domínio.
- Respeite os [limites de manifest](protocol.md#manifest) (256 capabilities; por capability, 16 actions, 64 keywords, 32 globs, 32 dependências). Uma capability acima do limite ou com glob catch-all (`*`, `**/*`, `?*`, …) é excluída com aviso `FORGE-MANIFEST-LIMITS`. Globs por extensão (`*.md`) são permitidos.
- `state`: `heuristic` ou `unresolved` nunca resultam em confiança `high`.
- `operation_class` declara o efeito colateral (`read_only` … `destructive`) e alimenta a [policy](security.md#policy-e-risco). `execution.requires_network = true` conta como leitura externa. É uma **declaração**, não enforcement: o core não verifica o que o provider faz. Declarar menos do que faz é quebra de contrato com o usuário.
- Sem `execute` em `ops`, as capabilities não são roteáveis: o routing registra a exclusão em `limitations` quando ela é relevante, e um pedido explícito de uma capability que nenhum outro provider poderia executar é recusado com `FORGE-PROTO-OP-UNSUPPORTED` ([protocol.md](protocol.md)).

## Resultado
O core rejeita o resultado inteiro se alguma regra de [integridade](protocol.md#integridade-do-resultado) falhar:
- IDs de evidence e de finding únicos, e todo `evidence_ids` apontando para uma evidence existente.
- `artifacts[].path` relativo POSIX, sem `\`, `/` inicial, drive (`C:`) ou `..`. A raiz é o cwd do `execute` (`.forge/runs/<id>/work/`): grave o artifact ali e declare o caminho relativo a ele, com o `sha256` dos bytes gravados.
- Hashes SHA-256 em 64 hex minúsculos.
- `created_at` em ISO-8601 UTC (`Z` ou `+00:00`).

### `Evidence.hash`
`Evidence.hash` é o sha256 **exatamente** do conteúdo coberto pelo item do ContextPack em `location.path`: os bytes do arquivo inteiro (ou do intervalo, quando o item tem `lines`) que o provider conferiu contra o `sha256` do pack. Em qualquer outro caso é `null`: hash ausente, calculado sobre outra coisa (texto decodificado, payload parseado, outro arquivo) ou que não dá para provar igual. Nunca copie um hash nativo sem conferir. Os adapters reais usam `evidence_hash` de `_shell.py`: o hash nativo (com prefixo `sha256:` opcional) só é mantido quando é igual ao sha256 verificado do arquivo copiado para `stage/`.

### `context_revalidation`
Um provider que confere o sha256 de cada arquivo do ContextPack antes de usá-lo pode declarar `"context_revalidation": "hash"` no manifest. Os dois adapters reais declaram: copiam para `<cwd>/stage/` só os arquivos dentro de `workspace_root` cujo sha256 bate com o do pack, e o especialista lê só essas cópias; o resto vira a limitação `context file '<p>' skipped: <motivo>`. O campo é opcional, e um core que não o conhece o ignora.

## Regras de segurança
- Leia apenas os arquivos listados no ContextPack e confira se continuam dentro de `workspace_root`.
- Não espere credenciais no ambiente: o core repassa só uma [allowlist de variáveis](security.md#ambiente-do-provider) e remove nomes com cara de credencial.
- Não dependa do cwd. Em `execute` ele é o diretório de trabalho do run (`.forge/runs/<id>/work`), e efeitos colaterais devem ficar ali. Em `describe` e `health` é um diretório temporário apagado depois da chamada. O cwd não é sandbox.
- Contenha o estado nativo no cwd do `execute` (caches, journals, bancos locais) e, antes de sair, reduza o cwd aos artifacts declarados. `work/` não passa por `security.redact` ([security.md](security.md#exceção-forgerunsidwork)). Os adapters reais fazem isso com `cleanup_workdir` em todo desfecho.
- `describe` e `health` devem caber em 10 s, sem rede e sem credenciais: evite importar a superfície inteira do especialista só para responder.
- Não deixe processos em segundo plano: em timeout o core encerra a árvore inteira do provider.
- O `producer` das responses e do resultado deve ser o do provider (id e versão). O core rejeita (`FORGE-PROTO-PRODUCER`) um valor diferente no envelope de `describe`, `health` e `execute` e no `ExecutionResult.producer`.

## Registro e trust
Registre o provider no `providers.toml` do **usuário** para receber trust (`trusted`/`local`). Entradas em `.forge/config/providers.toml` do projeto entram sempre como `unverified` (um `trust` maior é rebaixado com aviso) e só rodam com `--allow-unverified`. O que cada nível permite está em [security.md](security.md#níveis-de-trust). Veja o [README](../README.md#registrar-um-provider).

Argumentos relativos de `argv` são resolvidos contra o diretório do `providers.toml`, não contra o cwd. Um argumento relativo com separador (`/` ou `\`) que não seja um arquivo existente é erro de configuração (exit 2). Detalhes em [ADR 0013](adr/0013-provider-identity.md).

## Nota de migração (ciclo 2, Wave B)
Para providers escritos antes desta versão do core:

- **Versão.** `version` passa a ser validada como SemVer 2.0.0. `1.0` vira `1.0.0`; `v1.2.3` vira `1.2.3`. Sem isso o provider fica `invalid` (`FORGE-MANIFEST-VERSION`) e sai do routing.
- **Taxonomia.** IDs com 4+ segmentos, segmentos genéricos (`all`, `misc`, `tools`, …), namespaces `forge`/`theforge` ou ações fora de `^[a-z][a-z0-9-]{0,31}$` são excluídos (`FORGE-MANIFEST-TAXONOMY`). Para trocar um ID publicado, declare o novo e mantenha o antigo em `aliases`.
- **Cache.** O primeiro `registry refresh` (ou `ask`) depois da atualização descarta cada entrada do cache uma vez, com aviso, porque o hash do manifest passa a incluir os campos novos com default. Não há ação a tomar.
- **Artifacts.** Paths de `artifacts[]` são relativos ao cwd do `execute`. Um provider que declarava paths relativos ao workspace precisa gravar o artifact no cwd.
- **Evidence.** Revise `Evidence.hash`: hash que não seja o sha256 exato do conteúdo em `location.path` deve virar `null`.

## Certificação
Adicione o argv do provider em `PROVIDER_ARGVS` de `tests/test_conformance.py` e rode `python -m pytest tests/test_conformance.py`.
