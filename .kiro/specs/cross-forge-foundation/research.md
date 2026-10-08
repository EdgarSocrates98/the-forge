# Research & Design Decisions — cross-forge-foundation (Wave D)

## Summary
- **Feature**: `cross-forge-foundation`
- **Discovery Scope**: Extension (integração sobre o core existente e sobre as Waves B e C; sem biblioteca nova)
- **Key Findings**:
  - O core já tem quase tudo o que um nó de plano precisa: `Forger.ask` faz revalidação do registry, health, policy, contexto, execute, integridade, persistência redigida e receipt. O executor de plano deve **reutilizar** esse caminho por nó (um run filho por nó), não duplicá-lo.
  - A decomposição pode ser determinística e sem domínio reaproveitando `route()`: `RoutingDecision.candidates` já carrega, por (provider, capability), a contagem de tipos de sinal discriminantes e as keywords casadas. Falta só agrupar por provider e ordenar por uma regra genérica.
  - `explain` hoje só despeja os artefatos crus; o receipt já guarda hashes de `task`/`routing`/`context`/`risk`/`result` (e, com a Wave C, `telemetry` e `context-r*`). Verificar hashes é recalcular `sha256_of` do JSON em disco — o mesmo que `RunStore.write` devolve.

## Research Log

### Pontos de extensão no core (Wave A + Cycle 1)
- **Context**: onde encaixar plano, handoff, verificação e reprodutibilidade sem quebrar o fluxo `ask`.
- **Sources Consulted**: `src/theforge/forger/orchestrator.py`, `routing/router.py`, `runs/store.py`, `contracts/*.py`, `cli/main.py`, `cli/commands.py`, `docs/protocol.md`, `docs/cli.md`.
- **Findings**:
  - `Forger.ask` cria o run, grava `task` e segue `scan → _final_route → _select_healthy → policy → context → execute → integridade → result → _finish(receipt)`. Erros inesperados viram `FORGE-INTERNAL` com receipt; a CLI já não imprime traceback (`theforge: internal error: <Tipo>: <msg>`, exit 70).
  - `RoutingDecision.pattern` é `Literal["route"]` e `selected` já é lista de `Selection` com `role` — suporta múltiplas seleções sem mudar a forma.
  - `RunStore.ARTIFACTS` é uma tupla fechada; `read_contract` relê estritamente; `write` redige e devolve o hash do conteúdo em disco; `validate_receipt` confere `result_sha256` contra o disco.
  - `docs/protocol.md` reserva as ops `plan`, `verify`, `estimate` e os nomes `ExecutionPlan`, `VerificationResult`, `GraphNode`, `GraphEdge`, `InstallationPlan`, `WorkspaceDescriptor`, `DecisionRecord`, `Budget`, `EnvironmentReport`.
  - `TaskSpec.constraints: dict[str, Any]` existe e pode carregar o vínculo plano↔nó sem novo campo.
  - Códigos `FORGE-*` vivem só em `contracts/codes.py` (módulo mais à esquerda); `UsageError`/`PersistenceError` não têm código.
- **Implications**: o executor de plano chama um método de nó do `Forger` que é o mesmo pipeline de `ask` com provider fixado, handoff e vínculo ao plano; a taxonomia mora em `codes.py`; erros de CLI ganham código.

### Seams com `context-intelligence-v2` (Wave C)
- **Context**: perfis, git e verificação de contexto já pertencem à Wave C.
- **Sources Consulted**: `.kiro/specs/context-intelligence-v2/design.md` (Boundary Commitments, Profiles, GitReader, ContextVerify, TelemetryRecorder, RunStore).
- **Findings**:
  - `profiles.PROFILES`: `max_providers` = 1 (`economy`, `balanced`) e 4 (`max`); registrado, não aplicado pela Wave C.
  - `context.git.read_git_state(root)` nunca levanta exceção, não escreve no repositório e não executa programas do repositório; devolve `GitState(summary, changed, limitations)`.
  - `context.verify.reverify(root, items)` recalcula hashes (arquivo inteiro ou intervalo) sem cache; `DriftReport` e `apply_drift` já rebaixam evidência e marcam `partial`.
  - `RunTelemetry` v1 é gravado em todo run de `ask` e vinculado ao receipt por `telemetry_sha256`; `explain --json` da Wave C inclui `telemetry` por ler `ARTIFACTS`.
  - `WorkspaceSummary` é local ao ContextPack e não pode ser promovido a descritor de workspace.
