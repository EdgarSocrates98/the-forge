# theforge-apiforge-adapter

Provider [Forge Protocol v1](../../docs/protocol.md) que expõe o API Forge (`apiforge`) ao The Forge. Stdlib-only, Python ≥ 3.10, sem dependências declaradas e sem `import theforge`: fala o protocolo só por JSON (stdin/stdout).

- id do provider: `api-forge`
- versão: `0.1.0`
- especialista suportado: `apiforge >=0.1.0,<0.2.0` (exige Python 3.12)

> Estado: esqueleto instalável. Toda op (`describe`, `health`, `execute`) responde `refused` com exit 0 até o shell comum e a integração com o API Forge entrarem.

## Instalação

Instale o adapter **no mesmo interpretador Python 3.12 do API Forge**:

```bash
<python-3.12-do-api-forge> -m pip install apiforge   # >=0.1,<0.2
<python-3.12-do-api-forge> -m pip install ./adapters/apiforge
```

Desenvolvimento neste repositório (editável, junto do core):

```bash
python -m pip install -e .[dev] -e ./adapters/sparkforge -e ./adapters/apiforge
```

Verificação rápida:

```bash
echo '{"protocol":"forge/v1","kind":"Request","op":"describe","request_id":"r1","payload":{}}' \
  | <python-3.12-do-api-forge> -m theforge_apiforge describe
```

## Registro

Registre no `providers.toml` **do usuário** (único que concede trust; ver o [README](../../README.md#registrar-um-provider)):

```toml
[[providers]]
id = "api-forge"
argv = ["/caminho/para/python-3.12-do-api-forge", "-m", "theforge_apiforge"]
trust = "local"   # ou "trusted"
```

Depois rode `theforge registry refresh`.
