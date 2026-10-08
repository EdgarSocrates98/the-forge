# Implementation Plan — cross-forge-foundation (Wave D)

> Pré-requisito: `real-provider-integration` (Wave B) e `context-intelligence-v2` (Wave C) implementadas e mescladas. Esta spec consome `profiles.profile_for`, `context.git.read_git_state`, `context.verify.reverify`, o `DriftReport` e o artefato `telemetry` da Wave C, e os adapters em `--replay`, `tests/real_providers.py::require_forge` e o marker `real_provider` da Wave B. ADRs desta spec, com números congelados: 0018 (modelo de execução multi-provider) e 0019 (taxonomia de erros e reprodutibilidade).
>
> Costuras de implementação (ver design, "Seams de implementação"): (a) execução multi-provider = grupos 1–5, encerrados pelo gate 5.3; (b) integridade, explicabilidade e replay = 6.x e 7.3; (c) governança de erros = 7.1 e a documentação de erros em 9.x. Nenhuma tarefa de (b) ou (c) começa antes do gate 5.3; `agentic-maintainability` re-checa a consolidação após 5.3 e após 9.3.
>
> Versão: se alguma tarefa alterar `theforge.__version__`, a mesma tarefa acrescenta a linha correspondente da matriz de compatibilidade em `docs/versioning.md` exigida por `test_compat_matrix` (Wave B).

- [x] 1. Fundação: taxonomia, contratos, persistência e infraestrutura de testes
- [x] 1.1 Formalizar a taxonomia de códigos e criar os códigos novos
  - Acrescentar os códigos de plano, workspace, persistência, replay e de hash de artifact divergente na fonte única de códigos, sem alterar nenhum valor existente
  - Mapear explicitamente cada código, inclusive os das Waves B e C, para exatamente uma família (protocol, registry, routing, plan, context, provider, policy, persistence, security, workspace, replay, usage, internal), com os códigos de trust na família security, e oferecer a consulta da família de um código que devolve "nenhuma" para códigos nativos de provider
  - Dar a todo erro esperado de The Forge um código da fonte única: erro de uso (inclusive o de arquivo de plano), erros de persistência de escrita e leitura e a nova recusa de replay
  - Registrar em um arquivo golden os valores publicados e criar `docs/errors.md` como lista canônica de códigos, com a tabela código → família → significado, explicando que `routing` não tem códigos porque `ambiguous`/`no_route` são desfechos
  - Concluído quando um teste falhar para código sem família, para literal `FORGE-` no código-fonte fora da fonte única, para divergência entre a tabela de `docs/errors.md` e o mapeamento, e para valor publicado alterado, e passar no estado atual; e quando um código nativo (`AF-*`, `SPARKFORGE-*`) não tiver família; e quando todo erro esperado de The Forge expuser um código da fonte única
  - _Requirements: 13.1, 13.2, 13.3_

- [x] 1.2 Adicionar os contratos de plano, handoff e os campos aditivos de protocolo
  - Introduzir os padrões multi-provider (com `route` e `pipeline` como executáveis), o desfecho `planned`, os status de aresta e de reprodutibilidade e os limites de nós, handoff, profundidade, repositórios e grafo, todos com uma única definição no módulo de tipos compartilhados (os módulos de contrato só os importam)
  - Criar o plano (nós com papel, provider, capability, ação, alvos, dependências com status explícito/inferido e regra, entradas de artifacts, estimativa e limitações), as violações, a estimativa e o request da operação `plan`, o resultado de plano com desfecho por nó, a síntese e os valores em memória de execução de nó e de resultado de origem
  - Criar o handoff com itens de evidência, finding, referência de artifact e decisão, cada um com origem (run do plano, nó, run e provider) e status epistêmico original, com teto de tamanho do `claim`
  - Acrescentar de forma opcional o padrão à decisão de routing, o handoff ao request de execução, a declaração de consumo de handoff à capability e a declaração de execução determinística ao manifest
  - Concluído quando testes de contrato provarem defaults compatíveis (decisão de routing gravada sem padrão continua válida e relida estritamente, request de execução sem handoff e manifest sem os campos novos continuam válidos), releitura estrita de cada contrato novo e rejeição local de dependência inferida sem regra
  - _Requirements: 1.1, 1.4, 4.1, 4.2, 4.8, 15.1_

- [x] 1.3 Adicionar os contratos de workspace, grafo, verificação, instalação, explain e diagnóstico
  - Criar o descritor de workspace (repositórios com o resumo git da Wave C embutido sem redeclarar campos — inclusive HEAD destacado e quantidade de alterados — e limitações, caminhos, tecnologias com evidência e relações explícitas ou observadas) e o grafo (nós por tipo e arestas com evidência obrigatória, status `explicit`/`observed`/`inferred` e regra obrigatória só para inferidas)
  - Criar o resultado de verificação com os quatro níveis, impedindo no próprio contrato que auto-relato ou evidência do provider sejam marcados como verificação aprovada, e o nível de reprodutibilidade com motivos
  - Criar o plano de instalação marcado como somente de planejamento, o relatório de explain com identificador de versão, seções tipadas, relatório de integridade, seções não registradas e artefatos crus, e o diagnóstico com estágio, código, família, cadeia de causas e quadros sem variáveis locais
  - Concluído quando testes de contrato rejeitarem aresta sem evidência, aresta inferida sem regra, auto-relato `passed` e plano de instalação sem itens, e aceitarem releitura estrita de exemplos válidos de cada contrato
  - _Requirements: 7.1, 8.1, 8.2, 8.3, 9.1, 9.2, 9.3, 9.4, 10.6, 11.4, 13.5, 14.1_

- [x] 1.4 Implementar as invariantes relacionais de plano, handoff, grafo e resultado de plano
  - Validar a estrutura do plano reunindo todas as violações: ids únicos e válidos, dependências existentes, ciclo, entradas de artifacts fora das dependências, limite de nós, padrão reservado e plano `route` com mais de um nó
  - Validar o handoff contra limite de itens, de bytes canônicos e de tamanho de `claim`; validar arestas do grafo com extremidade inexistente; validar que um resultado de plano `ok` tem todos os nós `ok` com resultado, que nó `skipped` tem nó bloqueante e que a ordem é uma permutação dos nós
  - Concluído quando cada invariante tiver um caso válido e um inválido testados com o código `FORGE-*` esperado, e um plano com várias falhas devolver todas as violações de uma vez
  - _Requirements: 1.2, 1.3, 1.5, 3.6, 4.4, 8.4_

