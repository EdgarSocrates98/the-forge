# Research & Design Decisions — real-provider-integration

## Summary
- **Feature**: `real-provider-integration` (Wave B do Cycle 2)
- **Discovery Scope**: Complex Integration (extensão do core + dois sistemas externos reais)
- **Key Findings**:
  - Nenhum dos dois Forges fala Forge Protocol; ambos emitem JSON em stdout e erro em texto em stderr com exit ≠ 0. Os dois gravam estado relativo ao cwd (Spark também relativo a `repo`), sem variável que redirecione: o cwd controlado pelo core + cópia de entrada (`stage/`) dentro dele resolve a contenção.
  - Spark Forge tem um dispatcher programático (`call_tool`) com 136 tools anotadas (read-only/escrita/open-world); API Forge tem uma matriz pública de 21 capabilities com `state`/`risk`, mas sem verbo de CLI por capability. As superfícies de origem são diferentes: o adapter Spark deriva capabilities de grupos de tools; o API deriva 1:1 da matriz, filtrada por um mapa de verbos offline.
  - O import do Spark Forge custa ~6 s a frio e o `doctor` nativo sonda a cadeia de credenciais AWS: describe/health precisam de snapshot da superfície e checagens sem import pesado.

## Research Log

### Core atual (pós Wave A, `main` em b1d9ec7)
- **Context**: o design precisa partir do código mergeado, não do plano da Wave A.
- **Sources Consulted**: `src/theforge/contracts/{manifest,types,codes,result,integrity,base}.py`, `src/theforge/registry/{registry,config,health,identity}.py`, `src/theforge/protocol/{transport,negotiate}.py`, `src/theforge/routing/router.py`, `src/theforge/forger/orchestrator.py`, `src/theforge/security/{env,redact}.py`, `docs/{protocol,provider-authoring,security,architecture}.md`, ADRs 0001–0013, `.github/workflows/real-providers.yml`, `tests/{conftest,test_conformance,helpers,test_ci_workflows,test_codes}.py`, `.kiro/specs/cycle2-reality-hardening/{design,tasks}.md`.
- **Findings**:
  - O registry já aplica as regras de manifest em um ponto único (`Registry._describe` → `_apply_limits`), que exclui capabilities com aviso `FORGE-MANIFEST-LIMITS` e marca o provider `invalid` quando nada sobra. É o ponto natural para as regras de taxonomia e de versão.
  - `ForgeManifest.version` é uma string livre: nenhuma validação de formato. `producer.version` precisa ser igual a ela em describe, health, execute e no `ExecutionResult`.
  - `Capability.id` já tem formato (`^[a-z][a-z0-9-]*(\.[a-z][a-z0-9-]*)+$`), sem limite de segmentos nem de tamanho; `actions` não têm formato.
  - O router explícito já desempata sobreposição por trust e depois id e escreve `"N providers declare it"` no `reason`; o caminho por sinais trata sobreposição como empate (`ambiguous`). Não há aliases nem depreciação.
  - O ambiente do provider é uma allowlist (`security/env.py`): nenhuma variável `THEFORGE_*` nem `AWS_*` chega ao provider. Logo, um contrato de ambiente para testes reais só pode ser lido pelo harness de testes (para montar `argv`), nunca repassado ao provider.
  - O cwd de `execute` é `.forge/runs/<id>/work`; de `describe`/`health`, um diretório temporário apagado depois. Ferramentas nativas que escrevem relativo ao cwd já ficam fora do workspace do usuário se o adapter não redirecionar para outro lugar.
  - `artifacts[].path` é validado lexicamente (relativo POSIX, sem `..`), sem raiz documentada; a Wave A fala em "raiz controlada do run".
  - `real-providers.yml` faz checkout de `siblings/spark-forge-aws` e `siblings/api-forge`, usa só Python 3.11, roda `pytest -m real_provider`, aceita exit 5 (seleção vazia) e tem `continue-on-error: true` (follow-up da Wave A: reconsiderar para dar visibilidade a falhas). Não há contrato de ambiente (Wave A 5.3 deixou para a Wave B).
  - `tests/conftest.py` exige que todo arquivo de teste tenha categoria em `FILE_MARKERS`; `pyproject.toml` exclui `slow` e `real_provider` da seleção padrão.
  - `tests/test_codes.py` proíbe literais `FORGE-*` fora de `contracts/codes.py`.
  - `tests/test_ci_workflows.py` fixa propriedades de `real-providers.yml` (gatilhos, `continue-on-error`, tokens só nos checkouts, seleção `-m real_provider` e aceitação de seleção vazia): mudar o workflow exige atualizar esses testes.
