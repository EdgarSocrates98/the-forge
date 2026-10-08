# Requirements Document

## Project Description (Input)
Wave D do Cycle 2 de The Forge. Quem tem o problema: usuários de The Forge com tarefas híbridas (por exemplo, dados + API) e automações que dependem das decisões de The Forge. Situação atual: `RoutingDecision.pattern` só aceita `route`; `ExecutionPlan`, `VerificationResult`, `WorkspaceDescriptor`, `GraphNode`, `GraphEdge` e `InstallationPlan` existem apenas como nomes reservados na documentação; não há handoff estruturado entre providers; `explain` só despeja os artefatos do run, sem verificar hashes; não há replay nem modo de diagnóstico; os códigos `FORGE-*` não têm taxonomia formal. O que deve mudar: um `ExecutionPlan` DAG local e determinístico executado em sequência, `WorkspaceDescriptor` multi-repo, grafo mínimo com evidência, `VerificationResult`, handoff estruturado e uma prova REAL Spark Forge → API Forge → síntese; `explain` completo com `--json` estável e verificação de hashes, taxonomia `FORGE-*`, `--debug` e níveis de reprodutibilidade. Abordagem: ativar os contratos reservados de forma compatível com o Forge Protocol v1, com executor local sequencial e sem scheduler distribuído. Ver `brief.md` (requisitos semente 13 e 14 de `cycle2-reality-hardening`).

## Introduction
As Waves A, B e C deram a The Forge um core endurecido, adapters reais de Spark Forge e API Forge e um contexto mais barato e íntegro, mas cada run continua executando um único provider. Esta spec entrega a Wave D: The Forge passa a decompor de forma determinística uma tarefa híbrida em um plano de nós, executar esses nós localmente e em sequência, repassar entre eles apenas saídas estruturadas com origem e status epistêmico preservados e produzir uma síntese final, comprovada contra Spark Forge e API Forge reais. Ao mesmo tempo, cada run passa a ser explicável de forma completa e estável, com verificação de integridade dos artefatos persistidos, erros classificados em uma taxonomia única, diagnóstico controlado e um nível de reprodutibilidade honesto.

Toda decisão continua determinística e sem LLM; nenhum conhecimento de domínio entra no core: a decomposição usa apenas os sinais declarados pelos providers e propriedades genéricas da tarefa e do workspace.

## Boundary Context
- **In scope**: contrato `ExecutionPlan` (DAG de nós com papel, provider, capability, ação, entrada de contexto e entrada de artifacts) e sua validação; padrões multi-provider representados de forma compatível; decomposição determinística de uma tarefa em plano; plano fornecido pelo usuário; execução local, sequencial e em ordem topológica determinística; falha parcial de plano; handoff estruturado entre nós; síntese final determinística; prova cross-forge com Spark Forge e API Forge reais e seu equivalente offline; `WorkspaceDescriptor` multi-repo; `GraphNode`/`GraphEdge` mínimos com evidência; `VerificationResult`; operação `plan` do protocolo e decisão sobre `verify`; `InstallationPlan` somente de planejamento; `explain` completo, `--json` estável e verificação de hashes; taxonomia formal de códigos `FORGE-*`; CLI sem traceback e modo debug; nível de reprodutibilidade por run; replay (re-render, re-verify, re-execute).
- **Out of scope**: scheduler ou orquestrador distribuído, execução concorrente de nós, broker, server, banco de dados, web UI, graph engine ou banco de grafos; routing por LLM; forge-kernel; instalação ou download automático de Forges; conhecimento de domínio de Spark ou OpenAPI no core; adapters reais, conformance, contrato de ambiente `THEFORGE_REAL_*`, versionamento e taxonomia de capabilities (`real-provider-integration`); tiers de contexto, git somente leitura, cache de fingerprints, TOCTOU, perfis e telemetria (`context-intelligence-v2`); paridade de assets agentic, consolidação final de documentação/ADRs e relatório final do ciclo (`agentic-maintainability`).
- **Adjacent expectations**:
  - `theforge ask` continua executando no máximo um provider por run em qualquer perfil; a execução multi-provider acontece somente pelo fluxo de plano desta spec.
  - O limite de providers por run de cada perfil é definido por `context-intelligence-v2`; esta spec o aplica e não o redefine.
  - O estado git dos repositórios é obtido pela consulta git somente leitura de `context-intelligence-v2`; esta spec não executa o git por conta própria. O resumo de workspace do ContextPack continua local ao ContextPack e não é promovido a descritor de workspace.
  - Os adapters, as capabilities expostas, os IDs de evidência nativos e o contrato de ambiente dos Forges reais são de `real-provider-integration`; esta spec os consome sem redefini-los.
  - Os invariantes das Waves A–C (integridade de resultado, `producer`, trust, policy, ambiente mínimo, cwd controlado, redação, contexto por referência) valem para cada nó de um plano sem exceção.
  - Mudanças em receipt, telemetria ou níveis de verificação feitas por `context-intelligence-v2` são gatilho de revalidação desta spec.