- [x] 1.5 Estender receipt, persistência de runs e schemas publicados
  - Acrescentar ao receipt o tipo de run (run ou plano), o vínculo com o run do plano e o nó, o vínculo de replay, o hash da verificação, o nível de reprodutibilidade, o hash do handoff nas entradas e as referências do plano; exigir referências de plano e ausência de provider em receipts de plano e `planned` só neles
  - Validar no receipt de plano que o hash do resultado de plano e o hash da telemetria do run do plano são os dos arquivos em disco; manter inalterada a validação do receipt de run
  - Registrar no armazenamento de runs os artefatos de plano, resultado de plano, descritor de workspace (nome de artefato `workspace-descriptor`, distinto do resumo de workspace do ContextPack), grafo, instalação, handoff, verificação e diagnóstico, todos gravados com redação e releitura estrita
  - Exportar os contratos novos (abertos os que cruzam o protocolo: handoff, request e estimativa de `plan`; fechados os demais) e regenerar `schemas/`
  - Concluído quando a paridade de schemas passar com os arquivos novos, um receipt de plano com hash de resultado de plano ou de telemetria divergente for recusado sem gravação, e runs gravados no formato anterior continuarem relidos estritamente com verificação e reprodutibilidade ausentes
  - _Requirements: 4.6, 9.6, 14.4, 15.2, 15.3, 15.4_

- [x] 1.6 Preparar fixtures e infraestrutura de testes da Wave D
  - Registrar na tabela de categorias de teste todos os arquivos de teste novos previstos no design
  - Fazer o provider de fixture responder à operação `plan` com a estimativa declarada em seu manifest de teste e devolver como evidência a quantidade de itens de handoff recebidos; acrescentar ao provider defeituoso os modos de artifact adulterado, erro na operação `plan`, estimativa mais restritiva, consumo declarado de handoff e falha interna
  - Criar o workspace de prova com um repositório de pipeline de dados (job PySpark e dependência `pyspark`) e um de API (contrato OpenAPI, app e dependência `fastapi`), e o utilitário que o monta em diretório temporário como dois repositórios git independentes quando o git existe
  - Declarar o echo provider como de execução determinística
  - Concluído quando a suíte existente continuar passando com as fixtures alteradas, e um teste rápido confirmar que o workspace montado tem dois repositórios independentes e que a fixture responde `plan` e ecoa o handoff
  - _Requirements: 6.4, 10.1_

- [x] 2. Núcleo de workspace e planejamento
- [x] 2.1 (P) Implementar o descritor de workspace multi-repo e as relações explícitas
  - Descobrir repositórios na raiz e em subdiretórios até a profundidade documentada, sem seguir links simbólicos, ignorando diretórios excluídos e `.forge`, aceitando raiz que não é repositório e repositórios aninhados como independentes
  - Obter o resumo git de cada repositório pela consulta git somente leitura da Wave C e embuti-lo tal como devolvido, copiando suas limitações e registrando desconhecido quando o git falha ou não existe
  - Limitar o tempo total de git da descrição a 20 s (não 64 × 5 s): consultar na ordem dos caminhos e, quando a próxima consulta poderia ultrapassar o orçamento, deixar esse e os repositórios seguintes sem resumo git e com a limitação de orçamento esgotado
  - Detectar tecnologias somente a partir de arquivos de dependência genéricos que casam dependências declaradas por providers e de domínios de providers cujos globs casam arquivos do repositório, sempre com o caminho de evidência
  - Ler as relações explícitas de `.forge/config/workspace.toml`, ignorando com aviso entradas inválidas ou de repositórios inexistentes, e registrar relações de contenção observadas
  - Oferecer no registry a leitura de registros apenas a partir do cache, sem iniciar processos de provider, com teste próprio provando que nenhum processo de provider é iniciado
  - Concluído quando testes com repositórios git reais em diretório temporário (pulando com motivo sem git) provarem dois repositórios independentes e um aninhado, profundidade excedida ignorada, symlink não seguido, resumo git idêntico ao da Wave C (inclusive HEAD destacado e quantidade de alterados), git indisponível como desconhecido com limitação, orçamento de git esgotado com relógio falso sem ultrapassar 20 s, tecnologias com evidência, relações válidas e inválidas, e diretórios `.git` idênticos antes e depois
  - _Boundary: WorkspaceDescriber, WorkspaceRelations, Registry (somente a leitura a partir do cache)_
  - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6_

- [x] 2.2 (P) Implementar a ordem topológica e a validação de planos com o registry
  - Ordenar os nós por dependência com desempate determinístico por id e calcular, para um nó, o primeiro ancestral sem resultado válido
  - Validar cada nó contra o registry (provider existente e pronto, capability resolvida pela resolução de aliases do manifest da Wave B, declarada e suportada, ação oferecida) e o total de providers distintos contra o limite do perfil, somando às violações estruturais
  - Ler um plano de arquivo em modo estrito com limite de tamanho, substituindo os campos controlados pelo run, trocando capability dada por alias pelo ID canônico com a nota de alias da Wave B (e a de depreciação, quando houver) nas limitações do nó, e aplicando o perfil da linha de comando com limitação quando diverge; arquivo ilegível ou fora do contrato vira erro de uso com código de plano
  - Concluído quando testes cobrirem a ordem em DAGs com empate, o bloqueio transitivo, cada violação relacional, limite de providers por perfil, capability por alias registrada como ID canônico com a nota de alias e a mesma validação para plano em arquivo e plano gerado
  - _Boundary: PlanValidator, Order_
  - _Requirements: 1.2, 1.3, 1.5, 1.6, 3.1, 3.4_