- **Implications**: as mudanças no core são pequenas e localizadas (contratos de manifest, registry, router, CLI de capabilities). O grosso do trabalho fica nos adapters e nos testes.

### Spark Forge real (`E:\projetos\spark-forge-aws`, `sparkforge-aws` 0.5.0, HEAD 0ce3b98) — auditoria estática + imports
- **Context**: requisitos 1.x e 5.3.
- **Sources Consulted**: `pyproject.toml`, `sparkforge/__init__.py`, `sparkforge/adapters/cli.py` (`main` l.6124-6132, mapeamento CLI→tool l.6045), `sparkforge/adapters/tools.py` (`TOOLS` l.5396, `_HANDLERS` l.12042, `call_tool` l.12182, `_may_fail` l.1610), `sparkforge/findings/{models.py,schemas/}`, `rules/catalog/*.yaml`, `sparkforge/journal/__init__.py`, `sparkforge/observability/{context_ledger,store}.py`, `sparkforge/doctor.py`, `sparkforge/_core.py`.
- **Findings**:
  - Distribuição `sparkforge-aws` 0.5.0, Python >=3.10, deps `PyYAML`, `jsonschema`; extras `aws` (boto3), `parquet` (pyarrow), `mcp`. `sparkforge.__version__ = "0.5.0"`; `sparkforge --version` lê metadados instalados e pode divergir do código (0.4.0 obsoleto visto nesta máquina) — a versão confiável é `sparkforge.__version__`.
  - CLI (`python -m sparkforge.adapters.cli`) sempre JSON em stdout; erro = texto em stderr com exit 2 (padrão de `AdapterError`), 1 em `doctor`/`scan --fail-on`. Não há verbo "tool + JSON".
  - Dispatcher programático: `call_tool(name, arguments, *, policy=None, channel="", transport="") -> dict`. Nome desconhecido → `KeyError` (única exceção). `AdapterError` vira `{"error", "exit_code", "error_code"?, "required_approval"?}`.
  - Registro estático: `TOOLS[name] = {description, inputSchema, outputSchema, annotations{readOnlyHint, destructiveHint, idempotentHint, openWorldHint}}`; 136 tools, todas `sparkforge_*`. Buckets: 96 read-only/offline; 20 escritores locais (case/debate/funcval/sdd/report_sign/scan/change/receipt/`code_*`); 17 `collect_*` open-world (AWS) + escrita local; nenhuma destrutiva.
  - Rede/AWS só em `sparkforge/collect/*` (boto3 lazy) e em `_core.doctor`: mesmo offline, `doctor` chama `boto3.Session().get_credentials()` (cadeia local de credenciais, pode sondar IMDS) — **o adapter não pode usar `doctor` no health**.
  - Modelo nativo: `Fact{id "f_<sha1[:6]>" estável, kind, measures, attrs, subject{file, line, symbol…}, provenance{artifact, artifact_sha256, extractor}}`; `Finding{rule_id "SF-<AREA>-NNN", title, severity P0..P4, confidence, status structural|confirmed, evidence: fact ids, explanation, proposed_change…}`. ~214 rule IDs em `rules/catalog/*.yaml`. Fluxo nativo: `analyze_*` produz facts; `judge` produz findings a partir de facts.
  - Escritas: quase tudo em `<repo>/.sparkforge/` (case, journal, artifacts, scan, code index…), relativo ao argumento `repo`; e **toda** chamada de `call_tool` grava `Path.cwd()/.sparkforge/traces.db` no fim do processo (também em leitura). `~/.sparkforge/` só em integrate/detach/evals. Nenhuma variável redireciona o diretório de estado.
  - Saída: 48 tools com `limit`/`cursor` (`{total_count, returned_count, next_cursor}`), 54 com `detail_level` (padrão `full`, o maior). Alguns `analyze_*` sem paginação (platform_graph, ecosystem, lakehouse_catalog, dbt_artifacts…) têm saída sem teto.
  - Custo de startup: `import sparkforge.adapters.tools` ~6 s a frio no Windows (544 módulos). O timeout de describe/health do core é 10 s.
