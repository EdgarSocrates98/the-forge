# theforge-sparkforge-adapter

Provider [Forge Protocol v1](../../docs/protocol.md) que expõe o Spark Forge (`sparkforge-aws`) ao The Forge. Stdlib-only, Python ≥ 3.10, sem dependências declaradas e sem `import theforge`: fala o protocolo só por JSON (stdin/stdout).

- id do provider: `spark-forge`
- versão: `0.1.0`
- especialista suportado: `sparkforge-aws >=0.5.0,<0.6.0`

> Estado: `describe` implementado; `health` e `execute` ainda respondem `refused` (exit 0).

`describe` não importa a superfície de tools do Spark Forge: confere só que `sparkforge` é importável (senão `refused` `SPARKFORGE-ADAPTER-UNAVAILABLE` com o motivo) e deriva o manifest da tabela de capabilities (`catalog.py`) cruzada com o snapshot gravado (`native_catalog.json`). Só são declaradas ações de tools `readOnlyHint = true`, `openWorldHint = false` e com argumentos obrigatórios preenchíveis a partir de arquivos do workspace; o resto vai para `limitations` com o motivo. O manifest declara `context_revalidation = "hash"`. Snapshot ausente ou corrompido → `error` `SPARKFORGE-ADAPTER-SNAPSHOT-INVALID` (reinstale o adapter).

Regravar o snapshot (no interpretador do Spark Forge; saída determinística):

```bash
<python-do-spark-forge> -m theforge_sparkforge.record [--environment <dir-de-replay>]
```

Replay (`--replay <dir>`, antes da op): o `environment.json` do diretório (`{python, specialist_version}`) substitui a checagem de importabilidade. Cenário saudável em `tests/fixtures/native/sparkforge/default/`; cada outro desfecho em `tests/fixtures/native/sparkforge/scenarios/<nome>/`.

## Instalação

Instale o adapter **no mesmo interpretador do Spark Forge** (o adapter importa o especialista em processo, nunca o core):

```bash
<python-do-spark-forge> -m pip install sparkforge-aws   # >=0.5,<0.6
<python-do-spark-forge> -m pip install ./adapters/sparkforge
```

Desenvolvimento neste repositório (editável, junto do core):

```bash
python -m pip install -e .[dev] -e ./adapters/sparkforge -e ./adapters/apiforge
```

Verificação rápida:

```bash
echo '{"protocol":"forge/v1","kind":"Request","op":"describe","request_id":"r1","payload":{}}' \
  | <python-do-spark-forge> -m theforge_sparkforge describe
```

## Registro

Registre no `providers.toml` **do usuário** (único que concede trust; ver o [README](../../README.md#registrar-um-provider)):

```toml
[[providers]]
id = "spark-forge"
argv = ["/caminho/para/python-do-spark-forge", "-m", "theforge_sparkforge"]
trust = "local"   # ou "trusted"
```

Depois rode `theforge registry refresh`.
