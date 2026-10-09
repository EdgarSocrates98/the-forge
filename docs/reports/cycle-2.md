# Relatório final do Cycle 2

> **STATUS: CLOSED** — o gate de fechamento do Cycle 2.1 (Waves A–I) está em
> [cycle-2-final](cycle-2-final.md).
>
> Estado na geração: 2026-10-04. Para o estado validado depois do merge das Waves B–E, ver
> [Post-Merge Validation Update](#post-merge-validation-update) ao final deste documento.

- Data: 2026-10-04
- Versões vigentes (matriz de [versionamento](../versioning.md)): The Forge 0.1.0, Forge Protocol `forge/v1`, `theforge-sparkforge-adapter` 0.1.0 com `sparkforge-aws` `>=0.5.0,<0.6.0`, `theforge-apiforge-adapter` 0.1.0 com `apiforge` `>=0.1.0,<0.2.0`.
- Specs do ciclo, citadas só pelo nome: `cycle2-reality-hardening` (Wave A), `real-provider-integration` (Wave B), `context-intelligence-v2` (Wave C), `cross-forge-foundation` (Wave D) e `agentic-maintainability` (Wave E). As specs e os relatórios de gate ficam locais e fora do git ([ADR 0020](../adr/0020-agentic-assets-canonical-source.md)); este relatório resume o que eles registram.
- Fontes: histórico git das branches do ciclo, os relatórios de gate e as notas de implementação de cada spec, `scripts/bench/*.json` com [performance](../performance.md), os runs do GitHub Actions e o [índice de ADRs](../adr/README.md). Nenhum número aparece aqui sem origem; o que não tem origem está marcado "não medido".

## Implementado

| Wave | Spec | Commits | Entrega | ADRs |
|---|---|---:|---|---|
| A | `cycle2-reality-hardening` | 40 | Invariantes semânticas e leitura estrita de contratos; Forge Protocol resistente a providers adversariais (kill da árvore de processos, negociação de versão estrita, conferência de `op` e `producer` em todo envelope); routing por presença de tipos de sinal, resistente a inflação; cache do registry no diretório de cache do usuário, com fingerprint do provider e revalidação antes do routing; ambiente mínimo sem credenciais para providers; policy `allow`/`ask`/`deny` com `RiskAssessment` e `--approve`; CI em Linux e Windows, macOS semanal e workflow de providers reais | [0009](../adr/0009-registry-cache-location.md), [0010](../adr/0010-policy-model.md), [0011](../adr/0011-ci-support-matrix.md), [0012](../adr/0012-os-sandbox-research.md), [0013](../adr/0013-provider-identity.md) |
| B | `real-provider-integration` | 33 | Dois adapters instaláveis em `adapters/` (Spark Forge e API Forge) com backends `live` e `replay`; manifests derivados de snapshots gravados das superfícies nativas; versão de provider em SemVer 2.0.0 e matriz de compatibilidade; taxonomia de capabilities com aliases, depreciação e sobreposição; suíte de conformance em replay e testes contra os Forges reais (`-m real_provider`) | [0014](../adr/0014-provider-adapter-location.md), [0017](../adr/0017-capability-taxonomy.md) |
| C | `context-intelligence-v2` | 22 | `ContextPack` por tiers; relevância por sinais com prioridade fixa; negociação de contexto adicional com o provider; reverificação do contexto depois do execute (drift); consulta git somente leitura endurecida; cache de fingerprints fora do workspace; perfis `economy`/`balanced`/`max` numa tabela única; telemetria por run (`RunTelemetry`) ligada ao receipt; benchmark stdlib com baseline e budgets | [0015](../adr/0015-context-intelligence.md), [0016](../adr/0016-git-read-only-signals.md) |
| D | `cross-forge-foundation` | 37 | `theforge plan`: decomposição determinística em planos multi-provider, ordem topológica, handoff estruturado entre nós, síntese, grafo do workspace e plano de instalação (só planejado); descritor de workspace multi-repo (`workspace-descriptor`); `VerificationResult` que separa auto-relato do provider da conferência do Forge; reprodutibilidade por run e por plano; `explain --json` versionado (`ExplainReport` v1) com verificação de hashes; `replay` nos modos `render`, `verify` e `execute`; taxonomia de erros por família e CLI governada (`[código · família]`, `--debug`, exit 6 para divergência de integridade) | [0018](../adr/0018-multi-provider-execution.md), [0019](../adr/0019-error-taxonomy-and-reproducibility.md) |
| E | `agentic-maintainability` | 14 | Auditoria de paridade dos assets agentic entre Claude Code, Codex e Devin (`scripts/agentic/audit_assets.py` com `agentic.toml`) e teste offline de drift; `CLAUDE.md` e `AGENTS.md` reescritos como invariantes com escopo e regras curtas, com orçamento de tamanho; comandos legados `.claude/commands/kiro/` removidos; guia [desenvolvimento com agentes](../agentic.md); índice de ADRs com o mapa das oito decisões exigidas; README e documentos consolidados; verificação mecânica de links, índice, nome canônico da CLI, exit codes, ADRs e deste relatório; sdist sem assets agentic nem specs locais | [0020](../adr/0020-agentic-assets-canonical-source.md) |

Os commits contam o histórico de cada wave sem merges: Wave A de `47af0b8` (merge do PR #2) até `fe8f5a1`; Waves B–E pelo escopo da spec na mensagem, de `main` até `feat/cycle2-wave-e` (106 commits no total).

## Mudanças de arquitetura

- **Pacotes novos em `src/theforge/`:** `context/` (tiers, relevância, git, fingerprints, reverificação), `forger/telemetry.py`, `profiles.py`, `planning/` (decomposição, ordem, validação, handoff, síntese, grafo, estimativa, instalação), `workspace/` (descritor e relações), `explain/` (verificação de hashes e relatório), `forger/{plan_executor,verification,reproducibility,replay}.py` e `diagnostics.py`. A cadeia de imports `contracts → … → runs → explain → forger → cli` foi verificada sem violação por script AST nos gates da Wave D ([arquitetura](../architecture.md)).
- **Contratos:** os schemas publicados passaram de 11 (ciclo 1) para 12 na Wave A (`RiskAssessment`), 13 nas Waves B e C (`RunTelemetry`) e 24 na Wave D (`ExecutionPlan`, `PlanRequest`, `PlanEstimate`, `PlanResult`, `Handoff`, `WorkspaceDescriptor`, `WorkspaceGraph`, `VerificationResult`, `InstallationPlan`, `ExplainReport`, `Diagnostic`). Os campos novos em contratos existentes são aditivos; runs gravados antes deles continuam legíveis, com "não registrado" e reprodutibilidade `unknown` ([protocolo](../protocol.md)).
- **Artefatos do run:** além de `task`, `routing`, `context`, `result` e `receipt`, um run grava `risk` (A), `context-r1`/`context-r2` e `telemetry` (C) e `verification`; um run de plano grava `workspace-descriptor`, `plan`, `plan-result`, `graph`, `installation` e `telemetry`, e cada nó pode ter `handoff`; `diagnostic` só com `--debug` (D). Todos passam por `RunStore.write` (redação, hash e releitura estrita).
- **Ops do protocolo:** `plan` saiu de reservada na Wave D; `verify` e `estimate` continuam reservadas. Padrões `route` e `pipeline` executam; `delegate`, `parallel` e `debate` são representáveis e recusados ([ADR 0018](../adr/0018-multi-provider-execution.md)).
- **Adapters fora do core:** os Forges reais entram por pacotes em `adapters/`, instalados no interpretador de cada especialista e falando só Forge Protocol; o core não importa `sparkforge` nem `apiforge` ([ADR 0014](../adr/0014-provider-adapter-location.md)).
- **CLI:** comandos `plan`, `workspace show` e `replay`; `explain` versionado; mensagens de erro governadas com código e família ([CLI](../cli.md), [códigos de erro](../errors.md)). `planned` sai com 0.

## Integração real Spark/API

- **Adapters:** Spark Forge expõe 15 capabilities com 26 ações; API Forge expõe `api.analyze` e `api.change-control`. Só capabilities read-only e offline são declaradas; o resto vai para `limitations` do manifest com o motivo ([catálogo](../capabilities.md), [ADR 0017](../adr/0017-capability-taxonomy.md)).
- **Ambiente local da prova:** `sparkforge-aws` 0.5.0 num venv Python 3.11.15 e `apiforge` 0.1.0 num venv Python 3.12.13, apontados por `THEFORGE_REAL_SPARKFORGE_PYTHON` e `THEFORGE_REAL_APIFORGE_PYTHON` ([providers reais](../real-providers.md)). As superfícies nativas observadas: 136 tools no Spark Forge e 21 capabilities no API Forge.
- **Resultado:** em 2026-10-04, `-m real_provider` passou com os dois Forges reais executando localmente, sem skip e sem drift entre o replay gravado e a superfície viva (16 testes); depois da Wave D, 17 testes, incluindo a prova cross-forge.
- **Erratas de design corrigidas na implementação:** Spark `pyspark.static-analysis` usa `detail_level = "normal"` (o `sparkforge_judge` real rejeita facts de `summary`); o backend live do Spark roda cada tool num processo filho, para fechar o journal SQLite nativo antes da limpeza; o health do API Forge deixou de chamar `apiforge doctor` e confere Python, import, versão e CLI, porque o custo real estava no `import apiforge.cli` (3–17 s sob carga), não no doctor.
- **Contenção:** o cwd de cada execute é reduzido aos artifacts declarados; `.sparkforge/` e `.apiforge/` nunca ficam no workspace. O diretório `.forge/runs/<id>/work/` não passa por redação ([segurança](../security.md)).

## Contexto e economy

- O `ContextPack` é montado por tiers com orçamento do perfil; o arquivo citado na intenção e os manifests de dependência da raiz entram primeiro. O provider pode pedir contexto adicional em até 2 rodadas extras, cada uma com o timeout inteiro do perfil (pior caso no perfil `max`: 3 × 600 s ≈ 30 min).
- Depois do execute, o contexto é reverificado conforme o perfil (nenhum item em `economy`, todos em `max`); drift rebaixa a evidência afetada e vira limitação `context-drift: <path>`.
- O cache de fingerprints fica fora do workspace (`<cache>/context/`), descarta entradas com caminho parecido com segredo e se desliga se o diretório de cache cair dentro do workspace.
- A telemetria por run registra fases, contadores e tokens honestos (`unknown` quando o provider não mede). `fallbacks_used` conta os providers não saudáveis tentados, incluindo o primário, então `economy` pode registrar 1.
- Medido: a seleção de contexto limitada por perfil deixou o contexto frio cerca de 8× (1 000 arquivos) e 17× (10 000 arquivos) mais rápido; o cache quente evita reler os 64 arquivos selecionados, mas não reduz o tempo de parede nesse tamanho ([performance](../performance.md)). Os números estão em "Resultados medidos".

## Hardening de segurança

Correções de segurança feitas durante o ciclo, todas com teste de regressão:

- **Cache do registry** (Wave A, `fe8f5a1`): o documento do cache passa por `security.redact`; quando a redação mudaria algo, o provider não é cacheado e é descrito a cada uso.
- **Producer do envelope de execute** (Wave A, `3bad9a5`): o `producer` do envelope do execute passou a ser conferido, como já era em describe e health.
- **Lazy fetch do git** (Wave C, `f94dcc9`): o design dizia que `core.fsmonitor` e filtros eram as únicas chaves que fazem o `status` executar programa; num clone parcial, o lazy fetch executa o transporte do remoto do repositório. O git roda com `GIT_NO_LAZY_FETCH=1` e `GIT_ALLOW_PROTOCOL=none` ([ADR 0016](../adr/0016-git-read-only-signals.md)).
- **`workspace.toml` simbólico** (Wave D, `2b301a5`): um `.forge/config` ou `workspace.toml` que seja link simbólico é ignorado com aviso, em vez de ler arquivo fora do workspace.
- **Oráculo de existência na verificação de hashes** (Wave D, `5c475c8`): um artifact cujo caminho escapa de `work/` é reportado como ausente e nunca é sondado no disco.
- **Integridade das entradas do replay** (Wave D, `2664deb`): `replay --mode execute` reconstruía a tarefa e conferia drift a partir de `task.json` e `context*.json` sem conferir os hashes gravados; agora recusa quando receipt, tarefa, routing, handoff ou rodadas de contexto divergem.
- **Traceback de provider na CLI** (Wave D, `04508f9`): um traceback bruto no detalhe de erro é reduzido à última linha na saída humana; toda mensagem é redigida e sem caracteres de controle.
- **sdist vazando specs locais** (Wave E, `41f76f3`): o sdist incluía `.kiro/`, `.tokensave/`, os diretórios agentic e as instruções de host; agora são excluídos e um teste de empacotamento fixa as exclusões.
- **ReDoS na auditoria** (Wave E, `b41d702`): padrões de placeholder com mais de 200 caracteres ou com quantificadores aninhados são recusados como erro de configuração.

Varredura Snyk (registrada na Wave A): baseline de 8 notas LOW pré-existentes. Uma nota nova em `scripts/ci/check_zero_deps.py` (abertura do wheel com caminho fornecido pelo CI) sumiu quando o script passou a ler o wheel por listagem de diretório (`01b9f19`), e a contagem voltou ao baseline.

## CI

- **Workflows** ([ADR 0011](../adr/0011-ci-support-matrix.md), [arquitetura](../architecture.md)): `ci.yml` (gate de PR em Ubuntu e Windows × Python 3.11–3.14, mais o job `package`), `compat.yml` (macOS, semanal) e `real-providers.yml` (semanal e manual, nunca bloqueia PR). Actions fixadas por SHA.
- **Runs no GitHub:** só o workflow `ci` rodou, quatro vezes, todas sobre a Wave A (PR #3): a primeira falhou (run 37128243774) e as três seguintes passaram, incluindo o push do merge em `main` (run 37129740964, 2026-10-03, 10 jobs verdes). A prova POSIX do kill da árvore e do isolamento de ambiente em Linux, que não roda nesta máquina, foi feita por esses runs.
- **Ainda não rodado no GitHub:** as Waves B–E (nenhuma delas foi enviada ao remoto), `compat.yml` e `real-providers.yml`. O `ci.yml` das Waves B–E também instala os adapters, mudança que nenhum run exercitou.
- **Testes locais:** a suíte offline roda em 3 blocos sequenciais nesta máquina, porque uma execução única foi encerrada por falta de memória. Todo arquivo de teste tem categoria (`test_harness.py`).

## Prova cross-forge

**Executada com os Forges reais**, localmente, em 2026-10-04, em Windows, com `sparkforge-aws` 0.5.0 (Python 3.11.15) e `apiforge` 0.1.0 (Python 3.12.13): `tests/test_cross_forge_real.py::test_proof_task_runs_across_the_real_spark_forge_and_api_forge` passou dentro de `-m real_provider` (17 passed). A tarefa de prova ("projete um pipeline Spark que produza dados para uma API") virou o plano `pyspark.static-analysis` → `api.analyze`, terminou `ok`, e o nó da API recebeu a evidência do Spark (16 itens de handoff no run real, 12 no replay).

O que a prova não mostra, para não ser lida além do que rodou:

- O workspace de prova não gera findings; os ids nativos foram conferidos nos resultados dos nós e nos itens de handoff, não em `synthesis.findings`.
- O API Forge real não declara `accepts_handoff`: recebe o handoff, ignora o campo e o nó registra a limitação `handoff-use-undeclared`.
- A gravação de replay do API Forge para o cenário cross foi montada à mão a partir de um run live em Windows, e a checagem de drift live ainda não cobre esse cenário.
- A prova não rodou no CI: `real-providers.yml` nunca executou no GitHub.

A premissa do design de que o Python 3.12 do API Forge faltaria nesta máquina não se confirmou (3.12.13 foi instalado), então não houve substituto offline no lugar da prova real. Os substitutos offline existem e continuam na suíte padrão: fixtures (`tests/test_plan_flow.py`, `tests/test_cli_plan.py`) e adapters reais em replay (`tests/test_cross_forge_replay.py`), além do e2e em subprocesso `plan --execute` → `explain` (`tests/test_e2e.py`).

## Resultados medidos

| Métrica | Valor | Origem |
|---|---|---|
| CI no GitHub, Wave A | 10 jobs verdes (Ubuntu e Windows × 3.11–3.14, `package` em Ubuntu e Windows 3.11) | workflow `ci`, run 37129740964 (push em `main`, 2026-10-03), lido com `gh run view` em 2026-10-04 |
| Suíte offline ao fim da Wave A | 905 passed, 2 skipped; `-m slow` 2 passed; `-m security` 290 passed; 913 passed após os follow-ups | `python -m pytest` (Windows, Python 3.11), 2026-10-03, validação final de `cycle2-reality-hardening` |
| Suíte offline ao fim da Wave D | 2719 passed, 5 skipped, 0 failed (73 arquivos, 3 blocos) | `python -m pytest -p no:cacheprovider` em 3 blocos, 2026-10-04, gate 9.3 de `cross-forge-foundation` |
| `-m slow` ao fim da Wave D | 4 passed | `python -m pytest -m slow`, 2026-10-04, gate 9.3 de `cross-forge-foundation` |
| Suíte offline completa com a Wave E | não medido | não rodada inteira nesta consolidação (restrição de memória); só os arquivos de teste da Wave E |
| Forges reais, Wave B | 16 passed em 31,9 s, sem skip e sem drift | `python -m pytest -m real_provider`, 2026-10-04, gate final de `real-provider-integration` (commit `6746334`) |
| Forges reais com a prova cross-forge | 17 passed | `python -m pytest -m real_provider`, 2026-10-04, gate 9.3 de `cross-forge-foundation` |
| Itens de handoff Spark → API na prova | 16 (real), 12 (replay) | prova real e replay, 2026-10-04 (tarefa 8 de `cross-forge-foundation`) |
| Schemas publicados | 24 (11 no ciclo 1) | `git ls-tree` de `schemas/` nas branches, 2026-10-04; paridade de schemas no gate 9.3 |
| Dependências de runtime | 0 (`dependencies = []`) | `pyproject.toml`; gate 9.3 de `cross-forge-foundation`, 2026-10-04 |
| `context_1k_cold` (mediana) | 478,228 ms → 61,114 ms | [performance](../performance.md): `baseline.json` (10 repetições, `d77ba5f`) e `final.json` (`--quick`, 3 repetições, `68eb7ef`), 2026-10-04 |
| `context_10k_cold` (mediana) | 3 348,102 ms → 196,159 ms | [performance](../performance.md), mesmas fontes |
| Regressões contra os budgets | 0 em 11 medições | `run_bench.py --check scripts/bench/budgets.json` sobre `final.json`, 2026-10-04 ([performance](../performance.md)) |
| Custo do git por run dentro de repositório | ~0,7–1,3 s (5 processos, orçamento de 5 s) | observado nos testes desta máquina; [performance](../performance.md) |
| Custo do processo filho por execute live do Spark | 3–5 s | observado na implementação de `real-provider-integration` (tarefa 4.4), 2026-10-04 |
| Custo do `import apiforge.cli` | 3–17 s sob carga | observado na implementação de `real-provider-integration` (tarefa 7.2), 2026-10-04 |
| Auditoria dos assets agentic | exit 0, nenhum achado de falha (32 `host-syntax`, 3 `accepted`, 1 `host-only`, todos informativos) | `python scripts/agentic/audit_assets.py`, 2026-10-04, nesta consolidação |
| Tamanho das instruções de host (LF) | `CLAUDE.md` 2 018 bytes (orçamento 2 500); `AGENTS.md` 3 692 bytes (orçamento 6 000) | contagem de bytes em 2026-10-04, nesta consolidação; orçamentos em `scripts/agentic/agentic.toml` |
| Consistência da documentação | 30 passed, incluindo a checagem deste relatório | `python -m pytest tests/test_docs_consistency.py`, 2026-10-04, nesta consolidação |
| Suíte offline em Linux e macOS com as Waves B–E | não medido | nenhum run no GitHub depois da Wave A |
| Latência e consumo de tokens dos Forges reais em produção | não medido | sem fonte |

O baseline e a remedição final não foram feitos nas mesmas condições (10 contra 3 repetições, `final.json` com worktree sujo); os números valem para a máquina de origem descrita em [performance](../performance.md).

## Limitações

Abertas e documentadas; nenhuma bloqueou um gate.

- **Isolamento:** não há sandbox de SO; o cwd não é sandbox e o especialista acessa o filesystem inteiro. No Windows sem Job Object, um neto órfão sobrevive ao kill (a chamada continua limitada). Em POSIX, há uma janela de microssegundos entre o fork do processo nativo e o registro do guard de SIGTERM no adapter ([segurança](../security.md)).
- **Routing:** uma dependência ou keywords genéricas declaradas por um único provider confiável ainda podem vencer um provider mais específico; a mitigação é o trust.
- **Git:** filtros globais ou de sistema (git-lfs) não são detectados; qualquer `core.fsmonitor` local pula o `status`; `GIT_NO_LAZY_FETCH` exige git ≥ 2.44 (antes disso a proteção depende só de `GIT_ALLOW_PROTOCOL=none`). No Windows, o ctime é a data de criação, evidência mais fraca para o cache de fingerprints.
- **Adapters reais:** o API Forge exige Python 3.12; o custo do `import apiforge.cli` atinge todo execute da API; com o health sem `apiforge doctor`, dependência quebrada da CLI só aparece no execute. Itens de contexto com intervalo de linhas não são suportados pelos adapters. A limpeza do cwd mantém inteiro um diretório de topo que já existia e não trata caminhos acima de 260 caracteres sem `LongPathsEnabled`. Um artifact declarado que nunca existiu não gera nota.
- **Multi-provider:** a verificação independente fica sempre `not_performed`; um plano com nó `skipped` combina reprodutibilidade `unknown`; os adapters reais não consomem o handoff.
- **Paridade agentic:** a comparação por perfil semântico não pega prosa divergente que não muda nome, caminhos, skills referenciadas, fases ou arquivos de apoio ([ADR 0020](../adr/0020-agentic-assets-canonical-source.md)).
- **Benchmark:** budgets válidos só na máquina de origem; o cache quente não reduz tempo de parede no tamanho medido.

Follow-ups abertos, registrados nas notas das specs:

- Wave A: cair para `taskkill` se `TerminateJobObject` falhar e capturar `GetLastError` antes de `CloseHandle` no erro de spawn; arquivos de cache do registry por digest antigo não são podados; aviso para chaves de policy achatadas duplicadas; a guarda de rede dos testes não cobre `gethostbyname*`.
- Wave B: checar no disco (`lexists`) cada artifact declarado, hoje só conferido de forma léxica pelo core; `normcase` não cobre o macOS sem distinção de maiúsculas.
- Wave C: compartilhar com `protocol/transport.py` os helpers de pipe duplicados em `context/git.py`; expor um `hash_file` público em fingerprints; a forma `#L2` (linha única) não é reconhecida e palavras com barra (`and/or`) viram citações ausentes.
- Wave D: a `verification` não é gravada quando um erro interno ocorre depois do execute; proteger contra `_finish` duplo em erro que não é de persistência; falta teste de `explain` de plano com artefato `installation`; estender a checagem de drift live ao cenário cross; `RunStore.read_optional` segue `<name>.json` simbólico (comportamento anterior ao ciclo).

## Adiamentos intencionais

Fora do ciclo por decisão registrada, não por falta de tempo ([arquitetura](../architecture.md#fora-do-ciclo-2)):

- Entrada Forge Protocol nativa em cada Forge, com gatilho de migração no [ADR 0014](../adr/0014-provider-adapter-location.md).
- Routing por LLM ou semântico ([ADR 0005](../adr/0005-deterministic-routing-first.md)); a ambiguidade continua `ambiguous`.
- Execução dos padrões `delegate`, `parallel` e `debate`, execução concorrente de nós, scheduler, retomada e re-execute de planos, ops `verify` e `estimate` ([ADR 0018](../adr/0018-multi-provider-execution.md)).
- Installer: o `InstallationPlan` só planeja, nunca executa.
- Sandbox de SO: só pesquisa, sem dependência ([ADR 0012](../adr/0012-os-sandbox-research.md)); forge-kernel ([ADR 0004](../adr/0004-no-forge-kernel-yet.md)); banco de grafos; economy avançada.
- Capabilities que escrevem ou usam rede nos Forges reais: só read-only e offline são expostas ([ADR 0017](../adr/0017-capability-taxonomy.md)).
- Fonte canônica renderizada dos assets agentic e plugin do Claude Code: nenhuma migração nesta wave, com gatilho objetivo; nenhum hook de desenvolvimento adicionado ([ADR 0020](../adr/0020-agentic-assets-canonical-source.md)).
- Divisão da Wave D em duas specs (multi-provider e integridade/explain/erros): ficou como uma spec só, com dois gates (5.3 e 9.3).

## Próximo ciclo recomendado

Estado de push e PR em 2026-10-04 (`git branch -a`, `gh pr list`):

- `main` no remoto está em `b1d9ec7`, o merge do PR #3 (Wave A). `feat/cycle2-wave-a` também está no remoto.
- `feat/cycle2-wave-b` (com `feat/cycle2-wave-c` mesclada em `70c3bf9`), `feat/cycle2-wave-c`, `feat/cycle2-wave-d` e `feat/cycle2-wave-e` existem só localmente, sem upstream. Nada foi enviado ao remoto durante esta consolidação. Cada branch contém a anterior: `feat/cycle2-wave-e` tem as Waves B–E, 106 commits à frente de `main`.
- Não há PR aberto para as Waves B–E.

Recomendações, em ordem:

1. Enviar as branches e abrir os PRs das Waves B–E (ou um PR a partir de `feat/cycle2-wave-e`), até o primeiro run verde do `ci` em Ubuntu e Windows × 3.11–3.14 com os adapters instalados.
2. Rodar `compat.yml` (macOS) e `real-providers.yml` uma vez por `workflow_dispatch`, com o segredo `SIBLING_REPOS_TOKEN` configurado, para ter a prova cross-forge também no CI.
3. Fechar os follow-ups listados em "Limitações", começando pelos de Wave D (verificação depois de erro interno, `_finish` duplo) e pela checagem `lexists` dos artifacts declarados.
4. Decidir o consumo de handoff nos adapters reais (`accepts_handoff`) e um verificador independente para `verify`, se houver uso concreto.
5. Medir o custo do `import apiforge.cli` no execute e decidir se ele justifica um processo residente ou outra estratégia; registrar latência real por provider, hoje não medida.
6. Reavaliar no início do ciclo o gatilho do [ADR 0020](../adr/0020-agentic-assets-canonical-source.md) com o histórico de sincronizações dos mirrors.

## Post-Merge Validation Update

Seção adicionada em 2026-10-05, no Cycle 2.1 (Wave A). O corpo do relatório registra o **estado na geração** (2026-10-04); esta seção registra o **estado validado depois do merge**, sem apagar o histórico.

| Item | Estado na geração (2026-10-04) | Estado validado (2026-10-05) |
|---|---|---|
| `main` remota | `b1d9ec7` (merge do PR #3, só Wave A) | `1eaa285` (merge do [PR #4](https://github.com/EdgarSocrates98/the-forger/pull/4), Waves B–E, 2026-10-05T02:23:59Z) |
| Waves B–E | branches só locais, sem upstream e sem PR | mergeadas via `feat/cycle2-wave-e`; `feat/cycle2-wave-a` e `feat/cycle2-wave-e` existem no remoto |
| CI do PR #4 | nenhum PR existia | run 37253785287 falhou (2026-10-05T02:02:28Z); run 37254645706 passou (02:14:59Z) sobre `feat/cycle2-wave-e` |
| CI da `main` pós-merge | nenhum run das Waves B–E | run 37255244389, `success` em 2026-10-05T02:24:02Z sobre `1eaa285`: 10 jobs — `test` Ubuntu e Windows × Python 3.11–3.14 e `package` Ubuntu e Windows 3.11, com os adapters instalados (`pip install -e .[dev] -e ./adapters/sparkforge -e ./adapters/apiforge`) |
| `compat.yml` (macOS) | nunca executado | despachado por `workflow_dispatch` sobre `main` em 2026-10-05 (run 37260503904); resultado registrado na Wave B do [relatório do Cycle 2.1](cycle-2.1.md) |
| `real-providers.yml` | nunca executado | despachado por `workflow_dispatch` sobre `main` em 2026-10-05 (run 37260501716); resultado registrado na mesma Wave B |
| Suíte offline local | 2719 passed + 5 skipped em 3 blocos (Wave D) | 2859 passed, 5 skipped, 0 failed em execução única (77 arquivos de teste, Python 3.14.6, Windows, 2026-10-05). Uma execução intercalada com uma segunda sessão pytest sobre o mesmo `--basetemp` falhou 1 teste de `test_packaging.py`; re-executado isoladamente, o arquivo passou inteiro (11 passed) |

Sobre "Próximo ciclo recomendado": o item 1 (push/PR das Waves B–E) está superado por este update; os itens 2–6 são assumidos pelo Cycle 2.1 (Waves B–I) registrado em [cycle-2.1.md](cycle-2.1.md).