- **Implications**:
  - O adapter Spark chama `call_tool` no próprio processo (dentro do interpretador do Spark Forge), nunca a CLI nem `doctor`.
  - `describe` e `health` não podem importar `sparkforge.adapters.tools` (risco de estourar 10 s): o manifest é derivado de um **snapshot gravado** da superfície real (`TOOLS` + anotações) empacotado no adapter e verificado contra o Forge real pela conformance de integração (drift). `health` usa só `importlib.util.find_spec` e `sparkforge.__version__`.
  - `repo` sempre aponta para a cópia `stage/` dentro do cwd do execute; `traces.db` cai no cwd. Assim nenhum `.sparkforge/` aparece no workspace do usuário.
  - Execute de uma ação `analyze_*` encadeia `judge` sobre os facts produzidos (o mesmo fluxo da CLI nativa `analyze --out` → `judge --facts`), sempre com `detail_level` reduzido e `limit`; `next_cursor` não nulo → resultado `partial`.

### API Forge real (`E:\projetos\api-forge`, `apiforge` 0.1.0) — auditoria estática
- **Context**: requisitos 2.x e 5.3 exigem derivar capabilities e erros da superfície real.
- **Sources Consulted**: `pyproject.toml`, `src/apiforge/cli.py` (`_echo_json` l.337, `_fail` l.363-372, `_run` l.386-427), `src/apiforge/rules/capability_matrix.yaml`, `src/apiforge/capabilities/registry.py`, `src/apiforge/contracts/{platform,base,distribution,evidence}.py`, `src/apiforge/core/models.py`, `src/apiforge/economy/ledger.py`, `src/apiforge/cache/store.py`, `src/apiforge/distribution/{doctor,paths}.py`, `docs/catalog-contract.md`.
- **Findings**:
  - Python `>=3.12,<3.13`; deps pesadas (pydantic, typer, tree-sitter, cryptography…). Console script `apiforge = apiforge.cli:app` (Typer). `--version` imprime texto (`apiforge 0.1.0`).
  - Sucesso: JSON em stdout. Erro: uma linha de texto em stderr `AF-CODE: detail (field=...; unlock=...)`. Exit 0 sucesso; 2 recusa tipada, `AF-CLI-INPUT` e `AF-CLI-INTERNAL`; 3 `CaseIntegrityError`; 4 `analyze --fail-on` (achados acima do limiar, não falha). Catálogo `AF-*` em `docs/catalog-contract.md`.
  - Matriz pública: `rules/capability_matrix.yaml` (dado empacotado, carregado por `capabilities/registry.load_capabilities()`; também `apiforge capabilities list` em JSON). 21 registros `CapabilityRecord` (`version: 1`) com `capability_id`, `state` (supported|heuristic|unresolved|unsupported), `risk` (read_only|local_reversible|sensitive|external_mutation), `surfaces`, `prerequisites`, `limitations`. IDs já casam com o regex de capability do core.
  - Não existe verbo de CLI por capability: o mapeamento capability → verbo é implícito. Mapeamentos claros: `api.analyze` → `analyze`, `api.next-step` → `next-step`, `api.change-control` → `change-control run`; `*.verify-runtime` → `platform verify-runtime --vertical X` (roda probes locais que vivem em `tests/fixtures`, ausentes numa instalação só do wheel); `*.inspect` não têm verbo único.
  - Exigem rede/credenciais apesar de `read_only`: `git.read-context` (token GitHub), `integration.github-issues`, `integration.health`, `integration.json-read` (URL + token). `git.plan` é `unresolved`/`local_reversible`; `external.apply` é `unsupported`/`external_mutation`. `collect *` (AWS/boto3) não está na matriz.
  - `CapabilityResult` (`contracts/platform.py:69`) é só projeção da matriz (não executa nada) e não é exposto na CLI. `apiforge_call` (`mcp/gateway.py`) despacha por nome de função MCP, não por capability.
  - Modelo de evidência nativo estável: `Finding{finding_id, rule_id, status confirmed|unresolved|not_applicable, severity info..critical, title, detail, evidence: fact_ids}`, `Fact{fact_id, kind, source: SourceRef{path, sha256 (64 hex), line?, column?}}`. Achados `confirmed` sempre têm evidência.
  - Efeitos colaterais relativos ao cwd: `.apiforge/economy.jsonl` a cada emissão JSON (não redirecionável; só o cwd controla); cache `.apiforge/cache` (desligável com `APIFORGE_CACHE=off`); `analyze --out-dir` padrão `.apiforge`.
  - Saídas grandes: sem paginação; `analyze` devolve contagens e mapa de artefatos em disco; `--detail-level summary|normal|full`.
  - Saúde: `apiforge doctor` → `apiforge/doctor/v1` com `status ready|degraded|unresolved|blocked`, offline.
  - Três convenções de versão coexistem (`version` int, `apiforge/*/v1`, `af-*/1`) — já motivou o ADR 0002 do core.
