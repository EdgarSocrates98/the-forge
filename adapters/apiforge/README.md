# theforge-apiforge-adapter

Provider [Forge Protocol v1](../../docs/protocol.md) que expõe o API Forge (`apiforge`) ao The Forge. Stdlib-only, Python ≥ 3.10, sem dependências declaradas e sem `import theforge`: fala o protocolo só por JSON (stdin/stdout).

- id do provider: `api-forge`
- versão: `0.2.0`
- especialista suportado: `apiforge >=0.1.0,<0.2.0` (exige Python 3.12)

> Estado: `describe`, `health` e `execute` implementados, ao vivo e em replay. Decisão e contenção no [ADR 0014](../../docs/adr/0014-provider-adapter-location.md); catálogo de capabilities no [ADR 0017](../../docs/adr/0017-capability-taxonomy.md) e em [capabilities.md](../../docs/capabilities.md); guia completo em [real-providers.md](../../docs/real-providers.md).

`describe` exige Python 3.12 com `apiforge` importável (senão `refused` `APIFORGE-ADAPTER-UNAVAILABLE` com o motivo) e deriva o manifest da matriz pública gravada (`native_matrix.json`): só capabilities `supported`/`heuristic` e `read_only` são declaradas (`api.analyze`, `api.change-control`); o resto vai para `limitations` com o motivo. O manifest declara `context_revalidation = "hash"`. Snapshot ausente ou corrompido → `error` `APIFORGE-ADAPTER-SNAPSHOT-INVALID`.

`health` faz só checagens locais, sem rede e sem credenciais: Python 3.12, `apiforge` importável, versão dentro de `SUPPORTED_SPECIALIST` e `apiforge.cli` encontrado com `find_spec`, sem importar. Ele **não** roda o `apiforge doctor`, porque importar a CLI leva de 3 a 17 s, acima do orçamento de 10 s do core; uma dependência quebrada da CLI aparece no `execute`. Para diagnosticar a instalação, rode `<python-3.12-do-api-forge> -m apiforge doctor` à mão.

`execute` copia para `<cwd>/stage/` só os arquivos do ContextPack com sha256 conferido e roda a CLI pública com `APIFORGE_CACHE=off`: `analyze` com cwd no diretório do execute; `change-control run` com cwd na raiz do workspace copiado, porque o bundle cita `contract`/`project` relativos (caminho do bundle fora do workspace → `refused` `APIFORGE-ADAPTER-INPUT-OUTSIDE`). Erros `AF-*` passam intactos (exit 2 → `refused`; exit 3 ou `AF-CLI-INTERNAL` → `error`); sem linha `AF-*`, `APIFORGE-ADAPTER-NATIVE-FAILURE`; caso fora do formato, `APIFORGE-ADAPTER-NATIVE-INVALID`. Os arquivos do caso viram artifacts; no fim de todo execute, o cwd é reduzido a eles e `.apiforge/` nunca fica no workspace. Lista completa de códigos em [protocol.md](../../docs/protocol.md#códigos-dos-adapters-reais).

Replay (`--replay <dir>`, antes da op): `environment.json` (`{python, specialist_version}`), `health.json` (`{cli}`, mais `provenance`) e `<capability>.<action>.json` (ou `.error.json`) substituem o API Forge; ação sem gravação → `ADAPTER-REPLAY-MISSING`. Regravar o snapshot: `<python-3.12-do-api-forge> -m theforge_apiforge.record [--out <arquivo>]`.

## Instalação

Instale o adapter **no mesmo interpretador Python 3.12 do API Forge**:

```bash
<python-3.12-do-api-forge> -m pip install apiforge   # >=0.1,<0.2
<python-3.12-do-api-forge> -m pip install ./adapters/apiforge
```

Desenvolvimento neste repositório (editável, junto do core):

```bash
python -m pip install -e .[dev] -e ./adapters/sparkforge_aws -e ./adapters/apiforge
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
