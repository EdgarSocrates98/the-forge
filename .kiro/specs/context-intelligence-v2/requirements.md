# Requirements Document

## Project Description (Input)
Wave C do Cycle 2 de The Forge. Quem tem o problema: usuários de The Forge (que pagam o custo do contexto entregue aos providers) e mantenedores (que precisam de dados antes de otimizar). Situação atual: o Context Broker (`src/theforge/context/broker.py`) seleciona arquivos só por globs declarados pelo provider e por um budget em bytes (64 KiB / 256 KiB / 1 MiB); não usa git, não tem cache (`.forge/cache/` é criado e nunca usado), não revalida o conteúdo depois da execução (só o echo provider confere o sha256); os perfis `economy`, `balanced` e `max` diferem apenas em bytes e timeout; não há métricas de contexto por run nem baseline de performance. O que deve mudar: tiers de contexto, sinais git somente leitura, cache de fingerprints mensurável e conservador, estratégia TOCTOU documentada no protocolo, bytes ≠ tokens, perfis materialmente diferentes, telemetria por run e baseline de performance medido antes de otimizar. Ver `brief.md` (requisitos semente 11, 12 e 17 de `cycle2-reality-hardening`).

## Introduction
Esta spec evolui o Context Broker de The Forge para entregar ao provider o contexto mais barato suficiente, explicável e íntegro, sem abandonar o mecanismo atual de ContextPack por referência (sem conteúdo, com sha256). Ela também torna os perfis `economy`, `balanced` e `max` materialmente diferentes, registra telemetria por run e estabelece um baseline de performance medido, a partir do qual os budgets de regressão são definidos. Toda seleção continua determinística, sem embeddings nem LLM, e sem conhecimento de domínio no core.

## Boundary Context
- **In scope**: tiers de contexto; sinais de relevância determinísticos (globs, arquivos de dependência, alvos e caminhos explícitos da tarefa, git somente leitura); explicação por arquivo; cache de fingerprints de arquivos; detecção de divergência entre hash e leitura (TOCTOU) e a obrigação correspondente documentada no protocolo; orçamento em bytes e tokens com tipo de medição; pedido de contexto adicional negociado e limitado; parâmetros dos perfis `economy`/`balanced`/`max`; telemetria por run; baseline de performance e budgets de regressão.
- **Out of scope**: embeddings, busca semântica ou LLM; execução de mais de um provider em um mesmo run, `ExecutionPlan`, `WorkspaceDescriptor`, `VerificationResult` e o formato completo de `explain` (pertencem a `cross-forge-foundation`); adapters reais, conformance e taxonomia de capabilities (pertencem a `real-provider-integration`); qualquer operação que modifique o repositório git analisado.
- **Adjacent expectations**: o ContextPack continua validado pelas regras de integridade de `cycle2-reality-hardening` (budget, soma de bytes, caminhos); `cross-forge-foundation` consome o limite de providers por perfil e o resumo de workspace desta spec sem que esta spec execute planos; mudanças aditivas nos contratos `ContextPack`, `ExecutionResult`, `ExecutionReceipt` e `ForgeManifest` são sinal de revalidação para `real-provider-integration` e `cross-forge-foundation`.

## Requirements

### Requirement 1: Tiers de contexto e seleção mais barata suficiente
**Objective:** As a usuário de The Forge, I want que o contexto seja classificado em tiers e que o tier mais barato suficiente seja sempre preferido, so that o provider receba o necessário sem desperdício de budget.

#### Acceptance Criteria
1. The Forge shall classificar cada item do ContextPack em exatamente um tier: `metadata` (resumo do workspace sem conteúdo de arquivo), `reference` (arquivo inteiro por caminho, hash e tamanho), `excerpt` (intervalo de linhas de um arquivo por caminho, intervalo, hash do intervalo e tamanho) ou `requested` (item incluído por pedido explícito do provider).
2. The Forge shall incluir o tier `metadata` em todo ContextPack, sem contabilizar bytes de conteúdo de arquivo no budget.
3. When um arquivo relevante cabe no budget restante e no limite de arquivos do perfil, The Forge shall incluí-lo como `reference`.
4. While o perfil permite o tier `excerpt` e a capability selecionada declara suporte a excerpts, when um arquivo relevante não cabe inteiro no budget restante, The Forge shall incluí-lo como `excerpt` do maior prefixo de linhas completas que caiba no budget, em vez de excluí-lo.
5. When a tarefa referencia explicitamente um intervalo de linhas de um arquivo do workspace, o perfil permite o tier `excerpt` e a capability selecionada declara suporte a excerpts, The Forge shall incluir esse intervalo como `excerpt` em vez do arquivo inteiro.
6. If a capability selecionada não declara suporte a excerpts, The Forge shall entregar apenas os tiers `metadata` e `reference` (e `requested`, quando negociado), mesmo que o perfil permita `excerpt`.
7. The Forge shall nunca incluir o conteúdo de arquivos no ContextPack nem nos artefatos do run; todo tier além de `metadata` é entregue por referência com hash.
8. When dois ContextPacks são gerados para a mesma tarefa, o mesmo provider, o mesmo perfil e o mesmo conteúdo de workspace, The Forge shall produzir a mesma seleção, na mesma ordem, com os mesmos tiers e motivos.

