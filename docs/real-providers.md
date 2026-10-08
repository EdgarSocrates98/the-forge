# Providers reais: Spark Forge AWS, API Forge e os Doctors

The Forge fala com os especialistas através de adapters Forge Protocol v1 instalados **no interpretador de cada especialista**, nunca no interpretador do core: Spark Forge AWS (`sparkforge-aws`), API Forge (`apiforge`) e, desde o ciclo 3.1, os observadores determinísticos Forge Doctor Data (`forge-doctor-data`) e Forge Doctor API (`forge-doctor-api`). O porquê está no [ADR 0014](adr/0014-provider-adapter-location.md).

| | Spark Forge AWS | API Forge | Doctor Data | Doctor API |
|---|---|---|---|---|
| Distribuição do adapter | `theforge-sparkforge-aws-adapter` (`adapters/sparkforge_aws`) | `theforge-apiforge-adapter` (`adapters/apiforge`) | `theforge-doctordata-adapter` (`adapters/doctordata`) | `theforge-doctorapi-adapter` (`adapters/doctorapi`) |
| Módulo | `theforge_sparkforge_aws` | `theforge_apiforge` | `theforge_doctordata` | `theforge_doctorapi` |
| id do provider | `spark-forge-aws` | `api-forge` | `forge-doctor-data` | `forge-doctor-api` |
| Especialista suportado | `sparkforge-aws >=0.5.0,<0.6.0` | `apiforge >=0.1.0,<0.2.0` | `forge-doctor-data >=1.0.0rc1,<2.0.0` | `forge-doctor-api >=0.2.0,<0.3.0` |
| Interpretador | Python ≥ 3.10 (o CI usa 3.11) | Python 3.12 (exigido pelo API Forge) | Python ≥ 3.11 | Python ≥ 3.11 |
| Seam nativo | `sparkforge_aws.adapters.tools` (`sparkforge.*` antes do rename do pacote; resolvido por `native_pkg`) | `apiforge` CLI pública | `accept_request` + `check_conformance` (`forge-contracts/1`) | `DoctorBoundary` (spec 070) + strict parse |

Os adapters são stdlib-only, sem dependências declaradas, e não importam `theforge`. Os Doctors **não** rodam subprocesso nem rede no especialista: o adapter chama só as seams públicas num processo filho (`python -m theforge_doctordata.bridge` / `theforge_doctorapi.bridge`) e traduz o documento `forge-contracts/1`/`ApiHandoffBundle` para o Evidence Bus. Os caminhos abaixo são placeholders: `<spark-python>`, `<api-python>`, `<dd-python>` e `<da-python>` são o executável Python de cada venv (`<venv>/bin/python` no POSIX, `<venv>\Scripts\python.exe` no Windows), e `<the-forge>` é um checkout deste repositório.

## Instalação

### Spark Forge AWS (venv Python 3.11)

```bash
python3.11 -m venv <spark-venv>
<spark-python> -m pip install --upgrade pip
<spark-python> -m pip install "sparkforge-aws>=0.5,<0.6"      # ou: <checkout-spark-forge-aws>
<spark-python> -m pip install <the-forge>/adapters/sparkforge_aws
<spark-python> -c "import sparkforge_aws.adapters.tools, theforge_sparkforge_aws"   # deve sair 0
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

A prova cross-forge (`test_cross_forge_real.py`) exige a entrada `--upstream` do
`api.analyze` — `apiforge/upstream-facts/v1`, estável na `main` do api-forge desde
o PR #34 (`1745f87`; endurecida no ciclo 3.1 com namespaces `upstream:`/`upstream.`
e a recusa `AF-UPSTREAM-FORBIDDEN` de chaves imperativas). Com um `apiforge` sem
ela o adapter degrada com a limitação de consumo ausente (correto como
comportamento) e a prova falha: o teste real precisa da main pós-#34 (ou de
`apiforge>=0.1` publicado com o intake), também no workflow (`api_forge_ref`).

O adapter roda em Python ≥ 3.10. Num interpretador que não é 3.12, porém, `describe` recusa com o motivo e `health` responde `unavailable` (ver [Troubleshooting](#troubleshooting)).

### Forge Doctor Data (venv Python ≥ 3.11)

```bash
python3.11 -m venv <dd-venv>
<dd-python> -m pip install --upgrade pip
<dd-python> -m pip install "forge-doctor-data>=1.0.0rc1,<2.0.0"   # ou: <checkout-forge-doctor-data>
<dd-python> -m pip install <the-forge>/adapters/doctordata
<dd-python> -c "import forge_doctor_data, theforge_doctordata"    # deve sair 0
```

### Forge Doctor API (venv Python ≥ 3.11)

```bash
python3.11 -m venv <da-venv>
<da-python> -m pip install --upgrade pip
<da-python> -m pip install "forge-doctor-api>=0.2.0,<0.3.0"       # ou: <checkout-forge-doctor-api>
<da-python> -m pip install <the-forge>/adapters/doctorapi
<da-python> -c "import forge_doctor_api, theforge_doctorapi"      # deve sair 0
```

O `api.verify` do Doctor API exige a main pós-PR forge-doctor-api#13 (`035b635`): antes dele,
`ApiHandoffBundle.from_dict` falhava com `NameError: DeltaContext` porque a anotação só era
importada sob `TYPE_CHECKING` e `Model.from_dict` resolve hints em runtime.

### Desenvolvimento neste repositório

A suíte offline usa os adapters em modo replay, sem os especialistas:

```bash
python -m pip install -e .[dev] -e ./adapters/sparkforge_aws -e ./adapters/apiforge \
  -e ./adapters/doctordata -e ./adapters/doctorapi
