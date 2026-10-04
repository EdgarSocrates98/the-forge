# Escrevendo um provider

Um provider é qualquer executável que implementa o [Forge Protocol v1](protocol.md). A linguagem é livre.

## Mínimo
1. Ler `argv[-1]` como op e o request JSON do stdin.
2. `describe`: responder com o `ForgeManifest` (`id` igual ao id registrado; `ops` contendo `describe` e `health`, e `execute` se o provider executa algo).
3. `health`: responder `{"status":"ok","checks":[]}`.
4. `execute`: ler `payload.capability`, `payload.action` e `payload.context.files` (paths relativos a `payload.task.workspace_root`) e responder com um `ExecutionResult`.
5. Capability desconhecida → `status: "refused"` com `error.code` e, se fizer sentido, `unlock`.
6. Sempre exit 0 com uma response válida. Crash vira `provider_failure` no core.
7. Em toda response: ecoar `request_id`, emitir `"op"` igual à op pedida e `producer` com `id` igual ao id registrado e `version` igual à `version` do manifest.

Exemplo completo e standalone: `tests/fixtures/providers/fixture_forge.py`.

## Capabilities e sinais
- Formato do id: `domínio.assunto` (`^[a-z][a-z0-9-]*(\.[a-z][a-z0-9-]*)+$`), único no manifest. `actions` não pode ser vazio e `default_action` precisa estar em `actions`.
- Os sinais (`keywords`, `file_globs`, `dependencies`) são a única fonte de conhecimento do router. A decisão usa só a **presença por tipo** de sinal casado (0 a 3): declarar mais sinais do mesmo tipo não aumenta o score. Com menos de 2 tipos casados, ou empate, o resultado é `ambiguous` e nada executa.
- Um sinal casado por todos os candidatos (mesmo glob, dependência ou keyword) não discrimina: não conta e aparece nas `limitations` do routing. Declare sinais específicos do seu domínio.
- Respeite os [limites de manifest](protocol.md#manifest) (256 capabilities; por capability, 16 actions, 64 keywords, 32 globs, 32 dependências). Uma capability acima do limite ou com glob catch-all (`*`, `**/*`, `?*`, …) é excluída com aviso `FORGE-MANIFEST-LIMITS`. Globs por extensão (`*.md`) são permitidos.
- `state`: `heuristic` ou `unresolved` nunca resultam em confiança `high`.
- `operation_class` declara o efeito colateral (`read_only` … `destructive`) e alimenta a [policy](security.md#policy-e-risco). `execution.requires_network = true` conta como leitura externa. É uma **declaração**, não enforcement: o core não verifica o que o provider faz. Declarar menos do que faz é quebra de contrato com o usuário.
- Sem `execute` em `ops`, as capabilities não são roteáveis: o routing registra a exclusão em `limitations` quando ela é relevante, e um pedido explícito de uma capability que nenhum outro provider poderia executar é recusado com `FORGE-PROTO-OP-UNSUPPORTED` ([protocol.md](protocol.md)).

## Resultado
O core rejeita o resultado inteiro se alguma regra de [integridade](protocol.md#integridade-do-resultado) falhar:
- IDs de evidence e de finding únicos, e todo `evidence_ids` apontando para uma evidence existente.
- `artifacts[].path` relativo POSIX, sem `\`, `/` inicial, drive (`C:`) ou `..`.
- Hashes SHA-256 em 64 hex minúsculos.
- `created_at` em ISO-8601 UTC (`Z` ou `+00:00`).

## Contexto: tiers, pedidos e revalidação
Detalhes normativos em [protocol.md](protocol.md#contexto-v2). Tudo é opcional: um provider que não declara nada recebe só itens `reference` e nunca deve enviar `context_request`.

- **Leitura por item.** Cada `payload.context.files[]` tem `tier`. `reference` (e `requested` sem `lines`): leia o arquivo inteiro. `excerpt` (e `requested` com `lines`): leia só as linhas `lines.start..lines.end` (1-based, inclusivo, linhas delimitadas por `\n`, cada uma com o seu `\n`). O `sha256` e os `bytes` do item são do que deve ser lido, não do arquivo inteiro.
- **Declarar excerpts.** Só declare `capabilities[].context.excerpts: true` se a capability lê por intervalo. Sem a declaração, o core nunca envia `excerpt`; um arquivo grande demais para o budget é excluído (`budget`) em vez de recortado.
- **Declarar pedidos.** `capabilities[].context.requests: true` permite responder `execute` com `context_request: {items: [{path, lines?, reason}]}` (1 a 64 itens). O core estende o pack e chama `execute` de novo, até 0 (`economy`), 1 (`balanced`) ou 2 (`max`) rodadas. Pedido sem a declaração, além das rodadas ou com quantidade inválida de itens termina o run em `provider_failure` (`FORGE-CONTEXT-REQUEST-UNSUPPORTED`, `-LIMIT`, `-INVALID`). Itens fora da raiz, de segredo, inexistentes ou sem budget voltam em `excluded` com o motivo; não peça de novo o que foi recusado. Cada rodada tem o timeout inteiro do perfil.
- **Revalidar o que leu (obrigatório).** Escolha uma estratégia e declare-a em `context_revalidation` no manifest:
  - `hash`: recalcule o sha256 do conteúdo que leu e informe-o em `Evidence.hash` (estratégia recomendada; o eco embutido a usa);
  - `core`: não revalida e conta com a reverificação do core (que depende do perfil: `economy` não reverifica);
  - `none`: não revalida.

  Sem a declaração, o run registra `provider-revalidation-undeclared`.
- **Semântica de `Evidence.hash`.** É o sha256 de **exatamente** o conteúdo entregue em `location.path`: o arquivo inteiro para `reference` e `requested` sem `lines`; os bytes do intervalo `lines` para `excerpt` e `requested` com `lines`. `location.line` não muda o escopo. Deixe `hash` nulo quando a evidência não tem `location`, quando o caminho não está no ContextPack ou quando a leitura não cobre exatamente o conteúdo do item (por exemplo, só parte de um arquivo entregue como `reference`).
- **Divergência.** Um `hash` diferente do `sha256` de todos os itens com o mesmo caminho é divergência: as evidências `confirmed`/`observed` sobre o item viram `unresolved`, o resultado recebe `context-drift: <path>` e o run termina `partial`. Um `hash` com escopo errado (o do arquivo inteiro para um `excerpt`) também conta como divergência.
- **Tokens.** Informe `metrics.tokens` só com `kind` `measured` ou `estimated` e `value` não negativo; o core preserva esse valor e nunca converte bytes em tokens. Sem isso, fica `unknown`.

## Regras de segurança
- Leia apenas os arquivos listados no ContextPack e confira se continuam dentro de `workspace_root`.
- Não espere credenciais no ambiente: o core repassa só uma [allowlist de variáveis](security.md#ambiente-do-provider) e remove nomes com cara de credencial.
- Não dependa do cwd. Em `execute` ele é o diretório de trabalho do run (`.forge/runs/<id>/work`), e efeitos colaterais devem ficar ali. Em `describe` e `health` é um diretório temporário apagado depois da chamada. O cwd não é sandbox.
- Não deixe processos em segundo plano: em timeout o core encerra a árvore inteira do provider.
- O `producer` das responses e do resultado deve ser o do provider (id e versão). O core rejeita (`FORGE-PROTO-PRODUCER`) um valor diferente no envelope de `describe`, `health` e `execute` e no `ExecutionResult.producer`.

## Registro e trust
Registre o provider no `providers.toml` do **usuário** para receber trust (`trusted`/`local`). Entradas em `.forge/config/providers.toml` do projeto entram sempre como `unverified` (um `trust` maior é rebaixado com aviso) e só rodam com `--allow-unverified`. O que cada nível permite está em [security.md](security.md#níveis-de-trust). Veja o [README](../README.md#registrar-um-provider).

Argumentos relativos de `argv` são resolvidos contra o diretório do `providers.toml`, não contra o cwd. Um argumento relativo com separador (`/` ou `\`) que não seja um arquivo existente é erro de configuração (exit 2). Detalhes em [ADR 0013](adr/0013-provider-identity.md).

## Certificação
Adicione o argv do provider em `PROVIDER_ARGVS` de `tests/test_conformance.py` e rode `python -m pytest tests/test_conformance.py`.