### Requirement 2: Sinais de relevância determinísticos
**Objective:** As a usuário de The Forge, I want que a relevância de um arquivo considere mais do que globs, sem embeddings nem LLM, so that o contexto inclua o que a tarefa realmente aponta.

#### Acceptance Criteria
1. The Forge shall considerar como sinais de relevância de um arquivo: casamento com os globs declarados pela capability selecionada, ser arquivo de dependência reconhecido do workspace, estar sob um alvo explícito da tarefa, ser citado por caminho na intenção da tarefa e, quando disponível, estar alterado segundo o git.
2. The Forge shall ordenar os arquivos candidatos por uma prioridade fixa e documentada entre os tipos de sinal e, em empate, pelo caminho relativo, de forma independente da ordem de varredura do sistema de arquivos.
3. When a intenção da tarefa cita um caminho relativo que existe no workspace e não é excluído por segurança, The Forge shall tratar esse arquivo como relevante mesmo que nenhum glob o case.
4. If a intenção da tarefa cita um caminho que não existe, aponta para fora da raiz do workspace ou corresponde a um arquivo de segredo, The Forge shall não incluí-lo e shall registrar o motivo da exclusão.
5. The Forge shall usar somente sinais declarados pelo provider ou derivados de forma genérica do workspace e da tarefa, sem regras específicas de domínio no core.
6. The Forge shall não usar embeddings, modelos de linguagem nem serviços de rede para selecionar contexto.

### Requirement 3: Sinais git somente leitura
**Objective:** As a usuário de The Forge, I want que o estado git do workspace oriente a relevância sem nenhum risco de alterar o repositório, so that arquivos em trabalho tenham prioridade com segurança.

#### Acceptance Criteria
1. Where o workspace é um repositório git e o git está disponível, The Forge shall registrar no tier `metadata` o branch atual (ou HEAD destacado), o commit HEAD, se há alterações e a contagem de arquivos alterados, e shall usar os arquivos alterados como sinal de relevância.
2. The Forge shall não executar nenhuma operação que modifique o repositório git analisado, incluindo índice, refs, configuração, hooks, objetos e arquivos de trava.
3. The Forge shall consultar o git sem executar comandos ou programas configurados pelo próprio repositório analisado e sem repassar credenciais do usuário.
4. If o git não está disponível, o workspace não é um repositório git ou a consulta ao git falha ou excede o tempo limite, The Forge shall gerar o ContextPack sem sinais git e shall registrar a limitação correspondente no ContextPack.
5. If o repositório git está em estado não usual (sem commits, HEAD destacado, rebase ou merge em andamento), The Forge shall registrar esse estado e continuar a seleção sem falhar o run.

### Requirement 4: Explicação de seleção e exclusão
**Objective:** As a usuário de The Forge, I want saber por que cada arquivo entrou ou ficou fora do contexto, so that eu confie na seleção e consiga corrigi-la.

#### Acceptance Criteria
1. The Forge shall registrar, para cada item incluído no ContextPack, o tier e todos os sinais que o tornaram relevante.
2. The Forge shall registrar, para cada arquivo com ao menos um sinal de relevância que não foi incluído, um motivo de exclusão de um conjunto fechado e documentado: `budget`, `max_files`, `tier_not_allowed`, `secret`, `outside_root`, `unreadable`, `missing`, `symlinked_dir` ou `max_files_reached`.
3. The Forge shall registrar a quantidade de arquivos varridos sem nenhum sinal de relevância como um total agregado com o motivo `no_signal`, sem listá-los individualmente.
4. When `theforge explain <run>` é executado para um run com ContextPack, The Forge shall exibir os tiers usados, os itens incluídos com seus sinais e os arquivos excluídos com seus motivos.

### Requirement 5: Cache de fingerprints conservador
**Objective:** As a usuário de The Forge, I want que fingerprints de arquivos inalterados sejam reutilizados sem recalcular hash, so that runs repetidos fiquem mais baratos sem nunca entregar um hash desatualizado.