```

### Verificação rápida

```bash
echo '{"protocol":"forge/v1","kind":"Request","op":"describe","request_id":"r1","payload":{}}' \
  | <spark-python> -m theforge_sparkforge_aws describe
echo '{"protocol":"forge/v1","kind":"Request","op":"health","request_id":"r2","payload":{}}' \
  | <api-python> -m theforge_apiforge health
echo '{"protocol":"forge/v1","kind":"Request","op":"describe","request_id":"r3","payload":{}}' \
  | <dd-python> -m theforge_doctordata describe
echo '{"protocol":"forge/v1","kind":"Request","op":"health","request_id":"r4","payload":{}}' \
  | <da-python> -m theforge_doctorapi health
```

A resposta sai sempre com exit 0 e um envelope `Response`. `health` traz os checks (`{name, ok, detail}`) com o motivo de cada estado.

## Registro

Registre os dois no `providers.toml` **do usuário**, que é o único que concede trust (local do arquivo no [README](../README.md#registrar-um-provider)):

```toml
[[providers]]
id = "spark-forge-aws"
argv = ["<spark-python>", "-m", "theforge_sparkforge_aws"]
trust = "local"   # ou "trusted"

[[providers]]
id = "api-forge"
argv = ["<api-python>", "-m", "theforge_apiforge"]
trust = "local"   # ou "trusted"

[[providers]]
id = "forge-doctor-data"
argv = ["<dd-python>", "-m", "theforge_doctordata"]
trust = "local"