- **Implications**: o adapter API embrulha a CLI pública (não a projeção `CapabilityResult`): roda `apiforge` no mesmo interpretador, cwd do adapter, `APIFORGE_CACHE=off`, entradas por caminho absoluto, `--out-dir` dentro do cwd; traduz a linha `AF-*` do stderr em `ErrorInfo` preservando código, `field` e `unlock`. As capabilities expostas vêm da matriz em tempo de describe, filtradas por estado, risco e por uma tabela de mapeamento verbo-offline mantida pelo adapter; o resto vai para `limitations` do manifest com o motivo.

### Semântica dos hashes nativos × `Evidence.hash` (revisão cruzada com `context-intelligence-v2`)
- **Context**: `context-intelligence-v2` trata `Evidence.hash` não nulo diferente de `ContextFile.sha256` do mesmo `location.path` como drift reportado pelo provider (rebaixa a evidência para `unresolved` e força `partial`). `ContextFile.sha256` é do arquivo inteiro (itens reference) ou do intervalo `lines` (excerpt/requested).
- **Sources Consulted**: `sparkforge/facts/*.py` (montagem de `provenance`), `sparkforge/evals/evidence_adapters.py`, `sparkforge/dqdl/validator.py`; `apiforge/core/models.py` (`SourceRef.sha256`), `apiforge/adapters/*` (cálculo dos hashes por extrator).
- **Findings**:
  - Spark: `provenance.artifact_sha256` é calculado por extrator. Há casos sobre `text.encode("utf-8")` do texto decodificado (`facts/cdc.py`, `dqdl/validator.py`), casos sobre o payload parseado de um artefato (`athena_workgroup`, `catalog_schema`, `controlm_jobs`) e um consumidor que remove o prefixo `sha256:`. `provenance.artifact` pode ser diferente de `subject.file`. Não está provado que seja o sha256 dos bytes do arquivo em `location.path`.
  - API: `SourceRef.sha256` é validado como 64 hex; a maioria dos extratores usa `hashlib.sha256(path.read_bytes())`, mas alguns hasheiam texto (`graph_/plans.py`, `graph_/extract.py` para `query_sha256`). Sem garantia uniforme de ser o sha256 dos bytes de `source.path`.
- **Implications**: copiar hash nativo para `Evidence.hash` pode gerar drift falso. Regra adotada: `Evidence.hash` é o sha256 exatamente do conteúdo que o `ContextFile` de `location.path` cobre; o hash nativo só é copiado quando igual ao sha256 conferido no staging, senão `null`. Itens com `lines` não são copiados para `stage/` nesta wave.

### Skills e guias consultados
- `kiro-spec-design` (rules `design-principles`, `design-discovery-full`, `design-synthesis`, `design-review-gate`): boundary-first, File Structure Plan concreto, review gate mecânico.
- Pesquisa externa: não necessária. Não há biblioteca nova (core stdlib-only; adapters stdlib-only); SemVer 2.0.0 é gramática conhecida e implementável com `re`. As superfícies externas relevantes são os dois repositórios irmãos, auditados localmente.

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Notes |
|--------|-------------|-----------|---------------------|-------|
| A. Adapter dentro do pacote `theforge` | módulos `theforge.providers.sparkforge`/`apiforge` | um único pacote | viola "nunca `import sparkforge`/`apiforge`" se importar; exige o Forge no mesmo interpretador do core (API exige 3.12); acopla release do core às superfícies nativas | rejeitado |
| B. Entrada nativa em cada Forge | `python -m sparkforge.forge_protocol`, `python -m apiforge.forge_protocol` | menor acoplamento; dono da superfície mantém a tradução | exige mudança aceita pelos donos dos repositórios irmãos e release coordenado; não testável no CI de The Forge sem os irmãos | alvo futuro (gatilho no ADR) |
| C. Adapter como distribuição separada, mantida no repositório de The Forge, instalada no interpretador do especialista | `adapters/sparkforge`, `adapters/apiforge` (stdlib-only), registrados por `argv` | não toca os irmãos; core continua sem importar especialistas; conformance offline no CI principal via replay; versionamento próprio | acoplamento do adapter à superfície nativa fica do lado de The Forge; version skew precisa de janela explícita | **escolhido** |