#### Acceptance Criteria
1. When nenhuma evidência de mudança é detectada em um arquivo desde que seu fingerprint foi registrado, The Forge shall reutilizar o fingerprint sem ler o conteúdo do arquivo.
2. If qualquer evidência de mudança for detectada (tamanho, data de modificação, data de alteração de metadados, identidade do arquivo ou caminho resolvido diferentes, ou data de modificação próxima demais do momento do registro para ser confiável), The Forge shall recalcular o hash a partir do conteúdo e nunca reutilizar o fingerprint anterior.
3. If o cache de fingerprints estiver ausente, ilegível, malformado, de versão desconhecida ou pertencer a outra raiz de workspace, The Forge shall descartá-lo, recalcular os hashes necessários e continuar o run sem falhar.
4. The Forge shall armazenar o cache de fingerprints fora do workspace analisado, de modo que o conteúdo do projeto não consiga gravar nem pré-popular fingerprints usados pelo core.
5. If a gravação do cache de fingerprints falhar, The Forge shall concluir o run normalmente e registrar um aviso.
6. The Forge shall produzir, para o mesmo conteúdo de workspace, ContextPacks com os mesmos hashes com o cache ativo ou ausente.

### Requirement 6: Divergência entre hash e leitura (TOCTOU)
**Objective:** As a usuário de The Forge, I want que uma mudança de arquivo entre a geração do hash e a leitura pelo provider fique explícita, so that nenhuma evidência derivada de conteúdo divergente seja tratada como confirmada.

#### Acceptance Criteria
1. If um item do ContextPack muda entre a geração do hash e a leitura pelo provider, e essa mudança é detectada pelo provider ou pela reverificação de The Forge, The Forge shall marcar o resultado do run como `partial` e registrar no resultado e no receipt os caminhos divergentes.
2. If uma evidência com status `confirmed` ou `observed` se refere a um item divergente, The Forge shall persistir essa evidência com status `unresolved` e com uma limitação que registre o rebaixamento e o status original.
3. When uma evidência do provider informa um hash para um item do ContextPack diferente do hash do ContextPack, The Forge shall tratar o item como divergente.
4. The Forge shall definir e documentar no protocolo e no guia de autoria de providers a obrigação do provider de revalidar o hash do conteúdo que leu, ou de declarar a estratégia alternativa adotada.
5. Where o provider declara no manifest sua estratégia de revalidação de contexto, The Forge shall registrar essa estratégia no run.
6. If o provider não declara sua estratégia de revalidação de contexto, The Forge shall registrar no run a limitação de que a revalidação pelo provider é desconhecida.
7. The Forge shall nunca reportar `ok` para um run em que uma divergência de contexto foi detectada.

### Requirement 7: Orçamento em bytes e tokens honestos
**Objective:** As a usuário de The Forge, I want que o orçamento de contexto seja reportado no que é medido, so that eu não confunda bytes com tokens.

#### Acceptance Criteria
1. The Forge shall reportar o orçamento e o uso de contexto em bytes medidos, incluindo os bytes de cada tier.
2. The Forge shall reportar tokens com o tipo `measured`, `estimated` ou `unknown`, e shall usar `unknown` sempre que não houver medição nem estimativa.
3. The Forge shall nunca apresentar bytes como tokens nem derivar uma contagem de tokens com tipo `measured` a partir de bytes.
4. When o provider informa tokens com tipo `measured` ou `estimated` no resultado, The Forge shall preservar o valor e o tipo informados no resultado persistido.

### Requirement 8: Pedido de contexto adicional negociado
**Objective:** As a autor de provider, I want pedir contexto adicional de forma controlada, so that o provider obtenha o que falta sem que o core perca o controle de policy e budget.

#### Acceptance Criteria
1. Where o provider declara no manifest suporte a pedido de contexto adicional para a capability selecionada, The Forge shall aceitar do provider um pedido estruturado de itens adicionais por caminho e, opcionalmente, intervalo de linhas.
2. When um pedido de contexto adicional é recebido, The Forge shall validá-lo contra as regras de caminho e segredo, contra o budget e o limite de arquivos do perfil, e incluir como `requested` somente os itens aprovados, registrando o motivo de cada item recusado.
3. The Forge shall limitar a negociação ao número de rodadas permitido pelo perfil, nunca acima de 2 rodadas por run.
4. If o provider pede contexto além do limite de rodadas, não declarou suporte ao pedido ou envia um pedido malformado, The Forge shall encerrar o run como `provider_failure` com código de erro específico e sem persistir resultado.
5. The Forge shall persistir cada ContextPack entregue em cada rodada e nunca tratar como resultado final a resposta que contém um pedido de contexto.
6. The Forge shall considerar como sucesso apenas o `ExecutionResult` final válido produzido após a última rodada.

### Requirement 9: Perfis economy, balanced e max materialmente diferentes
**Objective:** As a usuário de The Forge, I want que `economy`, `balanced` e `max` produzam comportamento diferente e previsível, so that eu controle custo e profundidade.

