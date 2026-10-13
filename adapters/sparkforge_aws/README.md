# theforge-sparkforge-aws-adapter

Provider [Forge Protocol v1](../../docs/protocol.md) que expõe o Spark Forge AWS (`sparkforge-aws`) ao The Forge. Stdlib-only, Python ≥ 3.10, sem dependências declaradas e sem `import theforge`: fala o protocolo só por JSON (stdin/stdout).

- id do provider: `spark-forge-aws`
- versão: `0.2.0`
- especialista suportado: `sparkforge-aws >=0.5.0,<0.6.0`

> Estado: `describe`, `health` e `execute` implementados, ao vivo e em replay. Decisão e contenção no [ADR 0014](../../docs/adr/0014-provider-adapter-location.md); catálogo de capabilities no [ADR 0017](../../docs/adr/0017-capability-taxonomy.md) e em [capabilities.md](../../docs/capabilities.md); guia completo em [real-providers.md](../../docs/real-providers.md).

`describe` não importa a superfície de tools do Spark Forge AWS: confere só que `sparkforge` é importável (senão `refused` `SPARKFORGE_AWS-ADAPTER-UNAVAILABLE` com o motivo) e deriva o manifest da tabela de capabilities (`catalog.py`) cruzada com o snapshot gravado (`native_catalog.json`). Só são declaradas ações de tools `readOnlyHint = true`, `openWorldHint = false` e com argumentos obrigatórios preenchíveis a partir de arquivos do workspace; o resto vai para `limitations` com o motivo. O manifest declara `context_revalidation = "hash"`. Snapshot ausente ou corrompido → `error` `SPARKFORGE-ADAPTER-SNAPSHOT-INVALID` (reinstale o adapter).

`health` faz só checagens locais, sem rede e sem credenciais (nunca chama o `doctor` nativo): Python ≥ 3.10, `sparkforge.adapters.tools` encontrável, snapshot legível e versão dentro de `SUPPORTED_SPECIALIST` (fora da janela → `degraded` com a versão encontrada e a janela).

`execute` copia para `<cwd>/stage/` só os arquivos do ContextPack com sha256 conferido e roda a tool num processo filho (`python -m theforge_sparkforge_aws.native_call`, mesmo interpretador, cwd no diretório do execute, `detail_level = "normal"`), encadeando `sparkforge_judge` quando há facts. Erro nativo tipado ou exit 2 → `refused` com `SPARKFORGE-<código>`; senão `error`. Falhas do adapter: `SPARKFORGE-ADAPTER-NATIVE-FAILED` (filho com exit ≠ 0 ou stdout truncado), `SPARKFORGE-ADAPTER-NATIVE-INVALID` (saída fora do formato), `ADAPTER-NATIVE-TIMEOUT`, `ADAPTER-OUTPUT-TOO-LARGE`; a lista completa está em [protocol.md](../../docs/protocol.md#códigos-dos-adapters-reais). No fim de todo execute, o cwd é reduzido aos artifacts declarados: `.sparkforge/` e `traces.db` nunca ficam no workspace.

Regravar o snapshot (no interpretador do Spark Forge AWS; saída determinística):

```bash
<python-do-spark-forge-aws> -m theforge_sparkforge_aws.record [--environment <dir-de-replay>]
```

Replay (`--replay <dir>`, antes da op): o `environment.json` do diretório (`{python, specialist_version}`) substitui a checagem de importabilidade, `health.json` as sondas do health e `<capability>.<action>.json` (ou `.error.json`) a saída nativa; ação sem gravação → `ADAPTER-REPLAY-MISSING`. Cenário saudável em `tests/fixtures/native/sparkforge_aws/default/`; cada outro desfecho em `tests/fixtures/native/sparkforge_aws/scenarios/<nome>/`.

## Instalação

Instale o adapter **no mesmo interpretador do Spark Forge AWS** (o adapter e o processo filho de execute usam esse interpretador; o core nunca importa nenhum dos dois):

```bash
<python-do-spark-forge-aws> -m pip install sparkforge-aws   # >=0.5,<0.6
<python-do-spark-forge-aws> -m pip install ./adapters/sparkforge_aws
```

Desenvolvimento neste repositório (editável, junto do core):

```bash
python -m pip install -e .[dev] -e ./adapters/sparkforge_aws -e ./adapters/apiforge
```

Verificação rápida:

```bash
echo '{"protocol":"forge/v1","kind":"Request","op":"describe","request_id":"r1","payload":{}}' \
  | <python-do-spark-forge-aws> -m theforge_sparkforge_aws describe
```

## Registro

Registre no `providers.toml` **do usuário** (único que concede trust; ver o [README](../../README.md#registrar-um-provider)):

```toml
[[providers]]
id = "spark-forge-aws"
argv = ["/caminho/para/python-do-spark-forge-aws", "-m", "theforge_sparkforge_aws"]
trust = "local"   # ou "trusted"
```

Depois rode `theforge registry refresh`.