- **Implications**: o descritor de workspace chama `read_git_state` por repositório e embute o `GitSummary` devolvido em `RepositoryInfo.git` (sem redeclarar branch/head/dirty/state; mantém `detached` e `changed_files`), com orçamento total de git por descrição de 20 s (`WORKSPACE_GIT_BUDGET_S`), pois 64 repositórios × 5 s (`GIT_TIMEOUT_S` por consulta) daria até 320 s; o run do plano reutiliza `RunTelemetry` v1/`TelemetryRecorder` (tempos de varredura/routing, `providers_executed` = nós executados, `ProfileSnapshot`) e o receipt de plano registra `telemetry_sha256`; o texto do `explain` da Wave C (itens com tier e sinais, exclusões, `unmatched`, git, rodadas, drift, linha `Telemetry:`) é preservado lendo os artefatos crus; re-verify do replay usa `reverify`; o limite de providers do plano vem de `profile_for(...).max_providers`; o `explain --json` passa a ser um contrato próprio e o teste da Wave C que procura `telemetry` no topo precisa migrar para `artifacts.telemetry`.

### Seams com `real-provider-integration` (Wave B)
- **Context**: a prova real usa os adapters e o contrato de ambiente da Wave B.
- **Sources Consulted**: `.kiro/specs/real-provider-integration/design.md` (SparkForgeAdapter, ApiForgeAdapter, OfflineConformance, RealProviderEnv, Revalidation Triggers).
- **Findings**:
  - Spark Forge: id `spark-forge`, capability `pyspark.static-analysis` (sinais `pyspark`, `spark`, `*.py`, dependência `pyspark`), evidência com IDs nativos `f_xxxxxx`. API Forge: id `api-forge`, capability `api.analyze` (contrato OpenAPI + projeto), evidência com `fact_id`.
  - Modo `--replay <dir>` dos adapters roda sem o especialista e sem rede; é o equivalente offline natural da prova real.
  - Contrato de ambiente: `THEFORGE_REAL_SPARKFORGE_PYTHON`, `THEFORGE_REAL_APIFORGE_PYTHON`, `THEFORGE_REAL_PROVIDERS_REQUIRED`; harness `tests/real_providers.py::require_forge`.
  - `artifacts[].path` é relativo ao cwd do execute (`.forge/runs/<id>/work`); mudança disso é gatilho de revalidação para a Wave D.
  - O `AdapterShell` lê `ExecuteRequest` do stdin; nenhum dos adapters declara consumo de handoff nem determinismo.
- Aliases e notas: `ForgeManifest.resolve` resolve ID canônico antes de alias; as notas `capability-alias`/`capability-deprecated`/`capability-overlap` ficam em `RoutingDecision.limitations`. `docs/versioning.md` tem a matriz de compatibilidade testada por `test_compat_matrix` (linha obrigatória para `theforge.__version__`).
- Cenários de replay: `tests/fixtures/native/<adapter>/default/` (saudável) e `scenarios/<nome>/`; os workspaces de exemplo da Wave B são `tests/fixtures/workspaces/{spark,api}/`.
- **Implications**: handoff entra como campo opcional de `ExecuteRequest` (adapters devem ignorá-lo; verificado em replay); a prova real usa `require_forge` e o marker `real_provider`, sem mudar o workflow; a ausência de declaração de handoff vira limitação explícita, não falha. `check_plan`/`load_plan_file` usam `ForgeManifest.resolve` e registram o ID canônico com a nota de alias; `RoutingSection.notes` preserva as notas no `explain`. Esta spec possui os cenários `scenarios/cross/` dos dois adapters para o workspace `cross` (decisão: gravações próprias, em vez de tornar `cross/*` cópias byte a byte dos workspaces de exemplo da Wave B, porque o workspace `cross` é multi-repo e os caminhos de evidência precisam casar com ele). Qualquer wave que mude `theforge.__version__` acrescenta a linha da matriz.