- [x] 2.3 Implementar a decomposição determinística de tarefas
  - Agrupar os candidatos da decisão de routing por provider, escolher a melhor capability de cada um e qualificar os providers que atingem a força mínima de sinais do routing
  - Produzir um plano de um nó `route` (ou o próprio `ambiguous`/`no_route`) quando o perfil limita a um provider ou só um provider qualifica, registrando a limitação de perfil quando havia mais qualificados
  - Ordenar dois ou mais nós pela posição da primeira keyword casada na intenção e encadeá-los em pipeline com dependência inferida pela regra `intent-order` e sua evidência; tratar empate de posição, keyword ausente, empate de capabilities no mesmo provider e excesso sobre o limite do perfil como `ambiguous`
  - Definir alvos de cada nó pelos repositórios onde seus sinais casaram, papéis genéricos e a decisão de routing do plano com uma seleção por nó
  - Validar cedo, nesta tarefa e não só na prova real, com os manifests empacotados dos adapters da Wave B (obtidos pelo describe em modo replay, cenário `default`, que usa o snapshot empacotado) que a tarefa de prova gera exatamente um nó `pyspark.static-analysis` seguido de um nó `api.analyze`, detectando melhor capability não única em qualquer dos dois Forges; se não gerar, parar e reportar como revalidação do catálogo da Wave B, nunca acrescentando regra de domínio ao core
  - Concluído quando testes provarem a decomposição da tarefa de prova com fixtures e com os manifests empacotados dos adapters (com mensagem de falha apontando a revalidação do catálogo da Wave B), cada caso de ambiguidade, `no_route`, o comportamento em `balanced`, os alvos por repositório e, por propriedade, o mesmo plano para qualquer permutação de registros, candidatos e arquivos
  - _Depends: 2.1_
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 6.1_

- [x] 2.4 (P) Implementar o handoff estruturado
  - Montar o handoff de um nó apenas a partir dos resultados válidos dos nós declarados em suas entradas, com itens de decisão, finding, evidência e referência de artifact, preservando ids, status epistêmico e origem
  - Truncar de forma determinística pela prioridade do design ao atingir o limite de itens ou de bytes, registrando a quantidade descartada como limitação
  - Redigir segredos antes de devolver o handoff, de modo que o entregue e o persistido sejam o redigido
  - Concluído quando testes provarem que itens de nós não declarados nunca entram, que nenhum item carrega conteúdo de arquivo ou saída integral, que epistêmico e origem se mantêm, que a truncagem é estável e que um segredo em `claim` sai redigido
  - _Boundary: HandoffBuilder_
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

- [x] 2.5 (P) Implementar a síntese determinística do plano
  - Listar por nó provider, capability, ação, status, run, findings com ids originais e contagem de evidências por status epistêmico
  - Registrar os handoffs entre nós com quantidade e truncagem, os nós com falha ou não executados com motivo, e as limitações e incógnitas agregadas com prefixo do nó
  - Concluído quando testes provarem a mesma síntese para as mesmas execuções, nenhuma elevação de status epistêmico, nenhum finding criado pela síntese e falhas listadas com o nó e o motivo
  - _Boundary: Synthesizer_
  - _Requirements: 5.1, 5.2, 5.3, 5.4_

- [x] 2.6 (P) Implementar o construtor do grafo mínimo
  - Gerar nós de workspace, repositórios, providers, capabilities, nós do plano, evidências e artifacts, e arestas de contenção, dependência entre repositórios, declaração, uso, alvo, dependência entre nós (explícita para plano em arquivo, inferida com regra para plano decomposto), produção e handoff, cada uma com evidência
  - Descartar com limitação toda aresta sem evidência, com extremidade inexistente ou inferida sem regra, ordenar nós e arestas de forma estável e truncar evidências e artifacts acima do limite de nós
  - Concluído quando testes provarem as arestas esperadas para um plano executado, o descarte de arestas inválidas com limitação e o mesmo JSON para as mesmas entradas
  - _Boundary: GraphBuilder_
  - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6_

- [x] 2.7 (P) Implementar a estimativa pela operação `plan` e a comparação de decisões de policy
  - Chamar `plan` somente em providers que a declaram, com cwd temporário, ambiente mínimo, tempo limite e conferência de `producer`, lendo a estimativa (contexto necessário, classe de operação, artifacts esperados, incógnitas)
  - Converter ausência da operação e qualquer falha em estimativa desconhecida com limitação, sem falhar o planejamento, e nunca chamar `verify` nem `estimate`
  - Oferecer a escolha da decisão mais restritiva entre duas decisões de policy
  - Concluído quando testes com a fixture provarem estimativa registrada, limitação para provider sem `plan`, para resposta de erro e para tempo esgotado, e a ordem `deny` > `ask` > `allow`
  - _Boundary: Estimator_
  - _Requirements: 10.1, 10.3, 10.4_

- [x] 2.8 (P) Implementar o plano de instalação somente de planejamento
  - Reunir em no máximo um plano por run os providers referenciados (ou registrados, na decomposição) em estado inválido, inacessível ou incompatível e os de health indisponível, com motivo e ação sugerida vindos do registry ou do provider
  - Não produzir plano sem itens e nunca executar nada além de describe e health
  - Concluído quando testes provarem um único plano com itens de registry e de health, ausência de plano sem itens e o marcador somente de planejamento
  - _Boundary: Installation_
  - _Requirements: 10.5, 10.6_

- [x] 3. Núcleo de verificação, reprodutibilidade e diagnóstico
- [x] 3.1 (P) Implementar a construção do resultado de verificação
  - Registrar o auto-relato com o status declarado pelo provider e a evidência do provider com contagens por status epistêmico, com hash e com localização
  - Executar como verificação de The Forge a integridade do resultado, o `producer`, a reverificação de contexto conforme o nível do perfil (mínimo registrado como não executado) e o hash de cada artifact declarado no diretório de trabalho, aprovando só se todas as executadas passarem
  - Registrar a verificação independente como não executada com o motivo de `verify` reservada
  - Concluído quando testes provarem os quatro níveis em resultados com e sem evidências, a falha por artifact adulterado ou ausente, a reverificação não executada em nível mínimo e que auto-relato nunca aparece como verificação de The Forge
  - _Boundary: Verification_
  - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_

