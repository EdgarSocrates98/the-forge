# Capabilities: taxonomia e catálogo

Uma capability é o que um provider declara saber fazer, por exemplo `pyspark.static-analysis`. É por ela que o routing escolhe um provider e que um pedido explícito (`--capability`) é atendido. Este documento traz as regras para nomear e evoluir capabilities e o catálogo inicial dos dois Forges reais. A decisão está registrada no [ADR 0017](adr/0017-capability-taxonomy.md).

Há dois tipos de regra:

- **Mecânicas.** O core aplica essas regras (`theforge.contracts.taxonomy.validate_taxonomy`) junto dos limites de manifest. Uma capability que viola alguma delas é excluída com aviso `FORGE-MANIFEST-TAXONOMY`. As outras capabilities do provider continuam. Se nenhuma restar, o provider fica `invalid`. A tabela está em [Regras mecânicas](#regras-mecânicas).
- **De revisão.** Escolha de namespace e subject, granularidade, sobreposição e versionamento são decididos por quem escreve o provider e conferidos em revisão. O core não tem conhecimento de domínio para julgar essas escolhas e não deve ter.

## Formato do ID
`namespace.subject[.qualifier]`: de 2 a 3 segmentos separados por ponto. Cada segmento começa com letra minúscula e só tem `a-z`, `0-9` e `-`. Exemplos: `pyspark.static-analysis`, `api.change-control`, `parquet.footer-analysis`.

## Namespace
- O primeiro segmento é a tecnologia, plataforma ou domínio **do objeto analisado** (`pyspark`, `glue`, `iceberg`, `api`), não o nome do provider. `spark-forge-aws.pyspark` está errado: a identidade do provider já está no manifest (`id`).
- Os namespaces `forge` e `theforge` são reservados ao próprio The Forge.
- Mais de um provider pode usar o mesmo namespace. O namespace não é dono de ninguém.
- Quando o objeto não tem uma tecnologia própria, use o domínio do trabalho (`finops`, `orchestration`, `data-quality`), nunca uma palavra genérica (`misc`, `tools`).

## Subject
- O segundo segmento diz **o que** a capability faz com o objeto: um substantivo de resultado (`static-analysis`, `runtime-analysis`, `access-analysis`, `change-control`) ou um verbo (`analyze`).
- Use o terceiro segmento (qualifier) só para separar variantes do mesmo subject que têm entradas ou resultados diferentes. Ele não é número de versão (veja [Versionamento](#versionamento)).
- Segmentos genéricos (`all`, `general`, `default`, `util`, …) são proibidos em qualquer posição: não dizem nada ao routing nem a quem lê a decisão.

## Granularidade
- Uma capability é um tipo de trabalho que o routing consegue distinguir **pelos sinais** (`keywords`, `file_globs`, `dependencies`). Se duas capabilities teriam os mesmos sinais, elas são uma só. Se ações diferentes da mesma capability precisam de sinais que não se cruzam, considere separá-las.
- Ferramentas nativas que trabalham sobre o mesmo objeto viram **ações** de uma capability, não capabilities separadas. Exemplo: `pyspark.static-analysis` tem as ações `pyspark` e `graph`.
- Não crie uma capability por ferramenta nativa (específica demais: o catálogo explode e os sinais se repetem). Também não crie uma capability para o Forge inteiro (genérica demais: o routing não consegue escolher, e um glob catch-all é rejeitado).

## Ações
- Formato `^[a-z][a-z0-9-]{0,31}$`. `default_action` é a ação usada quando o pedido não escolhe outra.
- O nome vem da superfície nativa. Spark Forge AWS: nome da tool sem `sparkforge_`/`analyze_`, com `_` → `-` (`sparkforge_analyze_event_log` → `event-log`). API Forge: o verbo final da CLI (`analyze`, `run`).
- Uma ação só é declarada se é read-only, roda offline e pode ser preenchida com arquivos do workspace a partir de um `ExecuteRequest` v1. Se não for o caso, ela fica fora do manifest e aparece em `limitations` com o motivo (veja [Superfície nativa não exposta](#superfície-nativa-não-exposta)). Uma capability sem nenhuma ação elegível não é declarada.

## Sobreposição
- Dois providers podem declarar o mesmo ID quando fazem o mesmo trabalho, com a mesma semântica de entrada e de resultado. Se a semântica difere, use outro subject ou qualifier.
- O core não tem regra de domínio para escolher entre eles. Vale o routing de sempre: num pedido explícito, desempate por trust e depois por id; por sinais, o ranking. A decisão registra a nota `capability-overlap` com os providers e, no pedido explícito, o critério de desempate. `theforge capabilities list|search` mostra `declared_by`.

## Versionamento
- Uma capability publicada não muda de significado. Acrescentar uma ação compatível mantém o ID. Remover uma ação ou mudar entrada ou resultado de forma incompatível cria uma **capability nova**, com ID novo, e deprecia a antiga.
- A versão do provider segue SemVer (`FORGE-MANIFEST-VERSION`). A regra de pacote, protocolo e schema está em [versioning.md](versioning.md).

## Depreciação
- `deprecated = true` marca a capability. `replaced_by = "<id>"` aponta a substituta e precisa ter formato de ID. Ela pode ser de outro provider e precisa ser diferente do próprio ID.
- A capability depreciada continua roteável, e a depreciação não muda ranking nem confiança. A decisão registra `capability-deprecated` (com `replaced_by` ou `no replacement declared`). `theforge capabilities list|search` avisa em stderr.
- A capability depreciada sai do manifest só numa versão posterior do provider, respeitando a janela de suporte de [versioning.md](versioning.md).

## Aliases
- `aliases` guarda nomes antigos de uma capability renomeada. Cada alias segue todas as regras de ID.
- Um alias é único no manifest e diferente de todo ID de capability do mesmo manifest. Se houver colisão, o manifest é inválido e o provider fica `invalid`.
- Num pedido explícito, o ID canônico vem primeiro: os providers que declaram o nome como alias só entram se nenhum o declarar como ID. A decisão registra `capability-alias` e usa sempre o ID canônico. Se o mesmo alias resolver para IDs canônicos diferentes em providers diferentes, o resultado é `ambiguous`, nunca um chute.
- O routing por sinais não usa aliases.

## Relações declaradas
`capabilities[].relations` alimenta o grafo de capabilities ([ADR 0027](adr/0027-capability-graph.md)) — declaração de intenção, nunca prova de comportamento:

- **Sobre capabilities** — `requires`, `complements`, `conflicts`, `can_verify`, `can_review`: o ref é `cap.id` para a capability do próprio provider e `provider/cap.id` entre providers. `can_verify`/`can_review` marcam candidatura a verificação/revisão independente ([ADR 0021](adr/0021-independent-verification.md)). Cycle 5 adiciona `verified_by` (a capability é *verificada por* outra — a direção é source→verifier) e `specializes` (a capability especializa outra).
- **Sobre artefatos** — `produces`, `consumes`: o ref é um tipo de artefato (`^[a-z][a-z0-9-]*(\.[a-z][a-z0-9-]*)*$`, ex.: `spark.analysis-report`). `consumes` também filtra quais artifacts do handoff o nó recebe antes do orçamento de bytes. Cycle 5 adiciona `accepts` (tipos de artefato que a capability aceita como entrada), `verifies` (tipos de artefato que ela declara verificar — claim, nunca prova) e `refines` (tipos que ela refina).
- Um alvo ausente do registry não invalida o manifest: a aresta é mantida e o alvo vira limitação do grafo (`declared relation targets not in the registry`).
- Flags de papel na mesma capability: `accepts_handoff` (lê o `handoff` do `ExecuteRequest`), `proposes_plans` (responde `plan` com `purpose="proposal"` — o planner semântico do tier-2, [ADR 0028](adr/0028-hybrid-planner.md)) e `resolves_ambiguity` (responde `resolve` com `RoutingProposal` — o resolver semântico de routing, [ADR 0025](adr/0025-semantic-routing-fallback.md)).

`theforge graph` mostra o grafo inteiro — relações declaradas e observadas — a partir do cache do registry, sem iniciar providers.

## Identidade de superfície e invalidação

Cada manifest resolvido ganha uma `ProviderSurfaceIdentity` (`theforge/ProviderSurfaceIdentity/v1`) com dois fingerprints computados pelo core: `capability_fingerprint` (o conjunto de capabilities — ids, ações, sinais) e `surface_fingerprint` (a superfície operacional inteira — capabilities + ops, protocolos, features, execution, trust e segurança declaradas). O adapter pode declarar `native_surface_fingerprint`, o hash da superfície nativa que gerou o manifest (ex.: o catálogo de tools do especialista) — fica registrado mas não participa dos fingerprints do core.

A regra de invalidação é uniforme: **mudança de superfície não herda nada**.

- **Registry cache**: uma entrada cacheada só é usada se o digest da entry, o `sha256` do manifest, ambos os fingerprints e o protocolo negociado conferirem com o estado atual — qualquer divergência descarta o cache e o provider é re-probeado (`manifest hash mismatch`, `cached surface fingerprint does not match…`).
- **Provider performance**: histórico é escopado por `(provider, capability, surface)` — `ProviderPerformance.score` só responde por entradas gravadas contra o fingerprint exato; um provider que muda de superfície recomeça do zero e o histórico antigo fica preservado, acessível mas sem efeito no ranking.
- **Capability graph**: reconstruído por comando a partir dos records já verificados pelo registry — não há snapshot persistido para ficar obsoleto; o `theforge graph` sempre reflete as superfícies vigentes.
- **Snapshots nativos**: o `native_surface_fingerprint` declarado é comparado pelo adapter ao fingerprint do especialista instalado — drift de superfície nativa (ex.: tools novas no catálogo do especialista) aparece como diferença de fingerprint registrada no receipt, não como dados velhos reutilizados em silêncio.

## Regras mecânicas
Fonte: `src/theforge/contracts/taxonomy.py`. Uma violação gera `FORGE-MANIFEST-TAXONOMY` e exclui só a capability violadora.

| Regra | Valor |
|---|---|
| Segmentos do ID | 2 a 3: `namespace.subject[.qualifier]` |
| Tamanho | cada segmento com 1 a 32 caracteres; ID com até 64 |
| Namespaces reservados | `forge`, `theforge` |
| Segmentos genéricos proibidos (em qualquer posição) | `all`, `any`, `misc`, `general`, `generic`, `default`, `other`, `stuff`, `tool`, `tools`, `util`, `utils` |
| Ação | `^[a-z][a-z0-9-]{0,31}$` |
| Alias | as mesmas regras do ID |
| `replaced_by` | só o formato de ID (padrão, segmentos, tamanhos); pode apontar para outro provider |

## Catálogo inicial
O catálogo vem da auditoria das superfícies reais (2026-10-03). Cada adapter monta o manifest a partir de um snapshot da superfície nativa que acompanha o pacote:

- **Spark Forge AWS** (`spark-forge-aws`): `native_catalog.json`, gravado do `sparkforge-aws` 0.5.0 (`python -m theforge_sparkforge_aws.record`). A origem de cada ação é uma tool MCP nativa. Uma tool é exposta só com `readOnlyHint = true`, `openWorldHint = false` e argumentos obrigatórios que o adapter sabe preencher com arquivos do workspace.
- **API Forge** (`api-forge`): `native_matrix.json`, a matriz de capabilities do API Forge 0.1.0 (por enquanto montada à mão, até ser gravada com `python -m theforge_apiforge.record`). A origem de cada capability é um verbo da CLI nativa mais o registro dela na matriz. Um registro é exposto só com estado `supported` ou `heuristic`, risco `read_only` e um verbo offline mapeado pelo adapter.

Os sinais de routing de cada capability ficam no `catalog.py` de cada adapter e são declarados no describe. O teste `tests/test_capability_catalog_doc.py` compara as duas tabelas abaixo com o describe em replay dos dois adapters. Ele falha se uma capability ou ação for exposta sem estar no catálogo, se o catálogo listar algo que não é exposto, ou se uma exclusão ou o motivo dela divergir do describe.

### Capabilities expostas
Todas são `read_only`, `supported` e rodam localmente e offline.

| Provider | Capability | Ações | Origem nativa |
|---|---|---|---|
| `spark-forge-aws` | `pyspark.static-analysis` | `pyspark`, `graph` | `sparkforge_analyze_pyspark`, `sparkforge_analyze_graph` |
| `spark-forge-aws` | `spark.runtime-analysis` | `event-log`, `sql-metrics`, `plan` | `sparkforge_analyze_event_log`, `sparkforge_analyze_sql_metrics`, `sparkforge_analyze_plan` |
| `spark-forge-aws` | `streaming.analysis` | `schema-registry`, `streaming-integrations` | `sparkforge_analyze_schema_registry`, `sparkforge_analyze_streaming_integrations` |
| `spark-forge-aws` | `glue.analysis` | `glue-resource-link` | `sparkforge_analyze_glue_resource_link` |
| `spark-forge-aws` | `emr.analysis` | `emr-cluster`, `emr-serverless`, `emr-eks` | `sparkforge_analyze_emr_cluster`, `sparkforge_analyze_emr_serverless`, `sparkforge_analyze_emr_eks` |
| `spark-forge-aws` | `athena.analysis` | `sql`, `athena-workgroup` | `sparkforge_analyze_sql`, `sparkforge_analyze_athena_workgroup` |
| `spark-forge-aws` | `iceberg.analysis` | `iceberg` | `sparkforge_analyze_iceberg` |
| `spark-forge-aws` | `parquet.footer-analysis` | `parquet-footer` | `sparkforge_analyze_parquet_footer` |
| `spark-forge-aws` | `terraform.analysis` | `terraform` | `sparkforge_analyze_terraform` |
| `spark-forge-aws` | `orchestration.analysis` | `step-functions`, `airflow-dag` | `sparkforge_analyze_step_functions`, `sparkforge_analyze_airflow_dag` |
| `spark-forge-aws` | `data-quality.analysis` | `data-quality` | `sparkforge_analyze_data_quality` |
| `spark-forge-aws` | `lakeformation.access-analysis` | `lakeformation-grants`, `iam-access` | `sparkforge_analyze_lakeformation_grants`, `sparkforge_analyze_iam_access` |
| `spark-forge-aws` | `cloudwatch.analysis` | `cloudwatch`, `cloudwatch-logs` | `sparkforge_analyze_cloudwatch`, `sparkforge_analyze_cloudwatch_logs` |
| `spark-forge-aws` | `platform.graph-analysis` | `dbt-artifacts`, `consumers` | `sparkforge_analyze_dbt_artifacts`, `sparkforge_analyze_consumers` |
| `spark-forge-aws` | `finops.performance-analysis` | `workload` | `sparkforge_analyze_workload` |
| `api-forge` | `api.analyze` | `analyze` | verbo `apiforge analyze --detail-level summary`; registro `api.analyze` da matriz (supported, read_only) |
| `api-forge` | `api.change-control` | `run` | verbo `apiforge change-control run`; registro `api.change-control` da matriz (supported, read_only) |
| `forge-doctor-data` | `data.scan` | `analyze` | seam `accept_request` (`kind=scan`) do `forge_doctor_data.core.forger`; HandoffBundle `forge-contracts/1` |
| `forge-doctor-data` | `data.verify` | `verify` | seam `check_conformance` de `forge_doctor_data.core.conformance` |
| `forge-doctor-api` | `api.diagnose` | `analyze` | seam `DoctorBoundary` (`handle` + `endpoint_dict`) de `forge_doctor_api.handoff.boundary` (spec 070); `ApiHandoffBundle` v2 + envelope `ForgeHandoff` + `diagnostic-manifest` |
| `forge-doctor-api` | `api.verify` | `verify` | strict parse `ApiHandoffBundle.from_dict` / `ForgeHandoff.parse` + integridade `body_sha256` (v2) |

### Superfície nativa não exposta
O motivo é o texto exato que o adapter publica em `limitations` no describe. Ações e capabilities excluídas são listadas uma a uma; ferramentas sem capability são agrupadas pelo motivo.

| Provider | Capability | Ação | Origem nativa | Motivo |
|---|---|---|---|---|
| `spark-forge-aws` | `pyspark.static-analysis` | `call-graph` | `sparkforge_analyze_call_graph` | `consumes facts produced by another Spark Forge AWS analyzer, not a workspace file` |
| `spark-forge-aws` | `streaming.analysis` | `streaming` | `sparkforge_analyze_streaming` | `requires the dump vocabulary in 'artifact', which workspace files do not identify` |
| `spark-forge-aws` | `streaming.analysis` | `transport` | `sparkforge_analyze_transport` | `requires the dump vocabulary in 'artifact', which workspace files do not identify` |
| `spark-forge-aws` | `streaming.analysis` | `flink` | `sparkforge_analyze_flink` | `requires the dump vocabulary in 'artifact', which workspace files do not identify` |
| `spark-forge-aws` | `streaming.analysis` | `cdc` | `sparkforge_analyze_cdc` | `requires the dump vocabulary in 'artifact', which workspace files do not identify` |
| `spark-forge-aws` | `streaming.analysis` | `event-driven` | `sparkforge_analyze_event_driven` | `reads a dump with no native file name or directory convention, so no workspace file can be bound to it` |
| `spark-forge-aws` | `streaming.analysis` | `streaming-ops` | `sparkforge_analyze_streaming_ops` | `reads a dump with no native file name or directory convention, so no workspace file can be bound to it` |
| `spark-forge-aws` | `streaming.analysis` | `streaming-composition` | `sparkforge_analyze_streaming_composition` | `consumes facts produced by another Spark Forge AWS analyzer, not a workspace file` |
| `spark-forge-aws` | `streaming.analysis` | `glue-streaming` | `sparkforge_analyze_glue_streaming` | `reads a dump with no native file name or directory convention, so no workspace file can be bound to it` |
| `spark-forge-aws` | `glue.analysis` | `glue-job-runs` | `sparkforge_analyze_glue_job_runs` | `requires 'job_name', which no ExecuteRequest v1 field carries` |
| `spark-forge-aws` | `glue.analysis` | `catalog-schema` | `sparkforge_analyze_catalog_schema` | `reads a dump with no native file name or directory convention, so no workspace file can be bound to it` |
| `spark-forge-aws` | `glue.analysis` | `glue-dependency-audit` | `sparkforge_glue_dependency_audit` | `requires the Glue version in 'glue', which no ExecuteRequest v1 field carries` |
| `spark-forge-aws` | `iceberg.analysis` | `iceberg-assess-upgrade` | `sparkforge_iceberg_assess_upgrade` | `requires the source and target format versions, which no ExecuteRequest v1 field carries` |
| `spark-forge-aws` | `terraform.analysis` | `terraform-diff` | `sparkforge_analyze_terraform_diff` | `compares two module directories ('before' and 'after'); one workspace holds only one state` |
| `spark-forge-aws` | `orchestration.analysis` | `controlm-jobs` | `sparkforge_analyze_controlm_jobs` | `reads a dump with no native file name or directory convention, so no workspace file can be bound to it` |
| `spark-forge-aws` | `orchestration.analysis` | `sfn-history` | `sparkforge_analyze_sfn_history` | `reads a dump with no native file name or directory convention, so no workspace file can be bound to it` |
| `spark-forge-aws` | `orchestration.analysis` | `orchestration` | `sparkforge_analyze_orchestration` | `reads a dump with no native file name or directory convention, so no workspace file can be bound to it` |
| `spark-forge-aws` | `data-quality.analysis` | `dq-ai` | `sparkforge_analyze_dq_ai` | `reads a dump with no native file name or directory convention, so no workspace file can be bound to it` |
| `spark-forge-aws` | `data-quality.analysis` | `dq-ai-assess` | `sparkforge_dq_ai_assess` | `consumes facts produced by another Spark Forge AWS analyzer, not a workspace file` |
| `spark-forge-aws` | `data-quality.analysis` | `data-observability` | `sparkforge_analyze_data_observability` | `reads a dump with no native file name or directory convention, so no workspace file can be bound to it` |
| `spark-forge-aws` | `lakeformation.access-analysis` | `lakeformation-access-graph` | `sparkforge_lakeformation_access_graph` | `consumes facts produced by another Spark Forge AWS analyzer, not a workspace file` |
| `spark-forge-aws` | `lakeformation.access-analysis` | `lakeformation-matrix` | `sparkforge_lakeformation_matrix` | `answers from the Spark Forge AWS's own version matrix; it takes no workspace file` |
| `spark-forge-aws` | `lakeformation.access-analysis` | `lakeformation-architect` | `sparkforge_lakeformation_architect` | `takes the architecture declaration as a JSON argument, not a workspace file` |
| `spark-forge-aws` | `cloudwatch.analysis` | `error-signatures` | `sparkforge_analyze_error_signatures` | `consumes facts produced by another Spark Forge AWS analyzer, not a workspace file` |
| `spark-forge-aws` | `platform.graph-analysis` | `platform-graph` | `sparkforge_analyze_platform_graph` | `reads a dump with no native file name or directory convention, so no workspace file can be bound to it` |
| `spark-forge-aws` | `platform.graph-analysis` | `platform-ecosystem` | `sparkforge_analyze_platform_ecosystem` | `reads a dump with no native file name or directory convention, so no workspace file can be bound to it` |
| `spark-forge-aws` | `platform.graph-analysis` | `lakehouse-catalog` | `sparkforge_analyze_lakehouse_catalog` | `reads a dump with no native file name or directory convention, so no workspace file can be bound to it` |
| `spark-forge-aws` | `platform.graph-analysis` | `duckdb-microscope` | `sparkforge_analyze_duckdb_microscope` | `reads a dump with no native file name or directory convention, so no workspace file can be bound to it` |
| `spark-forge-aws` | `platform.graph-analysis` | `forge-lab` | `sparkforge_analyze_forge_lab` | `reads a dump with no native file name or directory convention, so no workspace file can be bound to it` |
| `spark-forge-aws` | `platform.graph-analysis` | `s3-listing` | `sparkforge_analyze_s3_listing` | `reads a dump with no native file name or directory convention, so no workspace file can be bound to it` |
| `spark-forge-aws` | `migration.assessment` | `migration-assess` | `sparkforge_migration_assess` | `requires the source and target releases, which no ExecuteRequest v1 field carries` |
| `spark-forge-aws` | `migration.assessment` | `release-describe` | `sparkforge_release_describe` | `requires the platform and release, which no ExecuteRequest v1 field carries` |
| `spark-forge-aws` | `migration.assessment` | `release-diff` | `sparkforge_release_diff` | `requires two platform/release pairs, which no ExecuteRequest v1 field carries` |
| `spark-forge-aws` | `migration.assessment` | `controlm-describe` | `sparkforge_controlm_describe` | `requires the Control-M version, which no ExecuteRequest v1 field carries` |
| `spark-forge-aws` | `migration.assessment` | — | `sparkforge_migration_assess`, `sparkforge_release_describe`, `sparkforge_release_diff`, `sparkforge_controlm_describe` | `no action is read-only, offline and fillable from workspace files` |
| `spark-forge-aws` | `finops.performance-analysis` | `benchmark` | `sparkforge_benchmark` | `compares the facts of two runs ('before_path' and 'after_path'); one workspace holds only one state` |
| `spark-forge-aws` | `finops.performance-analysis` | `workload-profile` | `sparkforge_workload` | `consumes facts produced by another Spark Forge AWS analyzer, not a workspace file` |
| `spark-forge-aws` | `finops.performance-analysis` | `capacity` | `sparkforge_capacity` | `consumes facts produced by another Spark Forge AWS analyzer, not a workspace file` |
| `spark-forge-aws` | `finops.performance-analysis` | `finops` | `sparkforge_finops` | `consumes facts produced by another Spark Forge AWS analyzer, not a workspace file` |
| `spark-forge-aws` | `finops.performance-analysis` | `tune` | `sparkforge_tune` | `consumes facts produced by another Spark Forge AWS analyzer, not a workspace file` |
| `spark-forge-aws` | `finops.performance-analysis` | `gain` | `sparkforge_gain` | `consumes facts produced by another Spark Forge AWS analyzer, not a workspace file` |
| `spark-forge-aws` | `finops.performance-analysis` | `simulate` | `sparkforge_simulate` | `consumes facts produced by another Spark Forge AWS analyzer, not a workspace file` |
| `spark-forge-aws` | `finops.performance-analysis` | `economy-report` | `sparkforge_economy_report` | `reads the Spark Forge AWS run ledger by 'run_id', not workspace files` |
| `spark-forge-aws` | — | — | `sparkforge_collect_athena_workgroup`, `sparkforge_collect_cloudwatch`, `sparkforge_collect_cloudwatch_logs`, `sparkforge_collect_emr_cluster`, `sparkforge_collect_emr_eks`, `sparkforge_collect_emr_serverless`, `sparkforge_collect_event_log`, `sparkforge_collect_glue_job`, `sparkforge_collect_glue_job_runs`, `sparkforge_collect_glue_resource_link`, `sparkforge_collect_iam_access`, `sparkforge_collect_iceberg_metadata`, `sparkforge_collect_lakeformation`, `sparkforge_collect_managed_flink`, `sparkforge_collect_parquet_footer`, `sparkforge_collect_schema_registry`, `sparkforge_collect_streaming_integrations` | `call AWS APIs over the network and write collection artifacts (openWorldHint)` |
| `spark-forge-aws` | — | — | `sparkforge_agentops_baseline`, `sparkforge_arbitrate`, `sparkforge_case_open`, `sparkforge_case_update`, `sparkforge_change_propose`, `sparkforge_change_sandbox`, `sparkforge_code_context`, `sparkforge_code_export`, `sparkforge_code_path`, `sparkforge_code_read`, `sparkforge_code_search`, `sparkforge_code_shape`, `sparkforge_code_status`, `sparkforge_code_symbol`, `sparkforge_code_sync`, `sparkforge_debate_next`, `sparkforge_debate_start`, `sparkforge_debate_submit`, `sparkforge_funcval_compare`, `sparkforge_funcval_plan`, `sparkforge_receipt_emit`, `sparkforge_report_sign`, `sparkforge_scan`, `sparkforge_sdd_stamp` | `write local Spark Forge AWS state (case, debate, receipts, sandbox, code index) into the repository (readOnlyHint false)` |
| `spark-forge-aws` | — | — | `sparkforge_doctor` | `probes the AWS credential chain and the host environment` |
| `spark-forge-aws` | — | — | `sparkforge_collect_verify` | `operates on AWS collection artifacts registered in the local collection manifest` |
| `spark-forge-aws` | — | — | `sparkforge_fuse`, `sparkforge_judge`, `sparkforge_root_cause`, `sparkforge_rules_lookup`, `sparkforge_validate_output` | `consumed internally by the analysis actions or takes no workspace file input` |
| `spark-forge-aws` | — | — | `sparkforge_agentops_compare`, `sparkforge_agentops_critical_path`, `sparkforge_agentops_inspect`, `sparkforge_agentops_timeline`, `sparkforge_case_get`, `sparkforge_change_plan`, `sparkforge_debate_referee`, `sparkforge_decision_evaluate`, `sparkforge_next_step`, `sparkforge_playbook`, `sparkforge_proof`, `sparkforge_receipt_verify`, `sparkforge_report_github`, `sparkforge_report_verify`, `sparkforge_resume`, `sparkforge_runtime_detect`, `sparkforge_sdd_check`, `sparkforge_sdd_status` | `works on Spark Forge AWS case, run, report or session state, not on workspace inputs` |
| `spark-forge-aws` | — | — | `sparkforge_context_expand`, `sparkforge_context_inspect`, `sparkforge_context_start`, `sparkforge_doctor_agentic`, `sparkforge_knowledge_drift`, `sparkforge_knowledge_path`, `sparkforge_pack_list`, `sparkforge_policy_explain`, `sparkforge_telemetry_export` | `host and agent plumbing (context gateway, doctor, knowledge, packs, policy, telemetry), not an analysis` |
| `api-forge` | `api.next-step` | — | registro `api.next-step` da matriz (supported, read_only) | `the native verb needs --phase, which ExecuteRequest v1 has no field for` |
| `api-forge` | `api.provenance` | — | registro `api.provenance` da matriz (supported, read_only) | `no single offline verb produces it` |
| `api-forge` | `cicd.inspect` | — | registro `cicd.inspect` da matriz (heuristic, read_only) | `no single offline verb produces it` |
| `api-forge` | `cicd.inspect-run` | — | registro `cicd.inspect-run` da matriz (heuristic, read_only) | `no single offline verb produces it` |
| `api-forge` | `cicd.verify-runtime` | — | registro `cicd.verify-runtime` da matriz (supported, read_only) | `its probes run fixtures under the API Forge repository tests/fixtures, absent from an installed package` |
| `api-forge` | `cloud.inspect` | — | registro `cloud.inspect` da matriz (heuristic, read_only) | `no single offline verb produces it` |
| `api-forge` | `cloud.verify-runtime` | — | registro `cloud.verify-runtime` da matriz (supported, read_only) | `its probes run fixtures under the API Forge repository tests/fixtures, absent from an installed package` |
| `api-forge` | `database.inspect` | — | registro `database.inspect` da matriz (heuristic, read_only) | `no single offline verb produces it` |
| `api-forge` | `database.verify-runtime` | — | registro `database.verify-runtime` da matriz (supported, read_only) | `its probes run fixtures under the API Forge repository tests/fixtures, absent from an installed package` |
| `api-forge` | `external.apply` | — | registro `external.apply` da matriz (unsupported, external_mutation) | `state 'unsupported' is not one of supported, heuristic; risk 'external_mutation' is not read_only; no offline verb is mapped to it by this adapter` |
| `api-forge` | `frontend.inspect` | — | registro `frontend.inspect` da matriz (heuristic, read_only) | `no single offline verb produces it` |
| `api-forge` | `frontend.verify-runtime` | — | registro `frontend.verify-runtime` da matriz (supported, read_only) | `its probes run fixtures under the API Forge repository tests/fixtures, absent from an installed package` |
| `api-forge` | `git.plan` | — | registro `git.plan` da matriz (unresolved, local_reversible) | `state 'unresolved' is not one of supported, heuristic; risk 'local_reversible' is not read_only; no offline verb is mapped to it by this adapter` |
| `api-forge` | `git.read-context` | — | registro `git.read-context` da matriz (heuristic, read_only) | `needs network access and a Git host token` |
| `api-forge` | `integration.github-issues` | — | registro `integration.github-issues` da matriz (supported, read_only) | `needs network access (and, for some, a host credential)` |
| `api-forge` | `integration.health` | — | registro `integration.health` da matriz (supported, read_only) | `needs network access (and, for some, a host credential)` |
| `api-forge` | `integration.json-read` | — | registro `integration.json-read` da matriz (supported, read_only) | `needs network access (and, for some, a host credential)` |
| `api-forge` | `messaging.inspect` | — | registro `messaging.inspect` da matriz (heuristic, read_only) | `no single offline verb produces it` |
| `api-forge` | `messaging.verify-runtime` | — | registro `messaging.verify-runtime` da matriz (supported, read_only) | `its probes run fixtures under the API Forge repository tests/fixtures, absent from an installed package` |