### Reprodutibilidade e replay
- **Context**: Req 14 exige nível honesto e replay com três modos.
- **Findings**:
  - O manifest só declara `execution.{local, offline, requires_network}` e `operation_class` por capability; não existe declaração de determinismo.
  - O receipt já guarda identidade do provider (`fingerprint`, `observed_version`, `manifest_sha256`) e hashes de contexto.
- **Implications**: um campo opcional `ExecutionInfo.deterministic` é necessário para que `reproducible` seja alcançável sem chute; na ausência dele o teto é `partially_reproducible`.

### Tecnologia
- Nenhuma dependência nova. Tudo em stdlib (`graphlib.TopologicalSorter` disponível desde 3.9 para ordenação topológica; `tomllib` para a configuração de relações; `traceback.extract_tb` para quadros do diagnóstico).
- `graphlib` foi avaliado: detecta ciclos (`CycleError`) mas sua ordem de saída depende da ordem de inserção; a ordem determinística exigida é obtida com Kahn explícito e desempate por id. Decisão: implementar Kahn de ~20 linhas com desempate documentado; `graphlib` não é usado.

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Notes |
|--------|-------------|-----------|---------------------|-------|
| Run filho por nó (selecionada) | cada nó é um run completo de `Forger` com provider fixado, vinculado ao run do plano | reutiliza todas as garantias da Wave A–C; cada nó é explicável sozinho; receipt por nó | mais diretórios de run; o plano precisa de seu próprio receipt | mantém "nenhum sucesso sem ExecutionResult válido" por nó |
| Plano dentro de um único run | um run com N resultados | menos diretórios | quebra `RunStore`/receipt (1 resultado por run), duplica o pipeline | rejeitada |
| Scheduler com fila/estado | executor persistente | retomada | fora de escopo (roadmap: sem orquestrador distribuído) | rejeitada |

## Design Decisions

### Decision: decomposição por agrupamento dos candidatos do router e ordem pela intenção
- **Context**: Req 2 exige decomposição determinística, sem domínio e sem LLM; Req 6.1 exige que a tarefa de prova vire nó de dados → nó de API.
- **Alternatives Considered**:
  1. Providers declararem `produces`/`consumes` por capability — exige mudar os adapters da Wave B e introduz vocabulário de domínio no protocolo.
  2. Plano sempre explícito em arquivo — não atende Req 2/6.1.
  3. Agrupar `RoutingDecision.candidates` por provider e ordenar pela posição, na intenção, da primeira keyword casada de cada nó.
- **Selected Approach**: 3. Um nó por provider cuja melhor capability atinge `MIN_SIGNAL_TYPES` discriminantes; ordem pela menor posição de token de keyword casada; pipeline linear. A dependência é registrada como `inferred` com a regra `intent-order` e a evidência (keyword e posição). Empate de posição, keyword ausente, empate de capability dentro do mesmo provider ou excesso sobre `max_providers` → `ambiguous`.
- **Rationale**: só usa sinais declarados pelos providers e a própria tarefa; é explicável e testável por permutação.
- **Trade-offs**: a ordem textual é só um proxy do fluxo de dados e pode produzir uma dependência `inferred` errada ("API que consome dados do Spark" põe a API antes); mitigado por `plan` sem `--execute` (revisão) e por plano explícito em arquivo (`--from FILE`). O limite é documentado no ADR 0018 e no texto de ajuda de `plan`.
- **Follow-up**: validado cedo, na tarefa 2.3 (`test_decompose.py` com os manifests empacotados dos adapters em `--replay`), que `pyspark.static-analysis` e `api.analyze` são as melhores capabilities únicas de cada Forge para a tarefa de prova; falha ali é revalidação do catálogo da Wave B, nunca regra de domínio no core.