## Requirements

### Requirement 1: Contrato e validação de `ExecutionPlan`
**Objective:** As a usuário de The Forge, I want que um plano multi-provider seja um contrato explícito e validado antes de qualquer execução, so that nenhum nó rode a partir de um plano inconsistente.

#### Acceptance Criteria
1. The Forge shall representar um `ExecutionPlan` como grafo acíclico de nós, em que cada nó declara identificador, papel, provider, capability, ação, entrada de contexto (alvos do workspace) e entrada de artifacts (nós dos quais recebe handoff), e cada dependência referencia um nó do mesmo plano.
2. If um `ExecutionPlan` contém ciclo, dependência para nó inexistente, identificador de nó duplicado, entrada de artifacts de um nó que não é dependência dele, ou nó cujo provider não declara a capability ou a ação indicadas, The Forge shall rejeitar o plano antes de executar qualquer nó e reportar cada violação encontrada.
3. If um `ExecutionPlan` excede o limite documentado de nós ou usa mais providers distintos do que o limite de providers do perfil efetivo, The Forge shall rejeitar o plano antes de executar qualquer nó e reportar o limite violado.
4. The Forge shall representar os padrões multi-provider `route`, `delegate`, `parallel`, `pipeline` e `debate` sem invalidar decisões de routing e runs gravados antes desta spec e sem alterar o Forge Protocol v1.
5. If um plano declara um padrão reservado que esta spec não executa, The Forge shall rejeitar o plano antes de executar qualquer nó, informando que o padrão é reservado.
6. When o usuário fornece um plano em arquivo, The Forge shall aplicar ao plano fornecido a mesma validação de um plano gerado por The Forge.
7. The Forge shall persistir o plano validado no run do plano, com redação de segredos aplicada, antes de executar o primeiro nó.

### Requirement 2: Decomposição determinística de tarefa em plano
**Objective:** As a usuário de The Forge, I want que uma tarefa híbrida seja decomposta automaticamente em nós por especialista, so that eu não precise montar o plano à mão nas tarefas comuns.

#### Acceptance Criteria
1. When uma tarefa é submetida ao fluxo de plano com um perfil cujo limite de providers é maior que 1, The Forge shall criar um nó para cada provider roteável cuja melhor capability atinge a força mínima de sinais já exigida pelo routing de um único provider.
2. The Forge shall decompor usando apenas sinais declarados pelos providers e propriedades genéricas da tarefa e do workspace, sem LLM, sem rede e sem regras de domínio no core.
3. When dois ou mais nós são criados, The Forge shall ordená-los e encadeá-los por uma regra fixa e documentada sobre a tarefa e registrar no plano a regra aplicada e a evidência que determinou cada dependência, marcando-a como inferida.
4. If a regra de ordenação não distingue dois nós, um mesmo provider tem duas capabilities empatadas como melhor opção, ou a quantidade de nós qualificados excede o limite de providers do perfil, The Forge shall reportar a tarefa como `ambiguous` com o motivo, sem executar nenhum nó.
5. If nenhum provider qualifica, The Forge shall reportar a tarefa como `no_route` sem executar nenhum nó.
6. While o perfil efetivo limita a execução a um provider, The Forge shall produzir um plano de no máximo um nó com padrão `route` e registrar que a decomposição multi-provider não é permitida pelo perfil.
7. When a mesma tarefa é submetida com os mesmos providers, o mesmo perfil e o mesmo conteúdo de workspace, The Forge shall produzir o mesmo plano, com os mesmos nós, dependências e ordem.
8. Where o usuário pede apenas o planejamento, The Forge shall persistir e exibir o plano sem executar nenhum nó.

### Requirement 3: Execução local sequencial e falha parcial
**Objective:** As a usuário de The Forge, I want que o plano seja executado localmente, um nó por vez e de forma previsível, so that a coordenação entre especialistas não dependa de um orquestrador complexo.