- [x] 3.2 (P) Implementar a avaliação de reprodutibilidade
  - Classificar como `unknown` runs sem execução de provider, como `non_reproducible` os com acesso externo, classe de operação externa ou destrutiva, divergência de contexto ou handoff de nó não reproduzível, como `reproducible` só quando todas as condições do design valem (incluindo execução determinística declarada) e os demais como `partially_reproducible`, sempre com motivos
  - Combinar níveis de nós pelo menos reprodutível
  - Concluído quando um teste por tabela cobrir cada condição isolada e a combinação, inclusive que determinismo não declarado nunca resulta em `reproducible`
  - _Boundary: Reproducibility_
  - _Requirements: 14.1, 14.2, 14.3_

- [x] 3.3 (P) Implementar o diagnóstico redigido
  - Montar a partir de uma exceção o estágio, código, família, tipo, mensagem e cadeia de causas redigidos, e os quadros apenas de módulos de The Forge como módulo, função e linha, sem caminhos absolutos nem variáveis locais
  - Concluído quando testes provarem que um segredo na mensagem e em uma causa sai redigido, que quadros de fora do pacote são omitidos e que o texto bruto de traceback nunca aparece no diagnóstico
  - _Boundary: Diagnostics_
  - _Requirements: 13.5, 15.3_

- [x] 4. Integração no orquestrador de um provider
- [x] 4.1 Permitir fixar o provider e vincular o run a um nó de plano
  - Aceitar no pedido de execução um provider fixado, que substitui a seleção do routing explícito quando roteável, vira `no_route` com motivo quando não é, e nunca usa fallback de health
  - Aceitar o vínculo com o nó do plano: registrar plano e nó na tarefa, usar o padrão do plano na decisão de routing, gravar o handoff como artefato antes da execução, enviá-lo no request de execução, registrar seu hash e o vínculo no receipt e a limitação quando a capability não declara consumo de handoff
  - Aceitar no pedido o vínculo de replay com o run original e gravá-lo no receipt
  - Manter `ask` sem esses campos exatamente como hoje
  - Concluído quando testes de integração provarem provider fixado unhealthy sem tentativa de fallback, o handoff recebido pela fixture igual ao persistido, o hash no receipt, a limitação para capability sem declaração (e ausência dela com o modo de consumo declarado), um run pedido com vínculo de replay com esse vínculo no receipt, e a suíte de `ask` existente inalterada
  - _Requirements: 3.2, 3.3, 4.6, 4.7, 4.8_

- [x] 4.2 Aplicar a estimativa mais restritiva na policy do nó
  - Quando o nó traz classe de operação estimada, avaliar a policy para a classe declarada e para a estimada e aplicar a decisão mais restritiva, registrando no risco a classe efetiva e a limitação
  - Concluído quando um teste com a estimativa mais restritiva da fixture exigir aprovação para uma capability declarada como somente leitura e um teste sem estimativa mantiver a decisão atual
  - _Depends: 2.7_
  - _Requirements: 10.2_

- [x] 4.3 Registrar verificação, reprodutibilidade e diagnóstico em todo run de um provider
  - Após o resultado validado e a reverificação de contexto da Wave C, gravar a verificação, marcar o run como `partial` com limitação quando um artifact diverge e vincular a verificação ao receipt
  - Calcular o nível de reprodutibilidade em todo desfecho e gravá-lo no receipt
  - Em erro interno, guardar o diagnóstico no desfecho e, com debug pedido, gravá-lo como artefato do run
  - Concluído quando testes provarem a verificação vinculada ao receipt em um run `ok`, `partial` por artifact adulterado, run do echo `reproducible`, run de fixture sem determinismo `partially_reproducible`, recusa de policy `unknown`, e o artefato de diagnóstico gravado só com debug
  - _Depends: 3.1, 3.2, 3.3_
  - _Requirements: 9.5, 9.6, 13.5, 14.1, 14.2_

- [x] 5. Executor de plano
- [x] 5.1 Implementar o planejamento e a persistência do run do plano
  - Criar o run do plano, descrever o workspace, obter o plano por decomposição ou por arquivo, validá-lo, obter as estimativas, verificar health dos providers do plano e montar o plano de instalação, persistindo tarefa, descritor de workspace (`workspace-descriptor`), decisão de routing, plano e instalação antes de executar qualquer nó
  - Encerrar com `refused` e o primeiro código de violação para plano rejeitado, com `ambiguous`/`no_route` da decomposição, ou com `planned` quando só o planejamento foi pedido, gravando o grafo, a telemetria do run do plano (contrato de telemetria da Wave C com tempos de varredura e routing, providers executados = nós executados e o retrato do perfil) e o receipt de plano com o hash da telemetria em todos os casos
  - Converter erro inesperado em receipt de falha interna com diagnóstico e telemetria
  - Concluído quando testes provarem que nenhum processo de execução de nó é iniciado em plano rejeitado, ambíguo ou só planejado, que o plano está persistido antes do primeiro nó, que a estimativa e o plano de instalação aparecem no run, e que a telemetria do run do plano existe e está vinculada ao receipt em cada desfecho
  - _Depends: 2.2, 2.3, 2.6, 2.7, 2.8, 4.1_
  - _Requirements: 1.2, 1.3, 1.5, 1.6, 1.7, 2.4, 2.5, 2.6, 2.8, 7.7, 10.1, 10.3, 10.4, 10.5_

- [x] 5.2 Implementar a execução sequencial, a falha parcial e o fechamento do plano
  - Executar os nós um por vez na ordem topológica, montando o handoff de cada um a partir das dependências declaradas, passando a estimativa e as aprovações da capability do nó, e relendo o resultado válido de cada run de nó
  - Marcar como não executados, com o nó bloqueante, os dependentes de um nó sem resultado válido e continuar os independentes
  - Calcular o status do plano pelas regras do design, a síntese, a reprodutibilidade combinada, o resultado de plano, o grafo com evidências produzidas, a telemetria do run do plano com a quantidade de nós executados e o receipt de plano vinculando tudo por hash
  - Concluído quando testes de integração com as fixtures provarem a tarefa de prova `ok` com dois runs de nó e o handoff do primeiro no segundo, recusa de policy no primeiro nó bloqueando o segundo com o plano falho, nó independente executado mesmo com falha de outro, `--approve` liberando só os nós da capability, execuções sem sobreposição na ordem esperada e a telemetria do plano contando os nós executados
  - _Depends: 2.4, 2.5, 3.2, 4.2, 4.3_
  - _Requirements: 3.1, 3.4, 3.5, 3.6, 3.7, 3.8, 4.3, 5.5, 6.2, 8.1, 14.3_

