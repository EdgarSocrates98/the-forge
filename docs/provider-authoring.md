# Escrevendo um provider

Um provider é qualquer executável que implementa o [Forge Protocol v1](protocol.md). A linguagem é livre.

## Mínimo
1. Ler `argv[-1]` como op e o request JSON do stdin.
2. `describe`: responder com o `ForgeManifest` (`id` igual ao id registrado; `ops` contendo `describe` e `health`).
3. `health`: responder `{"status":"ok","checks":[]}`.
4. `execute`: ler `payload.capability`, `payload.action` e `payload.context.files` (paths relativos a `payload.task.workspace_root`) e responder com um `ExecutionResult`.
5. Capability desconhecida → `status: "refused"` com `error.code` e, se fizer sentido, `unlock`.
6. Sempre exit 0 com uma response válida. Crash vira `provider_failure` no core.

Exemplo completo e standalone: `tests/fixtures/providers/fixture_forge.py`.

## Capabilities e sinais
- Formato do id: `domínio.assunto` (`^[a-z][a-z0-9-]*(\.[a-z][a-z0-9-]*)+$`).
- Os sinais (`keywords`, `file_globs`, `dependencies`) são a única fonte de conhecimento do router. Declare sinais específicos: o routing exige ≥ 2 tipos de sinal casados para ter confiança `high`.
- `operation_class` declara o efeito colateral: `read_only` … `destructive`.

## Regras de segurança
- Leia apenas os arquivos listados no ContextPack e confira se continuam dentro de `workspace_root`.
- Não espere credenciais no ambiente: o core repassa só uma allowlist de variáveis.
- O cwd é um diretório de trabalho do run (`.forge/runs/<id>/work`). Efeitos colaterais devem ficar ali.
- O `producer.id` das responses deve ser o id do provider; qualquer outro valor é rejeitado (`FORGE-PROTO-PRODUCER`).

## Registro e trust
Registre o provider no `providers.toml` do **usuário** para receber trust (`trusted`/`local`). Entradas em `.forge/config/providers.toml` do projeto entram sempre como `unverified` e só rodam com `--allow-unverified`. Veja o [README](../README.md#registrar-um-provider).

## Certificação
Adicione o argv do provider em `PROVIDER_ARGVS` de `tests/test_conformance.py` e rode `python -m pytest tests/test_conformance.py`.