#### Acceptance Criteria
1. When um `ExecutionPlan` válido é executado, The Forge shall executar os nós localmente, um de cada vez, em ordem topológica com desempate determinístico e documentado.
2. The Forge shall executar cada nó com as mesmas garantias de um run de um único provider (revalidação do registry, health, policy, contexto por referência, integridade do resultado, `producer` e persistência redigida) e registrar cada nó como um run próprio vinculado ao run do plano.
3. The Forge shall executar cada nó somente com o provider indicado no plano, sem fallback para outro provider.
4. If um nó termina sem um `ExecutionResult` válido (falha do provider, recusa, recusa de policy ou erro), The Forge shall não executar os nós que dependem dele, direta ou transitivamente, e registrar cada nó não executado com o nó bloqueante e o motivo.
5. While um nó falhou, The Forge shall continuar executando os nós que não dependem dele.
6. When a execução do plano termina, The Forge shall reportar o plano como `ok` somente se todos os nós produziram `ExecutionResult` válido com status `ok`; como `partial` se ao menos um nó produziu resultado válido e algum nó falhou, não foi executado ou terminou `partial`; e como falha, com o nó e o motivo, se nenhum nó produziu resultado válido.
7. When o usuário aprova uma capability para o plano, The Forge shall aplicar essa aprovação somente aos nós dessa capability, mantendo a avaliação de policy de cada nó antes da execução dele.
8. The Forge shall nunca executar dois nós ao mesmo tempo nem depender de serviço, scheduler ou processo persistente fora da invocação da CLI.

### Requirement 4: Handoff estruturado entre nós
**Objective:** As a usuário de The Forge, I want que um nó receba do anterior apenas saídas estruturadas e rastreáveis, so that a coordenação seja auditável e não vaze texto livre, conteúdo ou segredos.

#### Acceptance Criteria
1. When um nó depende de outro, The Forge shall entregar ao nó dependente apenas evidências, findings, referências a artifacts (caminho e hash, sem conteúdo) e decisões estruturadas do nó de origem, nunca a saída integral do provider nem conteúdo de arquivos.
2. The Forge shall preservar em cada item de handoff o status epistêmico original (`confirmed`, `observed`, `inferred`, `proposed`, `unresolved`) e identificar o nó, o provider (id e versão) e o run de origem.
3. The Forge shall incluir no handoff de um nó somente itens dos nós declarados em sua entrada de artifacts.
4. If o handoff de um nó excede o limite documentado de itens ou de tamanho, The Forge shall entregar um handoff truncado de forma determinística e registrar a truncagem como limitação no nó dependente.
5. The Forge shall aplicar redação de segredos ao handoff antes de entregá-lo ao provider e antes de persisti-lo.
6. The Forge shall persistir o handoff entregue a cada nó no run desse nó e vinculá-lo ao receipt do nó por hash.
7. If o provider do nó dependente não declara que consome handoff para a capability usada, The Forge shall ainda assim entregar o handoff, executar o nó e registrar no nó a limitação de que o uso do handoff pelo provider não foi declarado.
8. The Forge shall manter válidos, sem alteração, os providers que não reconhecem o handoff.

### Requirement 5: Síntese final determinística
**Objective:** As a usuário de The Forge, I want uma síntese final do plano, so that eu veja em um lugar o que cada especialista concluiu e com que grau de certeza.

#### Acceptance Criteria
1. When a execução de um plano termina, The Forge shall produzir uma síntese que lista, por nó, o provider, a capability, a ação, o status, os findings e a contagem de evidências por status epistêmico, cada item com o nó e o run de origem.
2. The Forge shall registrar na síntese quais itens foram repassados de cada nó para cada nó dependente.
3. The Forge shall registrar na síntese os nós que falharam ou não foram executados, com o motivo, e as limitações e incógnitas agregadas dos nós.
4. The Forge shall produzir a síntese de forma determinística, sem LLM, sem gerar conclusões que não estejam nas saídas estruturadas dos nós e sem elevar o status epistêmico de nenhum item.
5. The Forge shall persistir a síntese com redação de segredos aplicada e vinculada ao run do plano por hash.

### Requirement 6: Prova cross-forge Spark Forge → API Forge
**Objective:** As a usuário de The Forge, I want ver uma tarefa híbrida real coordenada entre Spark Forge e API Forge, so that a coordenação entre especialistas seja comprovada e não apenas simulada.