### Decision: handoff como campo opcional de `ExecuteRequest`
- **Context**: Req 4 exige entregar ao provider dependente apenas saídas estruturadas.
- **Alternatives Considered**: (1) arquivo no cwd do nó; (2) campo opcional `ExecuteRequest.handoff`; (3) nova op.
- **Selected Approach**: (2), contrato `theforge/Handoff/v1` aberto (cruza o protocolo), persistido como artefato `handoff` do run do nó e vinculado ao receipt. Providers que não reconhecem o campo o ignoram (leitura não estrita, como hoje). Capability declara consumo por `accepts_handoff` (opcional, `false`).
- **Rationale**: aditivo em `forge/v1`; sem nova op; auditável.
- **Trade-offs**: os adapters reais não usam o handoff nesta wave; a prova registra a limitação `handoff-use-undeclared`. Adoção pelos adapters é revalidação futura da Wave B.

### Decision: ativar `plan`, manter `verify` reservado
- **Context**: Req 10.4 permite ativar ops reservadas só com caso de uso concreto.
- **Selected Approach**: `plan` é ativada para o fluxo `theforge plan`: estimativa antes da execução (contexto necessário, classe de operação estimada, artifacts esperados, incógnitas), e a policy do nó usa a decisão mais restritiva entre a classe declarada e a estimada. `verify` permanece reservada: nenhum provider do ciclo oferece verificação independente; o nível independente do `VerificationResult` fica `not_performed`. `estimate` continua reservada.
- **Rationale**: há consumidor real para `plan` (pré-visualização e policy); não há para `verify`.

### Decision: `ExplainReport` v1 como contrato do `explain --json`
- **Context**: Req 11.4/11.5 exigem estrutura estável, versionada e com schema.
- **Selected Approach**: contrato fechado `theforge/ExplainReport/v1` com seções resumidas tipadas, relatório de integridade e os artefatos crus redigidos em `artifacts`. Substitui o despejo atual (topo com nomes de artefato), que nunca foi documentado como estável.
- **Trade-offs**: muda o formato atual de `explain --json`; testes existentes (incluindo o da Wave C que procura `telemetry`) migram para `artifacts.<nome>`.
- **Texto**: o texto do `explain` é reescrito de forma aditiva; as seções da Wave C e as notas de routing da Wave B são renderizadas dos artefatos crus com o mesmo formato, e seus testes entram na lista de revalidação desta spec sem mudança de asserção. `RoutingSection.notes` e `ContextSection.{unmatched, git, drift}` são os únicos acréscimos tipados; itens e exclusões não são duplicados no relatório.

### Decision: taxonomia por mapa explícito código → família
- **Context**: códigos publicados não podem mudar e não seguem um prefixo uniforme (`FORGE-HEALTH-*`, `FORGE-RESULT-*`, `FORGE-PROVIDER-BLOCKED` é de trust).
- **Selected Approach**: `CODE_FAMILIES: Mapping[str, ErrorFamily]` em `contracts/codes.py`, cobrindo todo valor de `Codes`; teste falha para código sem família, para literal `"FORGE-…"` fora de `codes.py`, para divergência com `docs/errors.md` e para mudança de valor contra `tests/golden/forge_codes.json`.
- **Rationale**: mapeamento por prefixo classificaria mal códigos existentes.
- **Fonte documental**: `docs/errors.md` é a lista canônica; `docs/protocol.md` aponta para ela e não mantém tabela concorrente; `test_error_taxonomy.py` confere a paridade (link presente, códigos citados existem com a mesma família).