#### Acceptance Criteria
1. While o perfil é `economy`, The Forge shall usar apenas resolução determinística, os tiers `metadata` e `reference`, o menor budget e limite de arquivos, nenhum pedido de contexto adicional, nenhum fallback para outro provider e verificação mínima (sem reverificação de contexto após a execução, com essa limitação registrada no run).
2. While o perfil é `balanced`, The Forge shall usar contexto determinístico expandido (tiers `metadata`, `reference`, `excerpt` e, por negociação, `requested`), budget e limite de arquivos intermediários, no máximo 1 rodada de pedido de contexto adicional, fallback de health permitido e verificação condicional (reverificação após a execução dos itens referenciados por evidências `confirmed` ou `observed`).
3. While o perfil é `max`, The Forge shall permitir o maior budget e limite de arquivos, todos os tiers, no máximo 2 rodadas de pedido de contexto adicional, fallback de health permitido, um limite de providers por run maior que 1 disponível para a execução multi-provider quando o plano exigir, e verificação forte (reverificação de todos os itens do ContextPack após a execução).
4. The Forge shall registrar em cada run os parâmetros efetivos do perfil usado: budget, limite de arquivos, tiers permitidos, rodadas de negociação, limite de providers, fallback permitido e nível de verificação.
5. The Forge shall ter testes que provem diferença observável entre os três perfis em budget de contexto, número máximo de providers e nível de verificação, sobre o mesmo workspace e a mesma tarefa.
6. The Forge shall não executar mais de um provider em um mesmo run de `ask` em nenhum perfil; a execução multi-provider permitida pelo perfil `max` pertence ao executor de plano de `cross-forge-foundation`.

### Requirement 10: Telemetria por run
**Objective:** As a usuário e mantenedor de The Forge, I want métricas de custo registradas em cada run, so that eu entenda onde o tempo e os bytes foram gastos.

#### Acceptance Criteria
1. The Forge shall registrar em cada run que chegou à varredura do workspace: duração da varredura, do routing, da geração de contexto e da execução do provider; arquivos varridos e selecionados; arquivos hasheados e bytes hasheados; acertos e faltas do cache de fingerprints; bytes de contexto; número de providers executados e de fallbacks usados; e rodadas de negociação de contexto.
2. The Forge shall registrar cada métrica com o tipo `measured`, `estimated` ou `unknown`, e shall usar `unknown` para fases que o run não alcançou.
3. The Forge shall persistir a telemetria do run com redação de segredos aplicada e vinculá-la ao receipt do run por hash.
4. When um run termina em `refused`, `no_route`, `ambiguous` ou `provider_failure`, The Forge shall ainda assim persistir a telemetria das fases executadas.
5. The Forge shall manter legíveis os runs gravados antes desta spec, tratando a telemetria e os campos novos ausentes como não registrados.

### Requirement 11: Baseline de performance e budgets de regressão
**Objective:** As a mantenedor, I want medir performance antes de otimizar, so that budgets de regressão se baseiem em dados.

#### Acceptance Criteria
1. The Forge shall oferecer um procedimento de benchmark reprodutível, sem dependência de runtime adicional, que meça: startup da CLI, registry com e sem cache, varredura de workspaces sintéticos de 1.000 e 10.000 arquivos, routing, geração de ContextPack com cache de fingerprints frio e quente, e persistência de run.
2. The Forge shall registrar o baseline medido com a origem da medição (máquina, sistema operacional, versão do Python, data e versão de The Forge) antes de introduzir otimizações de contexto.
3. The Forge shall definir budgets de regressão somente a partir do baseline medido e documentar os valores e a origem de cada um.
4. When o procedimento de benchmark é executado com verificação de budgets, The Forge shall reportar cada medição acima do seu budget como regressão, sem bloquear a suíte offline padrão.

### Requirement 12: Compatibilidade de contratos e persistência segura
**Objective:** As a mantenedor e autor de provider, I want que a evolução do contexto não quebre providers nem runs existentes, so that a Wave C conviva com o Forge Protocol v1.

#### Acceptance Criteria
1. The Forge shall introduzir os novos campos de contrato como aditivos e opcionais dentro de `theforge/<Name>/v1`, mantendo válidos os providers que não os usam.
2. When um contrato muda, The Forge shall ter os JSON Schemas de `schemas/` regenerados e em paridade com os contratos.
3. The Forge shall passar por redação de segredos tudo o que persiste nesta spec, incluindo ContextPacks, telemetria e o cache de fingerprints.
4. If a redação alteraria uma entrada do cache de fingerprints, The Forge shall não gravar essa entrada.
5. The Forge shall manter as regras de integridade de ContextPack existentes (uso dentro do budget, uso igual à soma dos itens e caminhos válidos) para todos os tiers.