#### Acceptance Criteria
1. When a tarefa "Projete um pipeline Spark que produza dados para uma API" é submetida ao fluxo de plano, com perfil que permite multi-provider, sobre um workspace de exemplo com um job PySpark e um contrato OpenAPI e com Spark Forge e API Forge reais registrados, The Forge shall decompô-la em um nó de dados atendido pelo Spark Forge e um nó de API atendido pelo API Forge, nessa ordem de dependência.
2. When esse plano é executado, The Forge shall executar o Spark Forge real, entregar ao API Forge real ao menos um item estruturado do nó de dados com origem e status epistêmico preservados, executar o API Forge real e produzir a síntese final referenciando os dois nós.
3. The Forge shall oferecer essa prova como teste de integração selecionável separadamente da suíte principal, usando o contrato de ambiente dos Forges reais de `real-provider-integration`: pular com motivo explícito quando um Forge real não está configurado e falhar quando os Forges reais são declarados obrigatórios.
4. The Forge shall oferecer, na suíte principal offline, o mesmo cenário de decomposição, execução, handoff e síntese contra providers de teste que não exigem rede, credenciais nem os repositórios irmãos.
5. When a prova real roda no workflow agendado de providers reais, The Forge shall tornar falhas da prova visíveis no resultado do workflow, sem bloquear pull requests.

### Requirement 7: `WorkspaceDescriptor` multi-repo
**Objective:** As a usuário de The Forge, I want que o workspace seja descrito com seus repositórios independentes, so that planos possam abranger mais de um repositório sem assumir monorepo.

#### Acceptance Criteria
1. The Forge shall representar um `WorkspaceDescriptor` com a raiz, os repositórios encontrados (caminho relativo, HEAD e branch, estado sujo), os caminhos relevantes, as tecnologias detectadas e as relações conhecidas entre repositórios.
2. The Forge shall reconhecer como repositórios independentes os repositórios encontrados na raiz e em subdiretórios até uma profundidade documentada, inclusive quando a raiz não é um repositório, sem seguir links simbólicos e sem tratar o workspace como monorepo.
3. The Forge shall obter HEAD, branch e estado sujo de cada repositório sem modificar nenhum repositório e sem executar programas configurados pelo próprio repositório.
4. If o git não está disponível ou a consulta a um repositório falha, The Forge shall registrar HEAD e estado sujo daquele repositório como desconhecidos, com a limitação correspondente, e continuar.
5. The Forge shall derivar as tecnologias detectadas somente de arquivos de dependência genéricos e de sinais declarados pelos providers, registrando para cada tecnologia o caminho que a evidencia.
6. The Forge shall registrar como relações conhecidas apenas relações declaradas explicitamente pelo usuário na configuração do workspace ou observadas no sistema de arquivos, cada uma com sua evidência de origem.
7. When o fluxo de plano é executado, The Forge shall persistir o `WorkspaceDescriptor` no run do plano, sem conteúdo de arquivos e com redação de segredos aplicada.
8. When o usuário pede a descrição do workspace, The Forge shall exibi-la em texto e em JSON sem executar nenhum provider.

### Requirement 8: Grafo mínimo com evidência
**Objective:** As a usuário e automação, I want um grafo mínimo de workspace, providers e plano em que toda relação tenha evidência, so that eu saiba por que cada relação existe.

#### Acceptance Criteria
1. The Forge shall representar `GraphNode` e `GraphEdge` mínimos em memória e como artifact JSON do run do plano, cobrindo workspace, repositórios, providers, capabilities, nós do plano e evidências e artifacts produzidos.
2. The Forge shall registrar em toda aresta a evidência de origem e um status epistêmico entre `explicit`, `observed` e `inferred`.
3. If uma aresta seria criada com status `inferred`, The Forge shall registrar nela a regra que a produziu, e shall nunca criar uma aresta inferida sem essa regra.
4. If uma aresta não tem evidência de origem ou referencia um nó inexistente no grafo, The Forge shall rejeitá-la e não persisti-la.
5. When o mesmo plano é executado sobre as mesmas entradas, The Forge shall produzir o mesmo grafo, com nós e arestas na mesma ordem.
6. The Forge shall manter o grafo como artifact do run, sem banco de grafos nem índice persistente fora dos runs.

### Requirement 9: `VerificationResult`
**Objective:** As a usuário de The Forge, I want saber quem verificou cada resultado e como, so that auto-relato de provider nunca passe por verificação independente.

