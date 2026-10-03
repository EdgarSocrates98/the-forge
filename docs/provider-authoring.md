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
- Sem `execute` em `ops`, as capabilities não são roteáveis.

## Resultado
O core rejeita o resultado inteiro se alguma regra de [integridade](protocol.md#integridade-do-resultado) falhar:
- IDs de evidence e de finding únicos, e todo `evidence_ids` apontando para uma evidence existente.
- `artifacts[].path` relativo POSIX, sem `\`, `/` inicial, drive (`C:`) ou `..`.
- Hashes SHA-256 em 64 hex minúsculos.
- `created_at` em ISO-8601 UTC (`Z` ou `+00:00`).

## Regras de segurança
- Leia apenas os arquivos listados no ContextPack e confira se continuam dentro de `workspace_root`.
- Não espere credenciais no ambiente: o core repassa só uma [allowlist de variáveis](security.md#ambiente-do-provider) e remove nomes com cara de credencial.
- Não dependa do cwd. Em `execute` ele é o diretório de trabalho do run (`.forge/runs/<id>/work`), e efeitos colaterais devem ficar ali. Em `describe` e `health` é um diretório temporário apagado depois da chamada. O cwd não é sandbox.
- Não deixe processos em segundo plano: em timeout o core encerra a árvore inteira do provider.
- O `producer` das responses e do resultado deve ser o do provider (id e versão). O core rejeita (`FORGE-PROTO-PRODUCER`) um valor diferente no envelope de `describe` e de `health` e no `ExecutionResult.producer`.

## Registro e trust
Registre o provider no `providers.toml` do **usuário** para receber trust (`trusted`/`local`). Entradas em `.forge/config/providers.toml` do projeto entram sempre como `unverified` (um `trust` maior é rebaixado com aviso) e só rodam com `--allow-unverified`. O que cada nível permite está em [security.md](security.md#níveis-de-trust). Veja o [README](../README.md#registrar-um-provider).

Argumentos relativos de `argv` são resolvidos contra o diretório do `providers.toml`, não contra o cwd. Um argumento relativo com separador (`/` ou `\`) que não seja um arquivo existente é erro de configuração (exit 2). Detalhes em [ADR 0013](adr/0013-provider-identity.md).

## Certificação
Adicione o argv do provider em `PROVIDER_ARGVS` de `tests/test_conformance.py` e rode `python -m pytest tests/test_conformance.py`.