- [x] 5.3 Gate de integração da metade multi-provider
  - Rodar sobre a costura (a) as checagens no estilo de `/kiro-validate-impl`: lint, checagem de tipos, paridade de schemas, verificação de taxonomia, a suíte offline completa, a direção de imports do design para `workspace`, `planning` e `forger`, a decomposição da tarefa de prova com os manifests empacotados da Wave B e o fluxo de plano com as fixtures
  - Conferir a rastreabilidade dos requisitos 1–10 e 14.1–14.3 contra testes existentes e registrar no relatório do gate qualquer lacuna como tarefa corretiva antes de seguir
  - Avisar `agentic-maintainability` para re-checar a consolidação (docs, exit codes, índice de ADRs) sobre esta metade
  - Concluído quando todas as checagens passarem sem falhas e nenhuma tarefa das costuras (b) explain/integridade/replay e (c) governança de erros tiver sido iniciada antes disso
  - _Depends: 5.1, 5.2_
  - _Requirements: 15.2, 15.5_

- [x] 6. Explain, integridade e replay
- [x] 6.1 (P) Implementar a verificação de hashes de runs
  - Comparar cada hash registrado no receipt (entradas, rodadas de contexto, resultado, telemetria, verificação, handoff e referências de plano) com o artefato em disco, e cada artifact declarado no resultado com o arquivo no diretório de trabalho
  - Em runs de plano, conferir as referências do plano (plano, descritor de workspace, grafo, instalação, resultado de plano) e a telemetria do próprio run do plano, e o receipt de cada run de nó contra o hash registrado no resultado de plano, verificando esses runs
  - Classificar divergências como modificado, ausente ou ilegível e artefatos sem hash registrado como não registrados, sem escrever nada nem iniciar providers
  - Concluído quando testes provarem detecção de resultado alterado, contexto apagado, artifact alterado, receipt de nó alterado e telemetria do run do plano alterada, run antigo sem divergência, e o diretório do run intacto após a verificação
  - _Boundary: HashCheck_
  - _Depends: 1.5, 5.3_
  - _Requirements: 12.1, 12.2, 12.4, 12.5_

- [x] 6.2 Implementar o relatório de explain
  - Montar o relatório com intenção, sinais, candidatos, seleção, fallbacks, notas de routing da Wave B (alias, depreciação, sobreposição), contexto e budget (com não casados, resumo git e drift da Wave C), provider e versão, findings e contagem de evidências, duração, risco, telemetria, verificação, reprodutibilidade, limitações, incógnitas, erro com família, integridade e artefatos crus
  - Acrescentar para runs de plano o plano, o estado de cada nó com seu run, os handoffs, o descritor de workspace, a instalação, a síntese e a telemetria do run do plano
  - Listar como não registradas as seções ausentes e tratar reprodutibilidade ausente como `unknown`, inclusive em runs anteriores a esta spec
  - Concluído quando testes provarem todas as seções em um run de `ask` e em um run de plano, as seções não registradas de um run no formato anterior e a validação do JSON contra o schema publicado do relatório
  - _Depends: 5.3, 6.1_
  - _Requirements: 11.1, 11.2, 11.3, 11.4, 14.4, 15.4_

- [x] 6.3 Implementar o replay com re-render, re-verify e re-execute
  - Re-render reapresenta o relatório sem executar providers nem ler o workspace
  - Re-verify combina a verificação de hashes com a reverificação de contexto da Wave C sobre os itens registrados, sem executar providers nem escrever, e sinaliza divergência para a CLI sair com 6 (mesmo exit de integridade do explain)
  - Re-execute (consumindo o vínculo de replay do orquestrador da tarefa 4.1) recusa runs de plano com o código de não suportado e runs `non_reproducible`/`unknown`, com contexto alterado ou com provider de identidade ou versão diferente com o código de não reproduzível; quando elegível, executa um novo run com os parâmetros originais, provider fixado e vínculo ao original, e compara os resultados sem campos voláteis
  - Concluído quando testes provarem render sem leitura do workspace, verify apontando arquivo de contexto alterado, execute de um run do echo criando um novo run vinculado com resultado igual, cada recusa sem processo de provider iniciado, e o run original intacto
  - _Depends: 4.3, 6.2_
  - _Requirements: 14.5, 14.6, 14.7, 14.8, 14.9_

- [x] 7. CLI governada
- [x] 7.1 Governar mensagens de erro, códigos de saída e o modo debug
  - Exibir todo erro (cujos códigos foram definidos na tarefa 1.1) com `[código · família]`, mantendo explicitamente os prefixos atuais `theforge: error:`, `theforge: persistence error:` (erro de persistência, exit 5), `theforge: internal error:` e `theforge: interrupted`, e mostrando códigos nativos de provider como código de provider
  - Garantir que erros internos inesperados nunca exibam traceback e acrescentar a opção comum de debug, que imprime o diagnóstico redigido e repassa o pedido de debug ao orquestrador
  - Manter os códigos de saída documentados e acrescentar 0 para `planned`, 4 para recusa de replay e 6 para divergência de integridade (explain e replay em modo verify), sem introduzir nenhum exit fora dos valores por desfecho somados aos fixos {1, 2, 5, 6, 70, 130} que `agentic-maintainability` confere
  - Concluído quando testes de CLI provarem a mensagem governada com o prefixo atual em erro de uso, de persistência e interno (sem `Traceback`, exit 70), o diagnóstico só com debug e com segredo redigido, os códigos de saída existentes inalterados e o conjunto total de exits igual aos valores por desfecho mais {1, 2, 5, 6, 70, 130}
  - _Depends: 3.3, 4.3, 5.3_
  - _Requirements: 13.4, 13.5, 13.6, 13.7, 15.3_

