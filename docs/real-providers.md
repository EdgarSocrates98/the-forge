# Providers reais: Spark Forge e API Forge

The Forge fala com o Spark Forge (`sparkforge-aws`) e o API Forge (`apiforge`) através de dois adapters, que são providers Forge Protocol v1 instalados **no interpretador de cada especialista**, nunca no interpretador do core. O porquê está no [ADR 0014](adr/0014-provider-adapter-location.md).

| | Spark Forge | API Forge |
|---|---|---|
| Distribuição do adapter | `theforge-sparkforge-adapter` (`adapters/sparkforge`) | `theforge-apiforge-adapter` (`adapters/apiforge`) |
| Módulo | `theforge_sparkforge` | `theforge_apiforge` |
| id do provider | `spark-forge` | `api-forge` |
| Especialista suportado | `sparkforge-aws >=0.5.0,<0.6.0` | `apiforge >=0.1.0,<0.2.0` |
| Interpretador | Python ≥ 3.10 (o CI usa 3.11) | Python 3.12 (exigido pelo API Forge) |

Os adapters são stdlib-only, sem dependências declaradas, e não importam `theforge`. Os caminhos abaixo são placeholders: `<spark-python>` e `<api-python>` são o executável Python de cada venv (`<venv>/bin/python` no POSIX, `<venv>\Scripts\python.exe` no Windows), e `<the-forge>` é um checkout deste repositório.

## Instalação

### Spark Forge (venv Python 3.11)

```bash
python3.11 -m venv <spark-venv>
<spark-python> -m pip install --upgrade pip
<spark-python> -m pip install "sparkforge-aws>=0.5,<0.6"      # ou: <checkout-spark-forge-aws>
<spark-python> -m pip install <the-forge>/adapters/sparkforge
<spark-python> -c "import sparkforge.adapters.tools, theforge_sparkforge"   # deve sair 0
```

### API Forge (venv Python 3.12)

O API Forge só roda em Python 3.12. Instale um 3.12 (python.org, gerenciador do sistema ou `uv python install 3.12`) e crie um venv com ele:

```bash
python3.12 -m venv <api-venv>
<api-python> -m pip install --upgrade pip
<api-python> -m pip install "apiforge>=0.1,<0.2"              # ou: <checkout-api-forge>
<api-python> -m pip install <the-forge>/adapters/apiforge
<api-python> -c "import apiforge, theforge_apiforge"           # deve sair 0
```