### Decision: reprodutibilidade conservadora
- **Selected Approach**: `reproducible` só com execução local/offline sem rede, capability `read_only`, `ExecutionInfo.deterministic = true`, identidade do provider registrada, hash de contexto registrado, contexto reverificado sem divergência (nível de verificação ≠ `minimal`), handoff só de nós `reproducible` e status `ok`. Acesso externo, `operation_class` externa/destrutiva ou divergência → `non_reproducible`. Sem execução de provider → `unknown`. Demais casos → `partially_reproducible`. Plano = mínimo dos nós.

### Decision: descritor de workspace com relações explícitas por configuração
- **Selected Approach**: repositórios descobertos até profundidade 3 sem seguir symlinks; HEAD/sujo via `read_git_state`; tecnologias = dependências dos arquivos de manifesto genéricos que casam com `signals.dependencies` de algum provider, e `domains` de providers cujos globs casam arquivos do repositório; relações `contains` observadas no sistema de arquivos e `depends_on` explícitas em `.forge/config/workspace.toml`.
- **Rationale**: nenhum conhecimento de domínio no core; nenhuma relação inferida.

## Synthesis Outcomes
- **Generalização**: plano de um nó com padrão `route` e `ask` são o mesmo caminho (`Forger` com provider opcionalmente fixado); a decomposição degrada naturalmente para `route` quando o perfil limita a 1 provider. `VerificationResult` e nível de reprodutibilidade são produzidos para runs de `ask` e de nós pelo mesmo código.
- **Build vs. adopt**: ordenação topológica própria (determinismo de desempate) em vez de `graphlib`; consulta git, reverificação de contexto, perfis e telemetria adotados da Wave C; adapters, replay e contrato de ambiente adotados da Wave B. Nenhuma biblioteca externa.
- **Simplificação**: sem fila, sem retomada de plano, sem concorrência; `delegate`, `parallel` e `debate` só representados (rejeitados se pedidos); `verify` e `estimate` não ativadas; re-execute só para runs de um provider; o grafo é artefato do run, sem índice; nenhum comando novo além de `plan`, `workspace show` e `replay`.

## Risks & Mitigations
- Sinais dos adapters reais podem não qualificar exatamente um nó por Forge para a tarefa de prova (empate entre capabilities do Spark Forge ou do API Forge, ou sinal compartilhado) — validado cedo na tarefa 2.3 com os manifests empacotados em replay, não só na prova real; a correção pertence ao catálogo da Wave B (gatilho de revalidação), nunca a uma regra de domínio no core.
- Crescimento do `Forger` — a execução de nó reutiliza `ask` por um método interno com parâmetros de fixação; o executor de plano fica em módulo próprio.
- Mudança do formato de `explain --json` — contrato versionado, documentado e com schema; migração de testes listada no design.
- Plano grande gerando muitos runs — limite de nós (`MAX_PLAN_NODES = 8`) e de providers do perfil.
- Handoff com segredo vindo de um provider — redação antes da entrega e da persistência; limite de tamanho e truncagem determinística.
- Tempo de git em workspaces grandes — orçamento total de 20 s por descrição; repositórios além do orçamento ficam sem resumo git, com limitação.
- Confusão de nomes entre o artefato do descritor e `ContextPack.workspace` — o artefato chama-se `workspace-descriptor`.

## References
- `.kiro/specs/context-intelligence-v2/design.md` — perfis, `read_git_state`, `reverify`, `RunTelemetry`.
- `.kiro/specs/real-provider-integration/design.md` — adapters, replay, `require_forge`, IDs nativos de evidência.
- `docs/protocol.md` — ops e nomes reservados.
- `docs/adr/0001-exec-protocol.md`, `0005-deterministic-routing-first.md`, `0010-policy-model.md`, `0013-provider-identity.md`.
- Python stdlib: `graphlib`, `tomllib`, `traceback` (documentação oficial do Python 3.11).