- [x] 7.2 Expor `plan` e `workspace show` na CLI
  - Oferecer `plan` com intenção, perfil, alvos, plano em arquivo, execução opcional, aprovações por capability e permissão de não verificados, renderizando plano, nós, handoffs, síntese, instalação e desfecho em texto e JSON
  - Dizer no texto de ajuda de `plan` que, sem plano em arquivo, a ordem dos nós segue a ordem textual das keywords na intenção (regra `intent-order`), um proxy do fluxo de dados que pode inferir uma dependência errada, e que `--from FILE` fixa a ordem explicitamente
  - Oferecer `workspace show` em texto e JSON usando apenas manifests do cache do registry, sem iniciar processo de provider
  - Concluído quando testes de CLI provarem `plan` sem execução com exit 0 e plano exibido, `plan --execute` da tarefa de prova com as fixtures, a ajuda de `plan` citando a regra `intent-order` e `--from FILE`, e `workspace show` sem processo de provider iniciado
  - _Depends: 5.2, 7.1_
  - _Requirements: 2.8, 3.7, 7.8_

- [x] 7.3 Expor `explain` versionado e `replay` na CLI
  - Fazer `explain` renderizar o relatório em texto e, com JSON, emitir o relatório versionado, com exit 6 quando houver divergência de integridade
  - Preservar no texto, com o mesmo formato, as seções da Wave C lidas dos artefatos crus de contexto, rodadas e telemetria (itens com tier e sinais, exclusões, não casados, git, rodadas de negociação, drift e a linha `Telemetry:`) e as notas de routing da Wave B (alias, depreciação, sobreposição), acrescentando as seções novas depois delas
  - Oferecer `replay` com os três modos e aprovações, exibindo divergências, novo run e comparação, com exit 6 em `--mode verify` quando houver divergência e 0 sem divergência
  - Migrar os testes existentes que leem o `explain --json` antigo (inclusive o da Wave C sobre telemetria) para os artefatos crus do relatório
  - Concluído quando testes de CLI provarem as seções do explain em texto (incluindo a linha `Telemetry:` de um run de plano e uma nota de alias de routing), o JSON validado contra o schema, exit 6 após adulterar um artefato, os três modos de replay com exit 6 em verify divergente, a suíte existente passando com os testes migrados e os testes de texto do explain da Wave C e de notas de routing da Wave B passando sem mudança de asserção
  - _Depends: 6.3, 7.1_
  - _Requirements: 11.1, 11.4, 12.3, 14.5, 14.7_

- [x] 8. Prova cross-forge
- [x] 8.1 Provar o fluxo de plano offline com providers de teste
  - Acrescentar à suíte de fluxo de plano a matriz de cenários de ponta a ponta (os casos de nível do executor ficam nas tarefas 5.1 e 5.2): a tarefa de prova no workspace montado em `max`, plano em arquivo válido e inválido, estimativa e estimativa mais restritiva, erro na operação `plan`, provider inválido gerando plano de instalação, provider sem conhecimento de handoff concluindo `ok` e o comportamento em `balanced`
  - Concluído quando o teste passar na suíte offline principal sem rede, credenciais nem repositórios irmãos, e o `explain` do run do plano não apontar divergência
  - _Depends: 7.2, 7.3_
  - _Requirements: 6.4, 1.6, 2.6, 4.8, 10.1, 10.2, 10.3, 10.5_

- [x] 8.2 Provar o fluxo de plano com os adapters reais em replay
  - Criar e possuir os cenários de replay `tests/fixtures/native/sparkforge/scenarios/cross/` e `tests/fixtures/native/apiforge/scenarios/cross/` no formato de cenário completo da Wave B (ambiente, health e uma gravação por ação exercitada sobre o workspace de prova): a do Spark Forge gravada com o auxiliar de gravação da Wave B a partir do Spark Forge real local, a do API Forge montada à mão e marcada como de proveniência manual até a primeira execução do workflow real; os cenários `default` da Wave B não são alterados
  - Registrar os adapters da Wave B em modo replay sobre esses cenários como Spark Forge e API Forge e executar a tarefa de prova no workspace montado
  - Concluído quando os cenários estiverem completos (nenhuma ação exercitada sem gravação) e o teste offline provar a decomposição em `pyspark.static-analysis` seguido de `api.analyze`, o handoff entregue e ignorado sem erro pelos adapters, a limitação de uso de handoff não declarado e a síntese com IDs de evidência nativos dos dois nós
  - _Requirements: 6.2, 6.4, 4.7, 15.1_

- [x] 8.3 Provar o fluxo de plano com Spark Forge e API Forge reais
  - Criar o teste de integração real selecionável pelo marker de providers reais, usando o contrato de ambiente da Wave B para pular com motivo ou falhar quando os Forges reais são obrigatórios
  - Executar a tarefa de prova em `max` com execução, conferindo os dois nós reais, ao menos um item de handoff com origem no Spark Forge e status epistêmico original recebido pelo nó de API, a síntese referenciando os dois runs e o `explain` sem divergência
  - Concluído quando o teste pular com motivo explícito nesta máquina sem os interpretadores configurados, for coletado pela seleção `-m real_provider` usada pelo workflow agendado de providers reais, e ficar fora da suíte principal
  - _Depends: 8.2_
  - _Requirements: 6.1, 6.2, 6.3, 6.5_

- [x] 9. Documentação, ADRs e gates finais
- [x] 9.1 Documentar protocolo, autoria de providers, arquitetura e segurança
  - Documentar no protocolo a operação `plan` (request, resposta, limites), o campo de handoff (formato, limites, ausência de conteúdo, redação, consumo opcional), as declarações de consumo de handoff e de execução determinística, as operações que continuam reservadas e a lista atualizada de nomes reservados; repetir as obrigações no guia de autoria de providers
  - Atualizar a arquitetura com o fluxo de plano, os pacotes novos e a direção de imports, e a segurança com handoff, op `plan`, relações de workspace, diagnóstico de debug e a âncora de confiança do receipt
  - Fazer o protocolo apontar para `docs/errors.md` como lista canônica de códigos em vez de manter tabela concorrente, e estender o teste de taxonomia com a paridade documental: o protocolo tem o link, todo código `FORGE-*` citado nele existe em `docs/errors.md` e nenhuma tabela dele atribui família diferente
  - Concluído quando cada código novo de plano, workspace, persistência e replay estiver em `docs/errors.md`, o teste de paridade documental passar e os documentos citarem os contratos novos pelo nome `theforge/<Name>/v1`
  - _Requirements: 10.4, 13.2, 15.6_