#### Acceptance Criteria
1. The Forge shall produzir, para cada nó executado e para cada run de um único provider, um `VerificationResult` que separa quatro níveis: auto-relato do provider, evidência do provider, verificação de The Forge e verificação independente.
2. The Forge shall registrar para cada nível se foi executado, o resultado e a base usada (por exemplo, integridade do resultado, reverificação de contexto, hashes de artifacts).
3. The Forge shall nunca classificar o status declarado pelo provider nem evidências produzidas pelo próprio provider como verificação de The Forge ou verificação independente.
4. If nenhuma verificação independente foi executada, The Forge shall registrar o nível independente como não executado.
5. When The Forge detecta divergência de contexto ou de hash de artifact durante a verificação, The Forge shall registrar a falha no nível de verificação de The Forge e nunca reportar o nó como `ok`.
6. The Forge shall persistir o `VerificationResult` com redação de segredos aplicada e vinculado ao receipt do run por hash.

### Requirement 10: Operações `plan` e `verify` e `InstallationPlan`
**Objective:** As a usuário e autor de provider, I want que operações reservadas só sejam ativadas com uso concreto e que dependências ausentes virem um plano de instalação inofensivo, so that o protocolo cresça sem promessas vazias e sem efeitos colaterais.

#### Acceptance Criteria
1. Where um provider declara a operação `plan`, The Forge shall obter dele, antes de executar o nó correspondente, o contexto necessário, a classe de operação estimada, os artifacts esperados e as incógnitas, e registrar essa estimativa no plano.
2. If a classe de operação estimada pelo provider é mais restritiva que a declarada no manifest, The Forge shall avaliar a policy do nó com a classe mais restritiva.
3. If o provider não declara `plan` ou a operação `plan` falha, The Forge shall registrar a estimativa como desconhecida, com o motivo, sem falhar o planejamento.
4. The Forge shall ativar uma operação reservada do protocolo somente quando houver caso de uso concreto neste ciclo, documentar a decisão para `plan` e para `verify`, e nunca invocar uma operação mantida reservada.
5. When um nó do plano depende de um provider registrado que está ausente, inválido ou indisponível, The Forge shall produzir no máximo um `InstallationPlan` por run, listando cada item faltante com o motivo e a ação sugerida informados pelo registry ou pelo provider.
6. The Forge shall marcar o `InstallationPlan` como somente de planejamento e nunca baixar, instalar nem executar nada a partir dele.

### Requirement 11: `explain` completo e JSON estável
**Objective:** As a usuário e automação, I want uma explicação completa e estável de cada run, so that eu entenda e automatize as decisões de The Forge.

#### Acceptance Criteria
1. When `theforge explain <run>` é executado, The Forge shall mostrar, quando disponíveis: intenção, sinais, candidatos, provider selecionado, fallbacks, contexto, budget, versão do provider, contagem de evidências, findings, duração, limitações, incógnitas, verificação e nível de reprodutibilidade.
2. When `theforge explain` é executado para o run de um plano, The Forge shall mostrar também o plano, o estado de cada nó com seu run, os handoffs entregues, o descritor de workspace, o `InstallationPlan` quando existir e a síntese.
3. If uma informação não foi registrada no run, The Forge shall indicá-la como não registrada em vez de omiti-la ou falhar, inclusive para runs gravados antes desta spec.
4. When `theforge explain <run> --json` é executado, The Forge shall emitir um documento JSON com identificador de versão de estrutura, estrutura estável e documentada e schema publicado.
5. The Forge shall evoluir a estrutura do `explain --json` apenas de forma aditiva dentro da mesma versão.

### Requirement 12: Verificação de hashes no `explain`
**Objective:** As a usuário, I want que `explain` confira a integridade do que foi persistido, so that eu saiba se um run foi alterado depois de gravado.

#### Acceptance Criteria
1. When `explain` é executado, The Forge shall recalcular o hash de cada artefato persistido do run cujo hash foi registrado e compará-lo com o registrado.
2. When `explain` é executado para um run cujo resultado referencia artifacts do provider, The Forge shall recalcular o hash de cada artifact referenciado e compará-lo com o declarado.
3. If algum hash diverge, um artefato registrado está ausente ou não pode ser lido, The Forge shall indicar cada divergência com o artefato e o tipo de divergência e encerrar com código de saída documentado distinto de sucesso.
4. When `explain` é executado para o run de um plano, The Forge shall verificar também os hashes dos runs dos nós e dos artefatos do plano.
5. The Forge shall verificar hashes sem executar nenhum provider e sem modificar o run.

### Requirement 13: Taxonomia de erros, CLI sem traceback e modo debug
**Objective:** As a usuário e automação, I want códigos de erro consistentes e mensagens governadas, so that eu trate falhas de forma programática e nunca veja um traceback bruto.