## Design Decisions

### Decision: Local dos adapters (ADR 0014)
- **Context**: requisito 4.6; o brief recomenda entrada nativa pequena se o dono aceitar, senão adapter separado no venv do especialista.
- **Alternatives Considered**: A, B, C da tabela acima.
- **Selected Approach**: C. Duas distribuições stdlib-only (`theforge-sparkforge-adapter`, `theforge-apiforge-adapter`), versões próprias SemVer, `requires-python >=3.10`, sem dependência declarada do Forge especialista (instaladas no interpretador onde ele já está). Nenhuma importa `theforge`.
- **Rationale**: entrega a Wave B sem depender de aceitação externa; mantém as invariantes do core; o código de tradução fica testável offline.
- **Trade-offs**: The Forge carrega o custo de acompanhar a superfície nativa; mitigado por snapshot + teste de drift + janela de versão.
- **Follow-up**: migrar para B quando um dono aceitar a entrada nativa; o protocolo não muda, só o `argv`.

### Decision: Superfície nativa por snapshot gravado + replay
- **Context**: Spark leva ~6 s para importar (describe/health têm 10 s); a conformance offline não pode depender dos irmãos (3.1).
- **Selected Approach**: cada adapter empacota um snapshot da superfície nativa (`native_catalog.json`: tools + anotações do Spark; matriz do API) gravado por um módulo `record` executado no interpretador do especialista. `describe` deriva o manifest do snapshot; a conformance de integração compara snapshot × superfície viva (drift). Para execute/health offline, `--replay <dir>` substitui só a fronteira nativa por saídas gravadas.
- **Rationale**: describe rápido e determinístico; derivação da superfície real preservada e verificada.
- **Trade-offs**: o snapshot pode ficar velho entre execuções do workflow real; janela de versão e drift semanal limitam a exposição.

### Decision: Exposição padrão por lista positiva
- **Context**: 1.5, 2.5; out of boundary: rede/credenciais.
- **Selected Approach**: só capabilities da tabela de mapeamento do adapter são declaradas; a tabela só aceita origem read-only/offline (Spark: `readOnlyHint` verdadeiro e `openWorldHint` falso; API: `state ∈ {supported, heuristic}`, `risk = read_only`, verbo offline). Todo o resto vai para `manifest.limitations` com motivo. Não existe opt-in nesta wave.
- **Rationale**: fail-closed; a policy (`read_only = allow`) não precisa de exceção.

### Decision: Contenção de arquivos auxiliares por cwd + `stage/`
- **Context**: 1.6, 2.6; nenhum Forge permite redirecionar estado por variável.
- **Selected Approach**: o adapter copia para `<cwd>/stage/` só os arquivos do ContextPack (sha256 conferido) e passa esse diretório como `repo`/`--project`; saídas nativas vão para subdiretórios do cwd. Em execute o cwd é `.forge/runs/<id>/work`; em describe/health, o diretório temporário do core.
- **Rationale**: respeita "ler só arquivos do ContextPack" e impede escrita em `<workspace>/.sparkforge` e `<workspace>/.apiforge`.
- **Trade-offs**: contexto limitado pelo budget do perfil; ferramentas que precisariam do repositório inteiro trabalham sobre o subconjunto (limitação explícita no resultado).

### Decision: Versão SemVer obrigatória e janela no adapter
- **Context**: 4.4, 4.5.
- **Selected Approach**: o core valida a gramática SemVer 2.0.0 de `manifest.version` (malformada → `invalid`, `FORGE-MANIFEST-VERSION`). A janela do Forge especialista (`SUPPORTED_SPECIALIST`) é do adapter, que reporta `degraded` fora dela. O core não compara versões de especialistas (não conhece especialistas).
- **Trade-offs**: providers de terceiros com versões `1.0`/`v1.2.3` deixam de rotear (fail-closed); documentado como gatilho de revalidação.