- [x] 9.2 Documentar a CLI e registrar os ADRs 0018 e 0019
  - Documentar `plan` (inclusive o limite da regra `intent-order` e `--from FILE` como ordem explícita), `workspace show`, `replay` (exit 6 em verify divergente), `--debug`, as mensagens governadas com os prefixos mantidos, o exit 6, a estrutura do relatório de explain e sua regra de evolução aditiva dentro da mesma versão
  - Criar o ADR 0018 do modelo de execução multi-provider (plano local sequencial, run por nó, handoff, ativação de `plan`, `verify`/`estimate` e padrões reservados, e a ordem textual da intenção como proxy do fluxo de dados que pode inferir dependência errada, com `--from FILE` como alternativa explícita) e o ADR 0019 da taxonomia de erros e do modelo de reprodutibilidade e replay, sem renumerar
  - Se `theforge.__version__` mudou nesta spec, acrescentar a linha da matriz de compatibilidade em `docs/versioning.md` exigida pelo teste de matriz da Wave B
  - Concluído quando os ADRs 0018 e 0019 existirem com status aceito, a documentação da CLI listar todos os comandos e códigos de saída implementados e o teste de matriz de compatibilidade da Wave B passar
  - _Requirements: 10.4, 11.5, 15.6, 15.7_

- [x] 9.3 Executar os gates finais
  - Rodar lint, checagem de tipos estrita, paridade de schemas, a verificação de taxonomia e a suíte offline completa, mais um teste de ponta a ponta da CLI com `plan --execute` seguido de `explain` em subprocesso
  - Confirmar a ausência de dependências de runtime novas e de imports fora da direção definida no design
  - Tratar este gate como o gate das costuras (b) e (c), no mesmo estilo do gate 5.3, e avisar `agentic-maintainability` para re-checar a consolidação
  - Concluído quando lint, tipos, paridade de schemas, taxonomia (com a paridade documental) e a suíte offline passarem sem falhas, nenhum teste novo ficar fora da tabela de categorias e o pacote continuar sem dependências de runtime
  - _Requirements: 13.2, 15.2, 15.5_