O adapter roda em Python ≥ 3.10. Num interpretador que não é 3.12, porém, `describe` recusa com o motivo e `health` responde `unavailable` (ver [Troubleshooting](#troubleshooting)).

### Desenvolvimento neste repositório

A suíte offline usa os adapters em modo replay, sem os especialistas:

```bash
python -m pip install -e .[dev] -e ./adapters/sparkforge -e ./adapters/apiforge
```

### Verificação rápida

```bash
echo '{"protocol":"forge/v1","kind":"Request","op":"describe","request_id":"r1","payload":{}}' \
  | <spark-python> -m theforge_sparkforge describe
echo '{"protocol":"forge/v1","kind":"Request","op":"health","request_id":"r2","payload":{}}' \
  | <api-python> -m theforge_apiforge health
```

A resposta sai sempre com exit 0 e um envelope `Response`. `health` traz os checks (`{name, ok, detail}`) com o motivo de cada estado.

## Registro

Registre os dois no `providers.toml` **do usuário**, que é o único que concede trust (local do arquivo no [README](../README.md#registrar-um-provider)):

```toml
[[providers]]
id = "spark-forge"
argv = ["<spark-python>", "-m", "theforge_sparkforge"]
trust = "local"   # ou "trusted"

[[providers]]
id = "api-forge"
argv = ["<api-python>", "-m", "theforge_apiforge"]
trust = "local"   # ou "trusted"
```

Use o caminho absoluto do interpretador do venv: o core executa esse `argv` sem shell. Depois rode:

```bash
theforge registry refresh
theforge registry show spark-forge
theforge providers health
```

Só capabilities read-only e offline são declaradas. Tools que pedem rede, credenciais AWS ou escrita local, e capabilities `unsupported` ou de mutação do API Forge, aparecem em `limitations` do manifest com o motivo e nunca são executáveis. O catálogo e as exclusões estão em [capabilities.md](capabilities.md).

### O que acontece num execute

- O adapter copia para `.forge/runs/<id>/work/stage/` só os arquivos do `ContextPack` com sha256 conferido. O especialista lê essas cópias, com cwd em `work/`.
- O estado nativo (`.sparkforge/`, `traces.db`, `.apiforge/`, cache de caso) fica em `work/` e é apagado no fim. Sobram só os artifacts declarados: a saída nativa completa em `native/full-output.json` quando o resultado passa de 4 MiB, e os arquivos de caso do API Forge.
- `work/` **não passa por `security.redact`**: o que sobra ali foi escrito pelo provider e pode conter trechos do código analisado. Trate o diretório com a mesma sensibilidade do workspace e não o publique ([ADR 0014](adr/0014-provider-adapter-location.md#segurança-e-contenção)).
- O Spark Forge roda cada ação num processo filho (`python -m theforge_sparkforge.native_call`) com `detail_level = "normal"` e `limit = 200`, encadeando `sparkforge_judge` quando há facts. O API Forge roda a CLI pública com `APIFORGE_CACHE=off`. No `change-control run`, o cwd é a raiz do workspace copiado, porque o bundle cita `contract`/`project` relativos.

## Contrato de ambiente da conformance de integração

Os testes `real_provider` (`python -m pytest -m real_provider`) rodam contra os Forges reais. Eles ficam fora da suíte offline padrão e são controlados por três variáveis:

| Variável | Valor | Efeito |
|---|---|---|
| `THEFORGE_REAL_SPARKFORGE_PYTHON` | caminho absoluto de um interpretador com `sparkforge-aws` e `theforge-sparkforge-adapter` | habilita a integração do Spark Forge |
| `THEFORGE_REAL_APIFORGE_PYTHON` | caminho absoluto de um interpretador 3.12 com `apiforge` e `theforge-apiforge-adapter` | habilita a integração do API Forge |
| `THEFORGE_REAL_PROVIDERS_REQUIRED` | `1` | pré-requisito ausente vira falha em vez de skip |

- Só o harness de teste lê essas variáveis, para montar o `argv` do `providers.toml` de usuário isolado de cada teste. Elas nunca chegam ao ambiente do provider, porque a allowlist de ambiente do core não muda.
- Os pré-requisitos de cada Forge são verificados nesta ordem, cada um com motivo explícito: a variável está definida; o valor é um caminho absoluto de um interpretador (`python`, `python3` ou `python3.x`, com `.exe` opcional) e o arquivo existe; e `<python> -c "import <adapter>, <especialista>"` sai 0 em até 60 s. Exemplo de motivo: `THEFORGE_REAL_APIFORGE_PYTHON not set (API Forge needs Python 3.12; see docs/real-providers.md)`.
- Sem `THEFORGE_REAL_PROVIDERS_REQUIRED=1`, um pré-requisito ausente **pula** a integração daquele Forge com o motivo, e a suíte não falha. Com a variável, o mesmo caso **falha**.
- No CI, o workflow agendado `real-providers.yml` cria um venv 3.11 (Spark) e um 3.12 (API) a partir dos irmãos em `siblings/` e exporta as três variáveis, com `THEFORGE_REAL_PROVIDERS_REQUIRED=1`. Uma seleção vazia é regressão. O workflow não roda em pull requests e nunca bloqueia merge.

Localmente:

```bash
export THEFORGE_REAL_SPARKFORGE_PYTHON=<spark-python>
export THEFORGE_REAL_APIFORGE_PYTHON=<api-python>
python -m pytest -m real_provider
```

No PowerShell: `$env:THEFORGE_REAL_SPARKFORGE_PYTHON = "<spark-python>"`.

A integração cobre, por Forge, `describe` (manifest `ready` e snapshot igual à superfície viva), `health`, `execute` de uma capability sobre `tests/fixtures/workspaces/{spark,api}/`, provider ausente e version skew (`--assume-specialist-version 9.9.9`).

### Prova cross-forge (Spark Forge → API Forge)
`tests/test_cross_forge_real.py` (marker `real_provider`, mesmo contrato de ambiente) registra os dois adapters e roda `theforge plan "Projete um pipeline Spark que produza dados para uma API" --profile max --execute` no workspace de prova `tests/fixtures/workspaces/cross/` (montado em diretório temporário, um repositório git por subdiretório). Confere o plano `spark-forge/pyspark.static-analysis` → `api-forge/api.analyze`, ao menos um item de handoff com origem no Spark Forge e o status epistêmico original recebido pelo nó de API, a síntese com os dois runs e `theforge explain` do plano sem divergência ([ADR 0018](adr/0018-multi-provider-execution.md)).

- `api-forge/api.analyze` declara `accepts_handoff` e consome os itens: o adapter traduz o handoff a `apiforge/upstream-facts/v1` (limitado a 32 itens/64 KiB, itens malformados pulados com limitação), grava `upstream-facts.json` no cwd nativo, passa `--upstream` ao `analyze` do especialista instalado e marca as evidências derivadas com `derived_from` apontando para o item e o run do Spark Forge — o check `handoff-provenance` da verificação confere isso. O teste faz a prova A/B: o mesmo `execute` do nó, com e sem o `handoff` gravado, produz evidência observavelmente diferente. Quando o apiforge instalado não tem a entrada, o adapter responde `ok`/`partial` com a limitação de consumo ausente (e nunca inventa evidência upstream). `spark-forge` e `api.change-control` não declaram e seguem registrando `handoff-use-undeclared`.
- O equivalente offline (`tests/test_cross_forge_replay.py`) roda os adapters em `--replay` sobre os cenários `scenarios/cross/` de `tests/fixtures/native/sparkforge/` e `tests/fixtures/native/apiforge/`, possuídos pela spec `cross-forge-foundation`; os cenários `default` não mudam. A gravação do Spark vem do gravador; a do API Forge foi montada à mão a partir de um run real com `--upstream` e leva `"provenance": "hand-built"`. Em replay o adapter re-deriva as upstream facts do handoff **da requisição** (a tradução é determinística e vive no adapter, sem especialista): a provenance é sempre a do run atual, nunca a da gravação; sem handoff na requisição as facts upstream gravadas são descartadas. O teste real compara essas gravações com as saídas vivas (chaves dos arquivos de caso do API Forge e formato dos IDs nativos), como contraparte dos checks de drift da integração.

## Regravar snapshots e gravações de replay

Os arquivos gravados são comparados byte a byte. A escrita é canônica: chaves ordenadas, indentação de 2 espaços e LF final. O `.gitattributes` fixa LF para `adapters/**/native_*.json` e `tests/fixtures/native/**`. Uma gravação nunca pode conter caminho da máquina: o gravador de execute do Spark recusa gravar quando encontra um.

### Snapshot da superfície nativa (usado por `describe`)

```bash
# Spark: native_catalog.json (tools, anotações MCP, argumentos obrigatórios, versão de origem)
<spark-python> -m theforge_sparkforge.record [--output <arquivo>] [--environment <dir-do-cenário>]

# API: native_matrix.json (matriz pública de capabilities)
<api-python> -m theforge_apiforge.record [--out <arquivo>] [--recorded-at <timestamp>]
```

Sem `--output`/`--out`, o comando sobrescreve o snapshot empacotado no adapter. Rode a partir de um checkout com o adapter instalado em modo editável (`pip install -e`), senão a gravação vai para o `site-packages`. No Spark, `recorded_at` só muda quando a superfície muda. `--environment <dir>` também grava o `environment.json` (`{python, specialist_version}`) e o `health.json` (`{dispatcher, specialist_version}`) de um cenário de replay. Depois de regravar, rode a suíte offline: mudança de snapshot muda o manifest, e capabilities novas precisam constar em [capabilities.md](capabilities.md).

### Gravações de execute (replay)

Layout: cada diretório passado a `--replay <dir>` é um cenário completo. `tests/fixtures/native/<adapter>/default/` é o cenário saudável da conformance offline, e cada outro desfecho (erro nativo, especialista ausente, version skew, CLI ausente) fica em `tests/fixtures/native/<adapter>/scenarios/<nome>/`. Um cenário contém:

- `environment.json`: `{python, specialist_version}`. Substitui as checagens de interpretador e de importabilidade, e um `specialist_version` nulo simula o especialista ausente;
- `health.json`: no Spark, as sondas `{dispatcher, specialist_version}`; no API, `{cli}` (se `apiforge.cli` foi encontrado no interpretador gravado);
- `<capability>.<action>.json`: a saída nativa da ação;
- `<capability>.<action>.error.json`: a falha nativa da ação. Quando existem as duas gravações, a de erro prevalece.

Ação sem gravação responde `error` `ADAPTER-REPLAY-MISSING` com o nome do arquivo esperado: em replay o especialista nunca é chamado e nenhum resultado é inventado.

Spark: grave uma ação a partir de um workspace. O workspace nunca é tocado: ele é copiado sem links para um diretório temporário, e cada `--arg` é um caminho relativo a ele.

```bash
<spark-python> -m theforge_sparkforge.record_execute \
  --workspace tests/fixtures/workspaces/spark \
  --capability pyspark.static-analysis --action pyspark \
  --arg path=jobs \
  --out tests/fixtures/native/sparkforge/default
```

API: `theforge_apiforge.record_execute` grava uma ação a partir de um workspace, como o gravador do Spark. O workspace nunca é tocado: é copiado sem links para `stage/` num diretório temporário, cada `--arg` é `<input>=<caminho relativo ao workspace>` (para `api.analyze`, `contract` e `project`), e o verbo roda pela CLI pública com o mesmo argv que o adapter constrói. `--handoff <arquivo>` alimenta a entrada `--upstream` com um documento `theforge/Handoff/v1`, como o adapter faz ao vivo. A gravação sai como `{argv, case_dir, case_files, exit_code, native_cwd, stdout, provenance: "recorded", assembled_from}` em `<capability>.<action>.json` — ou `{exit_code, stderr}` em `<capability>.<action>.error.json` quando o verbo falha — e é recusada quando carregaria um caminho da máquina:

```bash
<api-python> -m theforge_apiforge.record_execute \
  --workspace tests/fixtures/workspaces/cross \
  --capability api.analyze --action analyze \
  --arg contract=orders-api/openapi.yaml --arg project=orders-api \
  [--handoff <handoff.json>] \
  --out tests/fixtures/native/apiforge/scenarios/cross
```

As gravações atuais de `tests/fixtures/native/apiforge/` ainda levam `"provenance": "hand-built"` (montadas a partir de runs reais, conferidas pelo teste cross) até a primeira regravação pelo gravador. Arquivos `.json` são reserializados (chaves ordenadas, indentação 2, LF final) para que os hashes do caso continuem valendo.

## Troubleshooting

Os códigos `FORGE-*` desta tabela estão, com a família de cada um, na lista canônica [errors.md](errors.md); os códigos dos adapters, em [protocol.md](protocol.md#códigos-dos-adapters-reais).

| Sintoma | Causa | O que fazer |
|---|---|---|
| provider `unreachable`, `FORGE-PROTO-SPAWN` com o caminho | o `argv[0]` registrado não existe ou não é executável | corrija o caminho absoluto do interpretador no `providers.toml` e rode `theforge registry refresh` |
| provider `invalid` com `SPARKFORGE-ADAPTER-UNAVAILABLE` / `APIFORGE-ADAPTER-UNAVAILABLE` | o adapter roda, mas o especialista não é importável nesse interpretador (ou, no API, o interpretador não é 3.12); o `describe` recusa com o motivo, por exemplo `apiforge is not importable with <python> (Python 3.11); install apiforge >=0.1.0,<0.2.0 in this interpreter` | instale o especialista no mesmo venv do adapter ou registre o interpretador certo |
| `ModuleNotFoundError: theforge_sparkforge` / `theforge_apiforge` no spawn | o adapter não foi instalado no interpretador registrado | `<python> -m pip install <the-forge>/adapters/<forge>` |
| Python 3.12 ausente | o API Forge exige 3.12. Sem ele, o `health` do API responde `unavailable` (`API Forge requires Python 3.12; this adapter runs on <x.y> at <python>`), e a integração pula com `THEFORGE_REAL_APIFORGE_PYTHON not set (API Forge needs Python 3.12; ...)` | instale um 3.12, crie o venv do API Forge e aponte a variável ou o `providers.toml` para ele |
| health `degraded` com `found <v>, supported <janela>` | version skew: a versão do especialista está fora de `SUPPORTED_SPECIALIST` do adapter (Spark `>=0.5.0,<0.6.0`, API `>=0.1.0,<0.2.0`) | instale uma versão dentro da janela ou atualize o adapter para uma versão cuja linha da matriz em [versioning.md](versioning.md) cubra a versão instalada |
| health `unavailable` (Spark) | `sparkforge.adapters.tools` não é encontrável, o Python é menor que 3.10 ou o snapshot está ausente ou ilegível | reinstale `sparkforge-aws` e o adapter no mesmo venv |
| health (API) `unavailable` com `apiforge.cli ... is not importable` | o health do API só faz checagens locais (Python 3.12, `apiforge` importável, versão na janela e `apiforge.cli` encontrado com `find_spec`, sem importar) e **não** roda o `apiforge doctor`: o doctor fica atrás do import completo da CLI (~440 módulos, 3 a 17 s medidos), acima do orçamento de 10 s do core, e suas sondas não cobrem nada de que o adapter dependa. Dependência quebrada da CLI aparece no `execute` (erro nativo) | reinstale o `apiforge` no venv; para diagnosticar a instalação, rode `<api-python> -m apiforge doctor` à mão |
| `theforge providers health` mostra só `degraded` | o detalhe fica nos checks do adapter | rode a op `health` direto no adapter ([Verificação rápida](#verificação-rápida)) para ler os checks |
| execute `error` `ADAPTER-NATIVE-TIMEOUT` | a chamada nativa passou de 85% do timeout de execute do perfil (`economy` 60 s, `balanced` 180 s, `max` 600 s); a árvore de processos nativa é encerrada | use `--profile balanced` ou `max`, ou reduza o contexto (`--target`) |
| `FORGE-PROTO-TIMEOUT` em `describe`/`health` | o core dá 10 s para cada um. `describe` não importa a superfície de tools (que leva ~6 s no Spark), e o `health` do API não roda o API Forge (não importa a CLI) | verifique se o interpretador registrado é o do venv, não um wrapper lento, e se o disco ou o antivírus não estão travando o import |
| execute `refused` com `AF-*` ou `SPARKFORGE-*` | recusa nativa preservada: o código, `field` e `unlock` do especialista vêm intactos (Spark: erro tipado ou exit 2 → `refused`, senão `error`; API: exit 2 → `refused`, exit 3 → `error`) | siga o `detail`/`unlock`; é uma resposta do especialista, não falha de transporte |
| execute `partial` com `no input: expected <globs>` | nenhum arquivo do contexto casa com o que a ação precisa; o especialista não é chamado | inclua os arquivos certos com `--target` |
| limitação `context file '<p>' skipped: <motivo>` | o arquivo está fora da raiz, o hash diverge do `ContextPack` ou o item é um intervalo de linhas | refaça o run; itens com `lines` não são suportados nesta versão dos adapters |
| `partial` com `output truncated: ...` | o resultado passou de 4 MiB e a saída completa foi para o artifact `native/full-output.json` | leia o artifact em `.forge/runs/<id>/work/`; sem nenhum finding cabendo, o resultado é `error` `ADAPTER-OUTPUT-TOO-LARGE` |
| limitação `workdir cleanup incomplete: <path>` | a remoção do estado nativo falhou (caminho > 260 caracteres sem LongPathsEnabled no Windows, arquivo em uso) | apague o caminho à mão; ele não é redigido |
| `SPARKFORGE-ADAPTER-SNAPSHOT-INVALID` / `APIFORGE-ADAPTER-SNAPSHOT-INVALID` | o snapshot empacotado está ausente ou corrompido | reinstale o adapter ou regrave o snapshot |
| `SPARKFORGE-ADAPTER-NATIVE-FAILED` / `-NATIVE-INVALID`, `APIFORGE-ADAPTER-NATIVE-FAILURE` / `-NATIVE-INVALID` | o processo nativo saiu com erro sem uma mensagem reconhecível, ou a saída não tem o formato esperado | rode a mesma ação direto no especialista para ver a saída; pode ser drift de superfície (regrave o snapshot e confira a janela) |
| `ADAPTER-REPLAY-MISSING` / `ADAPTER-REPLAY-INVALID` | em replay, a gravação da ação não existe ou o `environment.json` é inválido | grave a ação no cenário ([Gravações de execute](#gravações-de-execute-replay)) |
| `.sparkforge/` ou `.apiforge/` no workspace do usuário | não deveria acontecer: o estado nativo fica em `.forge/runs/<id>/work/` | abra uma issue com o run id |