[[providers]]
id = "forge-doctor-api"
argv = ["<da-python>", "-m", "theforge_doctorapi"]
trust = "local"
```

Use o caminho absoluto do interpretador do venv: o core executa esse `argv` sem shell. Depois rode:

```bash
theforge registry refresh
theforge registry show spark-forge-aws
theforge providers health
```

Só capabilities read-only e offline são declaradas. Tools que pedem rede, credenciais AWS ou escrita local, e capabilities `unsupported` ou de mutação do API Forge, aparecem em `limitations` do manifest com o motivo e nunca são executáveis. O catálogo e as exclusões estão em [capabilities.md](capabilities.md).

### O que acontece num execute

- O adapter copia para `.forge/runs/<id>/work/stage/` só os arquivos do `ContextPack` com sha256 conferido. O especialista lê essas cópias, com cwd em `work/`.
- O estado nativo (`.sparkforge/`, `traces.db`, `.apiforge/`, cache de caso) fica em `work/` e é apagado no fim. Sobram só os artifacts declarados: a saída nativa completa em `native/full-output.json` quando o resultado passa de 4 MiB, e os arquivos de caso do API Forge.
- `work/` **não passa por `security.redact`**: o que sobra ali foi escrito pelo provider e pode conter trechos do código analisado. Trate o diretório com a mesma sensibilidade do workspace e não o publique ([ADR 0014](adr/0014-provider-adapter-location.md#segurança-e-contenção)).
- O Spark Forge AWS roda cada ação num processo filho (`python -m theforge_sparkforge_aws.native_call`) com `detail_level = "normal"` e `limit = 200`, encadeando `sparkforge_judge` quando há facts. O API Forge roda a CLI pública com `APIFORGE_CACHE=off`. No `change-control run`, o cwd é a raiz do workspace copiado, porque o bundle cita `contract`/`project` relativos. Os Doctors rodam a seam pública num processo filho (`theforge_doctordata.bridge` / `theforge_doctorapi.bridge`, com `PYTHONIOENCODING=utf-8`) sobre a árvore copiada em `stage/` e declaram o documento nativo como artifact `native/handoff.json`.

## Níveis de "real"

"Prova real" é ambíguo sem o nível. O ciclo 3.1 fixa três termos, usados nas docs, nos relatórios e na saída dos benchmarks:

| Nível | O que executa | O que prova | O que não prova |
|---|---|---|---|
| `protocol-real` | provider *fixture* (`tests/fixtures/providers/*`) num subprocesso real, com envelopes Forge Protocol v1 reais | roteamento, envelopes, registry, planos, recibos e hash chain ponta a ponta | nada do especialista — a lógica é canned |
| `specialist-replay` | adapter real num subprocesso real, respondendo gravações (`--replay <cenário>`) do especialista | todo o caminho do adapter (describe/execute/health, staging, tradução de evidência, handoff, artifacts) com determinismo offline | o especialista não é importado: sem comportamento vivo, sem custo nativo |
| `specialist-real` | o pacote do especialista instalado (`sparkforge-aws`, `apiforge`, `forge-doctor-data`, `forge-doctor-api`), via adapter no venv dele | integração viva completa, inclusive consumo real de handoff e versões | nada é simulado — exige os venvs da [conformance](#contrato-de-ambiente-da-conformance-de-integração) |

Regras de uso: a suíte offline mistura `protocol-real` (fixtures) e `specialist-replay` (gravações); os testes marcados `real_provider` são `specialist-real` e nunca rodam sem as variáveis de ambiente. Um resultado `specialist-replay` nunca é apresentado como `specialist-real`; quando a afirmação precisa do especialista vivo, o teste pula com motivo explícito ou falha sob `THEFORGE_REAL_PROVIDERS_REQUIRED=1`/`THEFORGE_ECOSYSTEM_REQUIRED=1` — nunca um skip silencioso. O benchmark de economia (`scripts/bench/run_context_economy.py`) declara `provider_mode` no relatório exatamente por isso: hoje é `specialist-replay`.

### Taxonomia de testes (mock taxonomy)

Cada arquivo de teste declara suas categorias em `tests/conftest.py::FILE_MARKERS`
(coleção falha sem a declaração). A taxonomia mapeia para os tiers de prova:

| categoria (marker) | tier de prova | o que cobre |
|---|---|---|
| `unit` | — | lógica pura em processo, sem subprocesso nem filesystem de workspace |
| `contract` | — | forma de contratos/schemas/protocolo (validação, roundtrip, bounds) |
| `integration` | `protocol-real` + `specialist-replay` | múltiplos componentes: providers em subprocesso (fixtures) ou adapters em `--replay`, workspaces em disco |
| `e2e` | `protocol-real` | CLI real ponta a ponta num subprocesso |
| `security` | — | inputs hostis, segredos, limites de confiança (cruza com unit/integration) |
| `real_provider` | `specialist-real` | Forges reais vivos, env-gated, fora da suíte offline |
| `slow` | — | builds de pacote / gate de instalação fresh |

Um teste `integration` sobre adapters em replay **não** é prova de
especialista real — a evidência diz exatamente qual tier produziu o resultado.
"Remote blocked" não é um marker: é uma propriedade do design (sem transporte),
exercida pelos cenários B07/B13/B14 e pela suíte `test_remote*`.

## Contrato de ambiente da conformance de integração

Os testes `real_provider` (`python -m pytest -m real_provider`) rodam contra os Forges reais. Eles ficam fora da suíte offline padrão e são controlados por três variáveis:

| Variável | Valor | Efeito |
|---|---|---|
| `THEFORGE_REAL_SPARKFORGE_AWS_PYTHON` | caminho absoluto de um interpretador com `sparkforge-aws` e `theforge-sparkforge-aws-adapter` | habilita a integração do Spark Forge AWS |
| `THEFORGE_REAL_APIFORGE_PYTHON` | caminho absoluto de um interpretador 3.12 com `apiforge` e `theforge-apiforge-adapter` | habilita a integração do API Forge |
| `THEFORGE_REAL_DOCTORDATA_PYTHON` | caminho absoluto de um interpretador ≥ 3.11 com `forge-doctor-data` e `theforge-doctordata-adapter` | habilita a integração do Doctor Data |
| `THEFORGE_REAL_DOCTORAPI_PYTHON` | caminho absoluto de um interpretador ≥ 3.11 com `forge-doctor-api` e `theforge-doctorapi-adapter` | habilita a integração do Doctor API |
| `THEFORGE_REAL_PROVIDERS_REQUIRED` | `1` | pré-requisito ausente vira falha em vez de skip |
| `THEFORGE_ECOSYSTEM_REQUIRED` | `1` | alias equivalente no nível do ecossistema (mesma obrigação) |

- Só o harness de teste lê essas variáveis, para montar o `argv` do `providers.toml` de usuário isolado de cada teste. Elas nunca chegam ao ambiente do provider, porque a allowlist de ambiente do core não muda.
- Os pré-requisitos de cada Forge são verificados nesta ordem, cada um com motivo explícito: a variável está definida; o valor é um caminho absoluto de um interpretador (`python`, `python3` ou `python3.x`, com `.exe` opcional) e o arquivo existe; e `<python> -c "import <adapter>, <especialista>"` sai 0 em até 60 s. Exemplo de motivo: `THEFORGE_REAL_APIFORGE_PYTHON not set (API Forge needs Python 3.12; see docs/real-providers.md)`.
- Sem `THEFORGE_REAL_PROVIDERS_REQUIRED=1`, um pré-requisito ausente **pula** a integração daquele Forge com o motivo, e a suíte não falha. Com a variável, o mesmo caso **falha**.
- No CI, o workflow agendado `ecosystem-real.yml` cria um venv próprio por especialista — 3.11 (Spark Forge AWS e os dois Doctors) e 3.12 (API Forge) — a partir dos irmãos em `siblings/` e exporta as quatro variáveis, com `THEFORGE_REAL_PROVIDERS_REQUIRED=1`. Uma seleção vazia é regressão. O workflow não roda em pull requests e nunca bloqueia merge.
- `provider-surface-drift.yml` (semanal/`workflow_dispatch`) roda `python -m theforge_<adapter>.record --check` no venv de cada especialista contra a main dele: classifica `surface drift: none`, `additive` (ferramenta/seam/capability nova ou só bump de versão — exit 0, reportado no log) ou `breaking` (item gravado removido/alterado, request kind removido, versão de contrato movida — exit 1, job vermelho). O snapshot nunca é re-gravado pelo CI.
- `release-compat.yml` (semanal/`workflow_dispatch`) instala a main de cada especialista no seu interpretador e roda `theforge provider check -- <venv>/bin/python -m theforge_<adapter>` — conformidade de protocolo independente de número de versão.

Localmente:

```bash
export THEFORGE_REAL_SPARKFORGE_AWS_PYTHON=<spark-python>
export THEFORGE_REAL_APIFORGE_PYTHON=<api-python>
export THEFORGE_REAL_DOCTORDATA_PYTHON=<dd-python>
export THEFORGE_REAL_DOCTORAPI_PYTHON=<da-python>
python -m pytest -m real_provider
```

No PowerShell: `$env:THEFORGE_REAL_SPARKFORGE_AWS_PYTHON = "<spark-python>"`.

A integração cobre, por Forge, `describe` (manifest `ready` e snapshot igual à superfície viva), `health`, `execute` de uma capability sobre `tests/fixtures/workspaces/{spark,api,data/shop,cross/orders-api}/`, provider ausente e version skew (`--assume-specialist-version 9.9.9`).

### Prova cross-forge (Spark Forge AWS → API Forge)
`tests/test_cross_forge_real.py` (marker `real_provider`, mesmo contrato de ambiente) registra os dois adapters e roda `theforge plan "Projete um pipeline Spark que produza dados para uma API" --profile max --execute` no workspace de prova `tests/fixtures/workspaces/cross/` (montado em diretório temporário, um repositório git por subdiretório). Confere o plano `spark-forge-aws/pyspark.static-analysis` → `api-forge/api.analyze`, ao menos um item de handoff com origem no Spark Forge AWS e o status epistêmico original recebido pelo nó de API, a síntese com os dois runs e `theforge explain` do plano sem divergência ([ADR 0018](adr/0018-multi-provider-execution.md)).

### Prova hierárquica de quatro Forges (observe → engineer → verify)
No mesmo arquivo, `test_four_provider_proof_observe_then_engineer_then_verify` registra os quatro adapters reais e roda um plano `--profile max --execute` sobre o workspace cross completo (`data-pipeline` + `orders-api`). A prova não fixa ordem nenhuma: confere que toda aresta `produces→consumes` declarada é honrada pela ordem executada — `forge-doctor-data` antes de `spark-forge-aws` e `forge-doctor-api` antes de `api-forge`, com `capability-graph` como a regra citada na dependência, não o proxy de ordem de palavra-chave do intent. Para cada cadeia o teste verifica: o handoff do run do engineer contém itens com origem no Doctor (`origin.provider.id`), a evidência do engineer chega com `derived_from` apontando para provider/run/node/item do Doctor e `epistemic` verbatim; e a verificação independente do run do engineer passou, conduzida pelo Doctor da cadeia (`basis` cita `verifier:forge-doctor-data`/`forge-doctor-api`). A síntese cobre os quatro runs e `theforge explain` do plano sai sem divergência.

- `api-forge/api.analyze` declara `accepts_handoff` e consome os itens: o adapter traduz o handoff a `apiforge/upstream-facts/v1` (limitado a 32 itens/32 KiB, itens malformados pulados com limitação; no especialista o teto é 128 itens/256 KiB e o intake recusa chaves imperativas com `AF-UPSTREAM-FORBIDDEN`), grava `upstream-facts.json` no cwd nativo, passa `--upstream` ao `analyze` do especialista instalado e marca as evidências derivadas com `derived_from` apontando para o item e o run do Spark Forge AWS — o check `handoff-provenance` da verificação confere isso. O teste faz a prova A/B: o mesmo `execute` do nó, com e sem o `handoff` gravado, produz evidência observavelmente diferente. Quando o apiforge instalado não tem a entrada, o adapter responde `ok`/`partial` com a limitação de consumo ausente (e nunca inventa evidência upstream). `api.change-control` não declara e segue registrando `handoff-use-undeclared`.
- `spark-forge-aws/pyspark.static-analysis` (ação `pyspark`) declara `accepts_handoff` e `relations.consumes: ["data.diagnostic-evidence"]` — a aresta observe→engineer do ciclo 3.1. O adapter traduz o handoff ao documento upstream-facts do especialista instalado — o nome do schema acompanha o rename do pacote (`sparkforge_aws/upstream-facts/v1` em instalações pós-rename, `sparkforge/upstream-facts/v1` antes; `theforge_sparkforge_aws.handoff` emite o `UPSTREAM_SCHEMA` que o próprio intake instalado declara, nos mesmos tetos: 128 facts/256 KiB, ids `upstream:<sha256[:16]>` content-addressed, provenance `theforge/handoff`), grava `stage/upstream-facts.json`, passa `--file upstream=upstream-facts.json` ao `native_call` e audita o consumo pelo `output.filters_applied.upstream` — um Spark Forge AWS sem o intake ignora o argumento silenciosamente e a limitação `handoff delivered but not consumed` registra o gap (a entrada existe na `main` do especialista a partir do SDD `UPSTREAM_FACTS`; instalações `0.5.0` anteriores a ela seguem suportadas, sem intake). As facts estrangeiras voltam como evidência com `derived_from` apontando para provider/run/node/item do item de origem e `epistemic` verbatim — nunca `observed` (observado é o que o próprio especialista extraiu). Em replay nenhum arquivo de intake é escrito: a presença de `arguments.upstream` na gravação decide se o run gravado consumiu um handoff, e um handoff novo contra uma gravação sem intake vira limitação explícita.
- O equivalente offline (`tests/test_cross_forge_replay.py`) roda os adapters em `--replay` sobre os cenários `scenarios/cross/` de `tests/fixtures/native/sparkforge_aws/` e `tests/fixtures/native/apiforge/`, possuídos pela spec `cross-forge-foundation`; os cenários `default` não mudam. As duas gravações saem dos gravadores: a do Spark por `record_execute --handoff` (carrega `arguments.upstream` e as facts dobradas) e a do API Forge por `record_execute --handoff` sobre a main pós-PR #34 (`"provenance": "recorded"`, upstream facts embutidas). Em replay o adapter re-deriva as upstream facts do handoff **da requisição** (a tradução é determinística e vive no adapter, sem especialista): a provenance é sempre a do run atual, nunca a da gravação; sem handoff na requisição as facts upstream gravadas são descartadas. O teste real compara essas gravações com as saídas vivas (chaves dos arquivos de caso do API Forge e formato dos IDs nativos), como contraparte dos checks de drift da integração.
- `delta/v1` (fase 49): os dois Doctors declaram a feature no manifest; num run subsequente sobre o mesmo workspace o core envia `delta` no `ExecuteRequest` ([protocol.md — Delta](protocol.md#delta-deltav1)). O bridge do Doctor API resolve `baseline_ref` na store `.forge-doctor/snapshots` do workspace copiado em `stage/` e passa o `DoctorReport` de baseline ao `DoctorBoundary`, que emite o `DeltaContext` determinístico; o do Doctor Data grava um snapshot do relatório atual dentro do stage e o difere contra o anterior de `.forge-doctor-data/history` via `diff_snapshots`. Baseline não resolvido vira `delta.unresolved` explícito — nunca um delta fabricado — e a seção vira evidência `id="delta"` com contagens por tipo de mudança. Em replay a gravação responde o documento com ou sem `delta` igualmente; os cenários `scenarios/delta/` de cada Doctor cobrem o transporte e a tradução.

## Regravar snapshots e gravações de replay

Os arquivos gravados são comparados byte a byte. A escrita é canônica: chaves ordenadas, indentação de 2 espaços e LF final. O `.gitattributes` fixa LF para `adapters/**/native_*.json` e `tests/fixtures/native/**`. Uma gravação nunca pode conter caminho da máquina: o gravador de execute do Spark recusa gravar quando encontra um.

### Snapshot da superfície nativa (usado por `describe`)

```bash
# Spark: native_catalog.json (tools, anotações MCP, argumentos obrigatórios, versão de origem)
<spark-python> -m theforge_sparkforge_aws.record [--output <arquivo>] [--environment <dir-do-cenário>]

# API: native_matrix.json (matriz pública de capabilities)
<api-python> -m theforge_apiforge.record [--out <arquivo>] [--recorded-at <timestamp>]
                                       [--environment <dir-do-cenário>]

# Doctors: native_surface.json (seams públicas gravadas: módulo, callable, presença)
<dd-python> -m theforge_doctordata.record [--out <arquivo>] [--recorded-at <timestamp>] [--check]
<da-python> -m theforge_doctorapi.record [--out <arquivo>] [--recorded-at <timestamp>] [--check]
```

Sem `--output`/`--out`, o comando sobrescreve o snapshot empacotado no adapter. Rode a partir de um checkout com o adapter instalado em modo editável (`pip install -e`), senão a gravação vai para o `site-packages`. No Spark, `recorded_at` só muda quando a superfície muda. `--environment <dir>` também grava o `environment.json` (`{python, specialist_version}`) e o `health.json` (`{dispatcher, specialist_version}`) de um cenário de replay. Depois de regravar, rode a suíte offline: mudança de snapshot muda o manifest, e capabilities novas precisam constar em [capabilities.md](capabilities.md).

### Gravações de execute (replay)

Layout: cada diretório passado a `--replay <dir>` é um cenário completo. `tests/fixtures/native/<adapter>/default/` é o cenário saudável da conformance offline, e cada outro desfecho (erro nativo, especialista ausente, version skew, CLI ausente) fica em `tests/fixtures/native/<adapter>/scenarios/<nome>/`. Um cenário contém:

- `environment.json`: `{python, specialist_version}`. Substitui as checagens de interpretador e de importabilidade, e um `specialist_version` nulo simula o especialista ausente;
- `health.json`: no Spark, as sondas `{dispatcher, specialist_version}`; no API, `{cli}` (se `apiforge.cli` foi encontrado no interpretador gravado); nos Doctors, `{boundary}` (se o módulo da seam pública foi encontrado);
- `<capability>.<action>.json`: a saída nativa da ação;
- `<capability>.<action>.error.json`: a falha nativa da ação. Quando existem as duas gravações, a de erro prevalece.

Ação sem gravação responde `error` `ADAPTER-REPLAY-MISSING` com o nome do arquivo esperado: em replay o especialista nunca é chamado e nenhum resultado é inventado.

Spark: grave uma ação a partir de um workspace. O workspace nunca é tocado: ele é copiado sem links para um diretório temporário, e cada `--arg` é um caminho relativo a ele.

```bash
<spark-python> -m theforge_sparkforge_aws.record_execute \
  --workspace tests/fixtures/workspaces/spark \
  --capability pyspark.static-analysis --action pyspark \
  --arg path=jobs \
  --out tests/fixtures/native/sparkforge_aws/default
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

Dos arquivos de `tests/fixtures/native/apiforge/` resta `hand-built` apenas
`default/api.change-control.run.json`: a saída do verbo embute caminhos do diretório de
trabalho, e o gravador a recusa por conter caminho da máquina — a regravação destrava
quando o verbo portabilizar seus caminhos. `default/api.analyze.analyze.json`,
`scenarios/cross/api.analyze.analyze.json` e os `environment.json`/`health.json` dos dois
cenários já saem dos gravadores (`"provenance": "recorded"`). Arquivos `.json` são
reserializados (chaves ordenadas, indentação 2, LF final) para que os hashes do caso
continuem valendo.

## Troubleshooting

Os códigos `FORGE-*` desta tabela estão, com a família de cada um, na lista canônica [errors.md](errors.md); os códigos dos adapters, em [protocol.md](protocol.md#códigos-dos-adapters-reais).

| Sintoma | Causa | O que fazer |
|---|---|---|
| provider `unreachable`, `FORGE-PROTO-SPAWN` com o caminho | o `argv[0]` registrado não existe ou não é executável | corrija o caminho absoluto do interpretador no `providers.toml` e rode `theforge registry refresh` |
| provider `invalid` com `SPARKFORGE_AWS-ADAPTER-UNAVAILABLE` / `APIFORGE-ADAPTER-UNAVAILABLE` / `DOCTORDATA-ADAPTER-UNAVAILABLE` / `DOCTORAPI-ADAPTER-UNAVAILABLE` | o adapter roda, mas o especialista não é importável nesse interpretador (ou, no API, o interpretador não é 3.12; nos Doctors, menor que 3.11); o `describe` recusa com o motivo | instale o especialista no mesmo venv do adapter ou registre o interpretador certo |
| `ModuleNotFoundError: theforge_sparkforge_aws` / `theforge_apiforge` / `theforge_doctordata` / `theforge_doctorapi` no spawn | o adapter não foi instalado no interpretador registrado | `<python> -m pip install <the-forge>/adapters/<forge>` |
| Python 3.12 ausente | o API Forge exige 3.12. Sem ele, o `health` do API responde `unavailable` (`API Forge requires Python 3.12; this adapter runs on <x.y> at <python>`), e a integração pula com `THEFORGE_REAL_APIFORGE_PYTHON not set (API Forge needs Python 3.12; ...)` | instale um 3.12, crie o venv do API Forge e aponte a variável ou o `providers.toml` para ele |
| health `degraded` com `found <v>, supported <janela>` | version skew: a versão do especialista está fora de `SUPPORTED_SPECIALIST` do adapter (Spark `>=0.5.0,<0.6.0`, API `>=0.1.0,<0.2.0`, Doctor Data `>=1.0.0rc1,<2.0.0` — `rc` compara abaixo do release, Doctor API `>=0.2.0,<0.3.0`) | instale uma versão dentro da janela ou atualize o adapter para uma versão cuja linha da matriz em [versioning.md](versioning.md) cubra a versão instalada |
| health `unavailable` (Spark) | `sparkforge_aws.adapters.tools` (ou `sparkforge.adapters.tools` pré-rename) não é encontrável, o Python é menor que 3.10 ou o snapshot está ausente ou ilegível | reinstale `sparkforge-aws` e o adapter no mesmo venv |
| health `unavailable` (Doctors) com `boundary` falho | o módulo da seam pública (`forge_doctor_data.core.forger` / `forge_doctor_api.handoff.boundary`) não é encontrável — instalação quebrada ou versão fora da superfície gravada | reinstale o especialista no venv do adapter |
| health (API) `unavailable` com `apiforge.cli ... is not importable` | o health do API só faz checagens locais (Python 3.12, `apiforge` importável, versão na janela e `apiforge.cli` encontrado com `find_spec`, sem importar) e **não** roda o `apiforge doctor`: o doctor fica atrás do import completo da CLI (~440 módulos, 3 a 17 s medidos), acima do orçamento de 10 s do core, e suas sondas não cobrem nada de que o adapter dependa. Dependência quebrada da CLI aparece no `execute` (erro nativo) | reinstale o `apiforge` no venv; para diagnosticar a instalação, rode `<api-python> -m apiforge doctor` à mão |
| `theforge providers health` mostra só `degraded` | o detalhe fica nos checks do adapter | rode a op `health` direto no adapter ([Verificação rápida](#verificação-rápida)) para ler os checks |
| execute `error` `ADAPTER-NATIVE-TIMEOUT` | a chamada nativa passou de 85% do timeout de execute do perfil (`economy` 60 s, `balanced` 180 s, `max` 600 s); a árvore de processos nativa é encerrada | use `--profile balanced` ou `max`, ou reduza o contexto (`--target`) |
| `FORGE-PROTO-TIMEOUT` em `describe`/`health` | o core dá 10 s para cada um. `describe` não importa a superfície de tools (que leva ~6 s no Spark), e o `health` do API não roda o API Forge (não importa a CLI) | verifique se o interpretador registrado é o do venv, não um wrapper lento, e se o disco ou o antivírus não estão travando o import |
| execute `refused` com `AF-*` ou `SPARKFORGE-*` | recusa nativa preservada: o código, `field` e `unlock` do especialista vêm intactos (Spark: erro tipado ou exit 2 → `refused`, senão `error`; API: exit 2 → `refused`, exit 3 → `error`) | siga o `detail`/`unlock`; é uma resposta do especialista, não falha de transporte |
| execute `refused`/`error` com `FDD-*` / `FDA-*` | falha estruturada do bridge do Doctor: `*-REQUEST-INVALID` (exit 2) → `refused` com `field=request`; `*-NATIVE-FAILURE` → `error` | o `detail` traz tipo+mensagem da exceção nativa; inspecione a instalação do especialista |
| execute `partial` com `no input: expected <globs>` | nenhum arquivo do contexto casa com o que a ação precisa; o especialista não é chamado | inclua os arquivos certos com `--target` |
| limitação `context file '<p>' skipped: <motivo>` | o arquivo está fora da raiz, o hash diverge do `ContextPack` ou o item é um intervalo de linhas | refaça o run; itens com `lines` não são suportados nesta versão dos adapters |
| `partial` com `output truncated: ...` | o resultado passou de 4 MiB e a saída completa foi para o artifact `native/full-output.json` | leia o artifact em `.forge/runs/<id>/work/`; sem nenhum finding cabendo, o resultado é `error` `ADAPTER-OUTPUT-TOO-LARGE` |
| limitação `workdir cleanup incomplete: <path>` | a remoção do estado nativo falhou (caminho > 260 caracteres sem LongPathsEnabled no Windows, arquivo em uso) | apague o caminho à mão; ele não é redigido |
| `SPARKFORGE-ADAPTER-SNAPSHOT-INVALID` / `APIFORGE-ADAPTER-SNAPSHOT-INVALID` / `DOCTORDATA-ADAPTER-SNAPSHOT-INVALID` / `DOCTORAPI-ADAPTER-SNAPSHOT-INVALID` | o snapshot empacotado está ausente ou corrompido | reinstale o adapter ou regrave o snapshot |
| `SPARKFORGE-ADAPTER-NATIVE-FAILED` / `-NATIVE-INVALID`, `APIFORGE-ADAPTER-NATIVE-FAILURE` / `-NATIVE-INVALID` | o processo nativo saiu com erro sem uma mensagem reconhecível, ou a saída não tem o formato esperado | rode a mesma ação direto no especialista para ver a saída; pode ser drift de superfície (regrave o snapshot e confira a janela) |
| `ADAPTER-REPLAY-MISSING` / `ADAPTER-REPLAY-INVALID` | em replay, a gravação da ação não existe ou o `environment.json` é inválido | grave a ação no cenário ([Gravações de execute](#gravações-de-execute-replay)) |
| `.sparkforge/` ou `.apiforge/` no workspace do usuário | não deveria acontecer: o estado nativo fica em `.forge/runs/<id>/work/` | abra uma issue com o run id |