## Implementation Notes
- Cross-spec review (minor, open): extend B's live drift check to scenarios/cross (hand-built API recording) in the real test, or note it beside the provenance=hand-built marker; D may own adding protocol.md -> errors.md links in 9.1 if B/C skipped them. Open user decision: split D into D1 (multi-provider) / D2 (integrity+explain+errors).
- 1.1 (2026-10-04): codes.py ErrorFamily/CODE_FAMILIES/family_of; ForgeError.code (class default_code; code outside taxonomy → ValueError); UsageError(code=Codes.PLAN_FILE) for plan files (2.2); ReplayRefused(reasons, code=REPLAY_*) not yet caught in cli/main.py → 7.1 must map to exit 4 and catch ForgeError generically. New code ⇒ update codes.py + CODE_FAMILIES + docs/errors.md + tests/golden/forge_codes.json together. FORGE- literal guard lives in tests/test_codes.py.
- 1.2/1.3 (2026-10-04): new contracts in contracts/{plan,handoff,workspace,graph,verification,installation,explain,diagnostic}.py, in-memory NodeExecution/SourceResult in planning/execution.py; NOT yet exported in contracts/__init__.py / schema.py EXPORTED (1.5). ExecuteRequest emits `handoff: null` (asdict precedent, schema open). `planned` already a valid receipt status — 1.5 must restrict it to plan receipts; CLI EXIT_BY_STATUS lacks `planned` (→ 4, design wants 0) — 7.1/7.2. 1.4 must reject PlanResult.status outside ok/partial/refused/provider_failure. Diagnostic.family must equal family_of(code); frames only theforge modules.
- 1.4/1.5 (2026-10-04): integrity.py — validate_plan_structure(plan)->list[PlanViolation] (pure; codes PLAN_LIMIT/PLAN_PATTERN_RESERVED/PLAN_INVALID; empty plan rejected), validate_handoff (PLAN_LIMIT), check_graph_edge(edge, node_ids) for GraphBuilder, validate_graph (WORKSPACE_GRAPH_EDGE), validate_plan_result (PLAN_INVALID). Receipt: kind/parent_run/plan_node/replay_of/verification_sha256/reproducibility/plan(PlanRefs), inputs.handoff_sha256. Executor must write plan-result and telemetry BEFORE the plan receipt (RunStore.write checks disk hashes). check_plan (2.2) must call validate_plan_structure. Follow-ups (non-blocking): test duplicate dependency; reject skipped blocked_by == itself.
- 1.6 (2026-10-04): tests/helpers.py SPARK_PLAN_ENTRY/API_PLAN_ENTRY (fixture manifests fixture-*-plan.json declare op `plan` + estimate); base entries don't declare plan. fixture_forge echoes handoff as evidence e2 "received N handoff items". bad_forge modes plan-error, plan-estimate-stricter, handoff-accept, artifact-tamper (SWEEP currently `ok` → must become partial + FORGE-RESULT-ARTIFACT-HASH when artifact re-verification lands), internal-crash. tests/cross_workspace.py mount_cross_workspace(git=True) in system temp; fixture-api lacks accepts_handoff (expect handoff limitation). test_adapters_core proof uses union of root + per-repo dependencies (design line ~1014).
- 2.4 (2026-10-04): planning/handoff.py build_handoff(plan_run, target, sources, *, created_at=None) -> Handoff|None (None when no inputs); already redacted — persist/deliver as is; add handoff.limitations (handoff-truncated, handoff-input-missing) to the dependent node; graph handed_off_to evidence = items kind=evidence with origin.node == source.
- 2.1 (2026-10-04): workspace/describe.py describe_workspace(root, records, scan, *, git_reader, clock, git_budget_s); repository_of; relations.load_relations; Registry.cached_records(); routing.signals.dependencies_by_file. Follow-up: reject symlinked .forge/config/workspace.toml like .forge.
- 2.2 (2026-10-04): planning/order.py topological_order, blocked_by(node, plan, failed); planning/validate.py check_plan(plan, records, profile), checked_plan, load_plan_file(path, records, *, plan_run, profile, created_at) (MAX 1 MiB). Executor/decomposer: use checked_plan(plan, records, profile_for(name)).
- 2.5–2.7 (2026-10-04): planning/synthesis.synthesize(plan, executions in effective order, one per node; skipped → handoff=None); planning/graph.build_graph(plan_run, descriptor, records, plan, plan_sha256, outcomes, *, created_at, max_nodes) — pass a fixed created_at for byte-identical replays; planning/estimate.request_estimate(record, task, capability, action, *, transport_factory, timeout, allow_unverified=False) -> (estimate|None, limitation|None), stricter_decision(a, b). None of these are re-exported from planning/__init__.py yet.
- 2.8 (2026-10-04): planning/installation.build_installation_plan(run_id, plan|None, records, health, *, created_at) -> InstallationPlan|None; caller runs check_health once per distinct provider first; extra state 'absent' (ABSENT_STATE) for unregistered referenced providers (req 10.5). Committed with a light controller review (planning-only builder, 19 tests).
- 2.3 (2026-10-04): planning/decompose: decomposition_dependencies(root, descriptor), decompose(task, decision, records, descriptor, scan, profile) -> Decomposition, decomposed_plan(...) (checked_plan). Pipeline only when profile.max_providers ≥ 2 (max); proof task in balanced = ambiguous + limitation 'multi-provider decomposition not allowed by profile'. Proof via real adapters in replay yields pyspark.static-analysis → api.analyze.
- 3.1–3.3 (2026-10-04): forger/verification.build_verification(run_id, response_status, result, drift, work_dir, *, expected, created_at) — pass provider's own status and the result BEFORE apply_drift; copy FORGE-RESULT-ARTIFACT-HASH limitations into run limitations, run → partial; persist via RunStore (redacts paths). forger/reproducibility.assess_run(...)/combine_levels (unknown ranks between non_reproducible and partial — a plan with a skipped node combines to unknown; record in ADR 0019). diagnostics.build_diagnostic(exc, *, stage, code, created_at) (already redacted; suggestion: cap message length). bad_forge artifact-tamper SWEEP must flip to partial when 4.3 wires verification.
- 4.1–4.3 (2026-10-04, one commit — intertwined in orchestrator.py): AskRequest(provider, node: NodeBinding, replay_of, debug); NodeBinding has extra field `upstream: tuple[Reproducibility, ...]` (DESIGN ADDITION — executor 5.2 must fill with handoff source levels). Pinned provider not routable → no_route "pinned provider <id> is not routable for …"; unhealthy pinned → provider_failure, limitation "pinned provider <id>: fallback not attempted". Diagnostic persisted only with debug=True (design 1167). Follow-ups: verification not written when an internal error happens after execute; AskOutcome.error.detail unredacted in memory on internal error (7.1 CLI must print redacted).
- 5.1/5.2 (2026-10-04, one commit): forger/plan_executor.py PlanExecutor(forger).run(PlanCommand) -> PlanOutcome, plan_status. PlanRefs.plan_sha256 optional (required for planned/ok/partial). build_graph works without a plan. Plan-file task_id replaced by the run's. Unreadable plan file → refused plan receipt (PLAN_FILE) then UsageError re-raised. Internal error → provider_failure INTERNAL, diagnostic only with debug. CLI 7.x: PlanExecutor(Forger(...)).run(PlanCommand(...)); map `planned` → exit 0. 6.1: plan receipts may have plan_sha256/routing None. Follow-ups: guard double _finish on non-persistence error; redact PlanOutcome.error.detail in CLI; add 3-node chain blocked_by test.
- 5.3 (2026-10-04): gate GO (report .kiro/specs/cross-forge-foundation/gate-5.3.md): ruff, mypy 114, parity 24 schemas, offline 2622 passed/5 skipped in 3 chunks, slow 4, imports OK. Fix F1 committed. Corrective C1 (handoff-truncated limitation integration test) and C2 (plan_flow proof checks verification_sha256 + reproducibility per node) — done in follow-up commit. C3 (doc: meta/state base modules) → 9.1.
- 6.1 (2026-10-04): explain/hashcheck.verify_run_hashes(store, run_id, *, depth=0) -> IntegrityReport (MAX_DEPTH=1); explain exit 6 and embedding are 6.2; replay re-verify (6.3) calls it. FYI RunStore.read_optional follows symlinked <name>.json (pre-existing).
- 6.2 (2026-10-04): explain/report.build_explain_report(store, run_id, *, created_at) -> ExplainReport; ValueError (bad id)/LookupError (unknown) → 7.3 maps to exit 2; exit 6 when integrity.divergences. Text: render.explain({'run_id', **report.artifacts}) reproduces Wave B/C text. Follow-ups: test plan run with installation artifact; stronger reproducibility asserts.
- 6.3 (2026-10-04): forger/replay.replay(forger, store, run_id, mode, *, approvals, allow_unverified, created_at) -> ReplayReport (import from theforge.forger.replay). Errors: UsageError (mode), ValueError/LookupError (id) → exit 2, ReplayRefused → exit 4, divergences → exit 6. Follow-up hardening: refuse execute when the replay inputs (task, context*, receipt) diverge from recorded hashes.
- 7.1 (2026-10-04): cli/main EXIT_* constants (EXIT_INTEGRITY=6 for explain/replay in 7.3; literals must stay in {0..6,70,130}); commands.error_family, print_debug; render.code_suffix, render.diagnostic, _detail collapses tracebacks (text only; --json error.detail still carries redacted stderr tail — decide in 7.3/9.x). 7.2 plan: redact display dict, debug=args.debug, EXIT_BY_STATUS (planned→0).
- 7.2/7.3 (2026-10-04, one commit): 9.2 MUST update docs/cli.md: explain --json shape (artifacts.<name>, absent omitted — line ~79), explain exits 0/2/6 (line ~17), ExplainReport v1 additive rule (11.5), replay new_status, plan/workspace show/replay commands, [code · family], --debug, planned→0, JSON traceback collapse.
- 8.x (2026-10-04): real proof PASSED locally (sparkforge-aws 0.5.0 + apiforge 0.1.0): plan ok, n2 received Spark evidence (16 handoff items real vs 12 replay), handoff-use-undeclared for api-forge (real API Forge doesn't declare accepts_handoff — document in 9.x). No findings on cross workspace → native ids proven on node results/handoff items, not synthesis.findings. API cross recording is hand-built from a win32 live run.
