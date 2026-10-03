# theforge-sparkforge-adapter

Provider [Forge Protocol v1](../../docs/protocol.md) que expõe o Spark Forge (`sparkforge-aws`) ao The Forge. Stdlib-only, Python ≥ 3.10, sem dependências declaradas e sem `import theforge`: fala o protocolo só por JSON (stdin/stdout).

- id do provider: `spark-forge`
- versão: `0.1.0`
- especialista suportado: `sparkforge-aws >=0.5.0,<0.6.0`

> Estado: esqueleto instalável. Toda op (`describe`, `health`, `execute`) responde `refused` com exit 0 até o shell comum e a integração com o Spark Forge entrarem.

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