## Design Review Notes
- **Tamanho do design (~1 400 linhas)**: acima do alerta de 1 000 linhas do template. Avaliado o split em duas specs (execução multi-provider × explicabilidade/erros/reprodutibilidade). Mantida uma spec porque (1) o roadmap aprovado fixa a Wave D com as duas fronteiras (brief: "Contratos multi-provider", "Executor de plano local", "Workspace/grafo mínimos", "Explain/erros/reprodutibilidade"); (2) as duas metades compartilham os mesmos contratos de run (`ExecutionReceipt` com `kind`/`PlanRefs`, `VerificationResult`, `ReproducibilityInfo`) e o `explain` precisa conhecer os artefatos de plano — separá-las criaria uma dependência circular de revalidação. O volume vem sobretudo das definições de contrato e da tabela de rastreabilidade (100 critérios), não de componentes especulativos. As tarefas isolam as duas metades em grupos com `_Boundary:_` distintos para permitir implementação e revisão separadas.
- **Revisão cross-spec (sizing)**: a spec **não** é dividida agora — dividir é decisão do usuário. Em vez disso, o design documenta três costuras: (a) execução multi-provider, (b) integridade/explicabilidade/replay e (c) governança de erros; a tarefa 5.3 é um gate de integração no estilo `/kiro-validate-impl` sobre (a) antes de qualquer tarefa de (b)/(c), e a 9.3 é o gate de (b)+(c). `agentic-maintainability` re-checa a consolidação após cada metade.
- **Decisão em aberto para o usuário — opção de divisão**: D1 = (a) execução multi-provider (grupos 1–5 e `plan`/`workspace show` na CLI, ADR 0018) e D2 = (b)+(c) (explain/`ExplainReport`, verificação de hashes, replay, mensagens governadas, `--debug`, `docs/errors.md`, ADR 0019). Custos conhecidos: os contratos de run compartilhados (`ExecutionReceipt.kind`/`PlanRefs`, `VerificationResult`, `ReproducibilityInfo`, `CODE_FAMILIES`) ficariam em D1 e D2 seria um consumidor puro, com gatilho de revalidação D1 → D2; o `explain` de D1 continuaria o atual (despejo) até D2. Se escolhida, as costuras e o gate 5.3 já delimitam o corte sem reescrever tarefas.
- **ADRs**: números congelados — 0018 (modelo de execução multi-provider) e 0019 (taxonomia de erros e reprodutibilidade); `agentic-maintainability` os referencia por número.
- **CLI**: prefixos atuais preservados (`theforge: error:`, `theforge: persistence error:`, `theforge: internal error:`, `theforge: interrupted`), só com o sufixo `[código · família]`. `replay --mode verify` com divergência sai com 6, a mesma semântica de integridade do `explain`; o conjunto de exits continua `EXIT_BY_STATUS` ∪ `{1, 2, 5, 6, 70, 130}` (`CLI_FIXED_EXITS` de `agentic-maintainability`).
- **Revisão cross-spec (telemetria do plano)**: a afirmação anterior de que "o run do plano não tem `telemetry` próprio" foi removida; o run do plano grava `RunTelemetry` v1 e o receipt de plano registra `telemetry_sha256`, incluído na verificação de hashes.
- **Revisão cross-spec (tipos)**: `Reproducibility`, `EdgeEpistemic` e `MAX_HANDOFF_*` (e os demais limites) têm uma única definição em `contracts/types.py`; os módulos de contrato só importam.
- **Direção de imports**: na primeira passada o `GraphBuilder` ficava em `workspace/` e dependia de `NodeExecution` (definido no executor do `forger`), uma importação para a direita. Corrigido: `GraphBuilder` e os valores em memória `NodeExecution`/`SourceResult` vivem em `planning/` (`graph.py`, `execution.py`); `workspace/` só descreve.
- **Revisão do grafo de tarefas (independente)**: 1ª passada `NEEDS_FIXES` (códigos de erro definidos depois de tarefas que os usam; vínculo de replay sem dono no orquestrador; edição do registry fora do `_Boundary:_` da 2.1). Corrigido movendo os códigos de `ForgeError` para 1.1, o vínculo de replay para 4.1 e explicitando o registry na 2.1. 2ª passada: `PASS`.