#### Acceptance Criteria
1. The Forge shall agrupar todos os códigos `FORGE-*` em uma taxonomia documentada de famílias (incluindo protocol, registry, routing, plan, context, provider, policy, persistence, security, usage e internal) em que cada código pertence a exatamente uma família.
2. The Forge shall ter verificação automatizada que falhe quando um código `FORGE-*` é usado fora da taxonomia, quando a documentação da taxonomia diverge dos códigos definidos ou quando o valor de um código já publicado muda.
3. The Forge shall preservar intactos os códigos de erro nativos de providers e apresentá-los como códigos de provider, separados da taxonomia `FORGE-*`.
4. The Forge shall exibir na CLI, para todo erro, o código e a família, e shall nunca exibir traceback bruto, inclusive em erros internos inesperados e de persistência.
5. Where o modo debug é solicitado, The Forge shall exibir diagnóstico detalhado da falha (etapa, tipo e mensagem do erro, cadeia de causas e localização no código de The Forge) com redação de segredos aplicada.
6. While o modo debug não é solicitado, The Forge shall exibir apenas a mensagem governada do erro.
7. The Forge shall manter os códigos de saída da CLI já documentados para os desfechos existentes.

### Requirement 14: Reprodutibilidade e replay
**Objective:** As a usuário e automação, I want saber se um run pode ser reproduzido e repeti-lo de forma segura, so that eu diferencie reapresentar, reverificar e reexecutar.

#### Acceptance Criteria
1. The Forge shall registrar em cada run, inclusive no run de um plano, um nível de reprodutibilidade entre `reproducible`, `partially_reproducible`, `non_reproducible` e `unknown`, com os motivos.
2. The Forge shall nunca declarar `reproducible` quando o provider declarou ou teve acesso a sistema externo (rede, credenciais, leitura ou mutação externa), quando foi detectada divergência de contexto ou quando o provider não declarou execução determinística.
3. The Forge shall atribuir ao run de um plano o nível menos reprodutível entre os seus nós.
4. The Forge shall tratar como `unknown` o nível de reprodutibilidade de runs gravados antes desta spec.
5. Where `replay` é oferecido, The Forge shall distinguir os modos re-render, re-verify e re-execute.
6. When o modo re-render é pedido, The Forge shall reapresentar o run a partir dos artefatos persistidos, sem executar providers e sem ler o workspace.
7. When o modo re-verify é pedido, The Forge shall reverificar os hashes persistidos e comparar os hashes de contexto registrados com o conteúdo atual do workspace, sem executar providers, e reportar cada divergência.
8. When o modo re-execute é pedido, The Forge shall executar um novo run vinculado ao original, sem alterar o original, e reportar se o resultado coincide com o original.
9. If o modo re-execute é pedido para um run `non_reproducible` ou `unknown`, cujas entradas de contexto mudaram ou cujo provider mudou de identidade ou versão, The Forge shall recusar a reexecução com os motivos e com código de erro específico, sem executar nenhum provider.

### Requirement 15: Compatibilidade, persistência segura e decisões registradas
**Objective:** As a mantenedor e autor de provider, I want que a Wave D conviva com o Forge Protocol v1 e com os runs existentes, so that nada já integrado quebre.

#### Acceptance Criteria
1. The Forge shall manter o Forge Protocol em `forge/v1` e introduzir mudanças em contratos existentes somente como campos ou valores aditivos e opcionais dentro de `theforge/<Name>/v1`.
2. The Forge shall publicar os novos contratos como `theforge/<Name>/v1` e manter os JSON Schemas de `schemas/` regenerados e em paridade com os contratos.
3. The Forge shall passar por redação de segredos tudo o que persiste nesta spec, incluindo plano, handoffs, síntese, descritor de workspace, grafo, verificação, `InstallationPlan` e diagnósticos de debug.
4. The Forge shall manter legíveis os runs gravados antes desta spec, tratando os artefatos e campos novos ausentes como não registrados.
5. The Forge shall manter o runtime sem dependências além da biblioteca padrão do Python suportado, sem LLM e sem serviços de rede próprios.
6. The Forge shall atualizar a documentação de protocolo, arquitetura, CLI e autoria de provider para plano, handoff, `plan`, taxonomia de erros, `explain`, debug, reprodutibilidade e replay.
7. The Forge shall registrar ADRs para o modelo de execução multi-provider (plano local sequencial e handoff) e para a taxonomia de erros e o modelo de reprodutibilidade.