### Decision: Taxonomia mecânica mínima + aliases/depreciação aditivos (ADR 0017)
- **Context**: 5.1–5.7.
- **Selected Approach**: regras verificáveis (segmentos 2–3, tamanho, namespaces reservados, segmentos genéricos proibidos, formato de ação) numa função pura no estilo de `validate_manifest_limits`; violação exclui a capability com aviso `FORGE-MANIFEST-TAXONOMY`. `Capability` ganha `aliases`, `deprecated`, `replaced_by` opcionais (forward-compat em `forge/v1`). O router resolve alias só no caminho explícito, canônico antes de alias, e registra alias, depreciação e sobreposição em `limitations`; nenhum peso novo.
- **Rationale**: limites, taxonomia e versão compartilham o mesmo ponto de aplicação (`Registry._apply_manifest_rules`); sem registro central de nomes nem versionamento por capability (`v2` vira nova capability + depreciação da antiga).

### Decision: `Evidence.hash` só com sha256 do conteúdo coberto pelo ContextPack
- **Context**: revisão cruzada com `context-intelligence-v2` (drift reportado por `Evidence.hash`); auditoria dos hashes nativos acima.
- **Selected Approach**: regra comum no AdapterShell (`evidence_hash`): `Evidence.hash` não nulo é o sha256 do arquivo inteiro em `location.path` (ou do intervalo `lines`, quando itens por intervalo forem adotados), igual ao sha256 conferido no staging; hash nativo (`provenance.artifact_sha256`, `source.sha256`) só é copiado quando igual a esse valor, senão `null`. Teste offline (6.3) e de integração (7.2) garantem que `Evidence.hash` nunca diverge de `ContextFile.sha256`.
- **Alternatives Considered**: copiar o hash nativo sempre (drift falso); recalcular sempre o sha256 do staging (afirmaria um hash que o especialista não reportou).
- **Trade-offs**: evidência sem hash quando o especialista hasheia outro conteúdo; o drift continua detectado pela reverificação do core.

### Decision: Declarar `context_revalidation = "hash"` nos adapters
- **Context**: sem a declaração, `context-intelligence-v2` registra `undeclared` e uma limitação em todo run real.
- **Selected Approach**: o adapter confere o sha256 de cada arquivo ao copiar para `stage/` e o especialista lê só a cópia, dentro do cwd do run: é a estratégia `hash`. Os manifests declaram o campo opcional; cores sem ele o ignoram (forward-compat de `forge/v1`), então não há dependência de ordem de merge.

### Decision: Reduzir `.forge/runs/<id>/work/` aos artifacts declarados
- **Context**: a invariante "tudo que o core persiste passa por `security.redact`" não cobre o que o provider escreve no cwd do run: cópias do contexto (`stage/`), estado nativo (`.sparkforge/`, `traces.db`, `.apiforge/economy.jsonl`) e saídas nativas.
- **Selected Approach**: `cleanup_workdir` no AdapterShell, em todo desfecho de execute, apaga `stage/` e tudo o que não é path de `artifacts[]`; artifacts declarados (spill `native/full-output.json`, arquivos de caso) permanecem e são escopo explícito. `docs/security.md` e ADR 0014 registram que `work/` guarda dados do provider não redigidos, fora da invariante do core.
- **Alternatives Considered**: redigir `work/` no core (o core não conhece o formato dos arquivos do provider); manter tudo para depuração (expõe cópias do contexto e estado nativo sem necessidade).
- **Trade-offs**: depurar uma falha nativa exige reexecutar; o resultado e o receipt já trazem o erro estruturado.

### Decision: Mensagem acionável quando o especialista não está instalado
- **Context**: 1.8, 2.7. Hoje um describe com status ≠ ok vira `invalid` com só o código (`describe <code>`), sem o detalhe.
- **Selected Approach**: o adapter responde describe `refused` com código próprio (`SPARKFORGE-ADAPTER-UNAVAILABLE`, `APIFORGE-ADAPTER-UNAVAILABLE`) e detalhe acionável (interpretador, versão de Python, o que instalar). O registry passa a incluir o detalhe redigido e truncado (500 caracteres) no `error` do registro. Interpretador inexistente continua `unreachable` com `FORGE-PROTO-SPAWN` e o caminho.
- **Rationale**: registros `invalid` não são cacheados, então instalar o Forge depois resolve sem limpar cache; manifest vazio + health `unavailable` foi rejeitado porque ficaria cacheado (o fingerprint não cobre código importado) e nunca seria revalidado.

### Synthesis
- **Generalização**: os dois adapters são o mesmo problema (envelope, despacho, staging, spill, erro nativo → `ErrorInfo`), resolvido por um `_shell.py` comum (cópia idêntica verificada por teste, porque cada adapter roda em outro interpretador e nenhum pode depender do outro nem de `theforge`). As regras de manifest (limites, taxonomia, versão) passam por um único ponto no registry.
- **Build vs adopt**: não há biblioteca a adotar para Forge Protocol; SemVer por regex stdlib (sem `packaging`, que seria dependência). Os adapters adotam as superfícies públicas existentes (`call_tool`, CLI `apiforge`, matriz) em vez de remodelá-las.
- **Simplificação**: sem opt-in para capabilities de rede; sem registro central de taxonomia; sem flag de teste para skew de protocolo (já coberto na Wave A); `api.next-step` fora do conjunto inicial em vez de inventar parâmetro no `ExecuteRequest`; `judge` do Spark não vira capability própria: é encadeado pela ação de análise, como na CLI nativa.

## Risks & Mitigations
- Snapshot da superfície nativa envelhece → teste de drift semanal + janela de versão + health `degraded` fora da janela.
- Budget de contexto pequeno demais para análises de projeto → limitação explícita no resultado; perfil `max`; evolução de contexto é de `context-intelligence-v2`.
- Import do Spark (~6 s) consome o timeout de execute em `economy` (60 s) → o adapter limita a chamada nativa a 85% do timeout do perfil e reporta `ADAPTER-NATIVE-TIMEOUT` estruturado.
- API Forge exige 3.12 (ausente localmente) → integração do API pula com motivo localmente e roda no workflow real com `setup-python` 3.12.
- Numeração de ADR entre as waves: congelada — 0014 (adapters) e 0017 (taxonomia) desta spec; 0015 e 0016 de `context-intelligence-v2`; 0018 e 0019 de `cross-forge-foundation`; 0020 de `agentic-maintainability`. Sem fallback para "próximo número livre".
- Merge com `context-intelligence-v2` (campos opcionais em `Capability`/`ForgeManifest`/`ExecutionResult`/`ContextPack`) → schema regenerado por quem fizer merge por último; adapters tratam os campos de contexto como ausentes, exceto `context_revalidation = "hash"`, que declaram.
- Drift falso por hash nativo de outro conteúdo → regra de `Evidence.hash` com `null` quando não provado igual; teste sem drift (6.3, 7.2).
- Sinais dos adapters não qualificarem exatamente uma capability por Forge para a tarefa de prova de `cross-forge-foundation` → checagem do lado B em replay (6.4); correção no catálogo dos adapters, nunca no core.
- Matriz de compatibilidade quebra quando outra wave altera `theforge.__version__` → regra "toda wave que altera a versão acrescenta a linha" em `docs/versioning.md`, gatilho de revalidação.
- Códigos `FORGE-*` com duas tabelas divergentes → `docs/errors.md` (de `cross-forge-foundation`) é a lista canônica testada; `docs/protocol.md` só tabela curta com link.
- `.forge/runs/<id>/work/` com dados do provider não redigidos → `cleanup_workdir` + registro em `docs/security.md` e ADR 0014.
- Mudança de regra de manifest quebra providers de terceiros → mensagens acionáveis, notas de migração em `docs/provider-authoring.md`, gatilho de revalidação documentado.

## References
- `docs/protocol.md`, `docs/provider-authoring.md`, `docs/security.md`, `docs/architecture.md`; ADRs 0001, 0002, 0004, 0006, 0009–0013.
- `.kiro/specs/cycle2-reality-hardening/{design.md,tasks.md}` (Implementation Notes 5.3, 6.2 e follow-ups).
- SemVer 2.0.0 — https://semver.org/spec/v2.0.0.html (gramática da versão).
