# Implementation Plan — context-intelligence-v2 (Wave C)

- [x] 1. Fundação: perfis, contratos aditivos, integridade e infraestrutura de testes
- [x] 1.1 Criar a tabela única de perfis e derivar dela budgets e timeouts
  - Definir os parâmetros de `economy`, `balanced` e `max` (budget, limite de arquivos, tiers, rodadas de negociação, limite de providers, fallback, nível de verificação, timeout de execução) com os valores do design, e o teto fixo de 2 rodadas de negociação
  - Fazer os budgets do Context Broker e o timeout de execução do orquestrador serem lidos da tabela, mantendo o nome público de budgets usado pelos testes existentes
  - Registrar na tabela de categorias de teste todos os arquivos de teste novos previstos no design (perfis, relevância, git, fingerprints, verificação, fluxo de contexto, benchmark)
  - Concluído quando um teste provar que budget e limite de arquivos crescem de `economy` a `max`, que nenhum perfil passa de 2 rodadas, que só `max` tem limite de providers maior que 1, e a suíte existente continuar passando com os mesmos budgets
  - _Requirements: 8.3, 9.1, 9.2, 9.3, 9.6_

- [x] 1.2 Adicionar os campos de contrato de contexto e de manifest de forma aditiva
  - Introduzir os tipos de tier, nível de verificação, estratégia de revalidação e motivo de exclusão, mover a métrica com tipo de medição para os tipos compartilhados mantendo o import antigo, e declarar a lista genérica de arquivos de dependência usada também pelo routing
  - Acrescentar ao ContextPack o resumo de workspace (com resumo git), bytes por tier, tokens com tipo `unknown` por padrão e o número da rodada; aos itens o tier, o intervalo de linhas e os sinais; aos excluídos os sinais
  - Acrescentar à capability a declaração de suporte a excerpts e a pedido de contexto, e ao manifest a estratégia de revalidação de contexto
  - Validar no próprio contrato que `excerpt` exige intervalo, `reference` o proíbe e intervalos inválidos são rejeitados
  - Regenerar os schemas publicados
  - Concluído quando ContextPacks, manifests e runs gravados no formato anterior forem relidos sem erro (inclusive em modo estrito), o routing continuar produzindo as mesmas decisões, os testes de contrato cobrirem as invariantes de tier, a paridade de schemas e a suíte existente passarem, e um teste provar que uma entrada do cache do registry gravada com o hash de manifest antigo é descartada com aviso e regenerada
  - _Requirements: 1.1, 1.7, 2.5, 7.2, 12.1, 12.2_

- [x] 1.3 Adicionar pedido de contexto, campos de receipt, contrato de telemetria e novos artefatos de run
  - Acrescentar ao resultado o pedido de contexto opcional (itens por caminho e intervalo opcional), ao receipt o hash da telemetria e às entradas do receipt os hashes dos packs de cada rodada
  - Criar o contrato `RunTelemetry` v1 com o retrato do perfil efetivo, as métricas de fase e contadores com tipo, a estratégia de revalidação, o nível de verificação executado e os caminhos com divergência; exportá-lo com schema fechado
  - Dar a toda métrica de `RunTelemetry` o default `unknown` e não impor no contrato limite superior a providers executados, para que o mesmo contrato represente o run de plano gravado por `cross-forge-foundation` (varredura, routing, nós executados e retrato do perfil, demais campos no default)
  - Declarar os três códigos `FORGE-CONTEXT-REQUEST-*` na fonte única de códigos
  - Registrar no run store os artefatos das rodadas de negociação e da telemetria, com o mesmo tratamento de redação e hash em disco
  - Regenerar os schemas publicados
  - Concluído quando a paridade de schemas passar com `RunTelemetry` fechado, um run sem os artefatos novos continuar legível pelo `explain`, a telemetria gravada for redigida e relida em modo estrito, e uma telemetria com a forma de run de plano (só varredura, routing, arquivos varridos, mais de um provider executado e perfil) for válida e relida em modo estrito
  - _Requirements: 8.1, 8.5, 10.3, 10.5, 12.1, 12.2, 12.3_

- [x] 1.4 Estender as invariantes de integridade para tiers, pedido de contexto e receipt
  - Validar no ContextPack que a soma dos bytes por tier é igual aos bytes usados (com `metadata` em zero) além das regras existentes de budget, soma e caminho
  - Validar o pedido de contexto (entre 1 e 64 itens) com o código específico de pedido inválido, deixando a validação de caminho por item para o broker
  - Validar o formato do hash de telemetria e dos hashes de rodada no receipt
  - Concluído quando cada nova invariante tiver um caso válido e um inválido testados com o código esperado e os casos existentes de integridade continuarem passando
  - _Requirements: 8.4, 12.5_

- [x] 2. Baseline de performance antes de qualquer otimização
- [x] 2.1 Construir o procedimento de benchmark e o gerador de workspaces sintéticos
  - Gerar workspaces sintéticos determinísticos de 1.000 e 10.000 arquivos a partir de uma semente fixa, em diretório temporário
  - Medir startup da CLI, registry com cache frio e quente, varredura de 1k e 10k, routing sobre 10k arquivos, geração de ContextPack em 1k e 10k e persistência de um run, com mediana e p90 de várias repetições, usando só a stdlib
  - Emitir o resultado em JSON com a origem da medição (máquina, sistema operacional, Python, data, versão de The Forge, HEAD) e oferecer comparação com um arquivo de budgets que reporta regressões e sai com código diferente de zero, sem entrar na suíte offline padrão
  - Concluído quando testes rápidos (sem medir tempo) provarem o determinismo do gerador com poucos arquivos, o formato da saída e a detecção de regressão pela comparação com budgets
  - _Requirements: 11.1, 11.4_

- [x] 2.2 Medir e registrar o baseline atual
  - Executar o benchmark sobre o código ainda sem cache de fingerprints e sem a nova seleção de contexto, e versionar o resultado com sua origem
  - Concluído quando o arquivo de baseline existir no repositório com todas as medições do procedimento e a origem preenchida, antes de qualquer tarefa do grupo 3 alterar a geração de contexto
  - _Depends: 2.1_
  - _Requirements: 11.2_

- [x] 3. Núcleo: componentes independentes de contexto
- [x] 3.1 (P) Implementar os sinais de relevância e a prioridade determinística
  - Atribuir a cada arquivo varrido os sinais de caminho citado na intenção, intervalo citado, alvo explícito (nunca para o alvo padrão `.`), glob da capability, alteração no git e arquivo de dependência
  - Reconhecer citações de caminho na intenção, inclusive com sufixos de intervalo de linhas, e rejeitar com motivo citações absolutas, com `..`, de segredo ou inexistentes
  - Ordenar pela prioridade fixa do design com desempate por caminho e contar os arquivos sem nenhum sinal como agregado
  - Concluído quando testes cobrirem cada sinal, a ordem de prioridade com um arquivo por classe, cada rejeição de citação e, por propriedade, a mesma saída para qualquer permutação da varredura e dos globs
  - _Boundary: Relevance_
  - _Requirements: 1.5, 1.8, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 4.2, 4.3_

- [x] 3.2 (P) Implementar a consulta git somente leitura e endurecida
  - Obter toplevel, diretório git, branch (ou HEAD destacado) e commit, e os arquivos alterados e não rastreados convertidos para caminhos relativos à raiz do workspace, ignorando submódulos
  - Executar o git com o ambiente mínimo sem credenciais, sem travas opcionais, com o fsmonitor desligado, encerramento da árvore no tempo limite total e sem alterar a confiança de diretório do git
  - Pular a consulta de status, registrando a limitação, quando a configuração local ou de worktree definir fsmonitor ou filtros, ou quando a versão do git não permitir essa inspeção
  - Converter git ausente, não repositório, repositório recusado pelo git, falha e tempo esgotado em limitações, e reportar estados sem commits, merge, rebase, cherry-pick e bisect sem falhar
  - Concluído quando, em repositório real temporário, o conteúdo e a data de todo o diretório git forem idênticos antes e depois da consulta, nenhum `index.lock` existir, um fsmonitor local que criaria um marcador nunca o criar, e os cenários de ausência e falha retornarem limitação sem exceção (testes pulam com motivo se não houver git)
  - _Boundary: GitReader_
  - _Requirements: 2.6, 3.1, 3.2, 3.3, 3.4, 3.5_

- [x] 3.3 (P) Implementar o cache conservador de fingerprints fora do workspace
  - Guardar fingerprints por raiz de workspace no diretório de cache do usuário, relidos em modo estrito e descartados se ausentes, malformados, de outra raiz ou de versão desconhecida
  - Reutilizar um hash somente com tamanho, datas, identidade do arquivo e caminho resolvido iguais e data de modificação fora da janela de 2 s; caso contrário ler e hashear, registrando só quando o estado do arquivo não mudou durante a leitura
  - Gravar uma vez por run de forma atômica após redação, recusando a gravação (e removendo a cópia anterior) se a redação alterar o documento, e convertendo falha de escrita em aviso
  - Contabilizar arquivos e bytes hasheados, acertos e faltas
  - Ser o dono único do hash de intervalo de linhas e do maior prefixo de linhas completas, com regra única de quebra de linha, para uso do broker e da reverificação
  - Concluído quando testes provarem acerto sem leitura de conteúdo, falta para cada evidência de mudança e para a janela racy, descarte de cache inválido, cache fora do workspace, aviso em falha de escrita e, por propriedade, hashes idênticos com cache ligado ou desligado, e o hash de intervalo for testado para última linha sem quebra final e intervalo além do fim
  - _Boundary: FingerprintStore_
  - _Depends: 2.2_
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 12.3, 12.4_

- [x] 3.4 Implementar a detecção de divergência de contexto e o rebaixamento de evidências
  - Detectar divergência reportada pelo provider somente sob a semântica definida para `Evidence.hash`: evidência com localização e hash não nulo que difere do hash de todos os itens do mesmo caminho, comparando com o hash do intervalo quando o item tem intervalo (excerpt ou requested com linhas) e nunca com o hash do arquivo inteiro nesse caso; hash nulo ou evidência sem localização não gera divergência reportada
  - Selecionar os itens a reverificar conforme o nível (nenhum em mínimo, os citados por evidências confirmadas ou observadas em condicional, todos em forte) e recalcular hashes de arquivo inteiro ou intervalo sem cache (reutilizando o hash de intervalo da tarefa 3.3), tratando ausência como divergência
  - Rebaixar para `unresolved` as evidências confirmadas ou observadas sobre itens divergentes, com limitação do status original, registrar os caminhos divergentes no resultado e marcá-lo como parcial
  - Concluído quando testes cobrirem cada nível, a divergência reportada contra item inteiro e contra excerpt (hash do arquivo inteiro informado para um excerpt conta como divergência, hash do intervalo não), o mesmo caminho em dois itens, hash nulo sem divergência, a reverificada e a ausência de arquivo, e provarem que sem divergência o resultado não muda
  - _Boundary: ContextVerify_
  - _Depends: 3.3_
  - _Requirements: 6.1, 6.2, 6.3, 6.7_

- [x] 3.5 Implementar o registrador de telemetria do run
  - Medir as fases de varredura, routing, contexto e provider (somando todas as rodadas de execução) e acumular os contadores de arquivos, bytes, cache, providers, fallbacks e rodadas
  - Marcar como `unknown` toda fase ou contador não alcançado e como `measured` os medidos
  - Registrar o retrato do perfil e dos tiers efetivos, a estratégia de revalidação declarada (ou `undeclared` com limitação), o nível de verificação executado e os caminhos divergentes
  - Manter o registrador utilizável quando só varredura, routing e o número de providers executados são registrados (uso previsto pelo run de plano de `cross-forge-foundation`)
  - Concluído quando testes provarem que um run interrompido antes do contexto produz telemetria válida com as fases seguintes `unknown`, um run completo produz todas as métricas medidas, e um registro só de varredura, routing e vários providers executados produz telemetria válida
  - _Boundary: TelemetryRecorder_
  - _Depends: 3.4_
  - _Requirements: 6.5, 6.6, 9.4, 10.1, 10.2_

- [x] 3.6 Montar o ContextPack por tiers dentro do budget e do limite de arquivos
  - Calcular os tiers efetivos como a interseção do perfil com o que a capability declara e incluir sempre o resumo de workspace sem bytes
  - Selecionar na ordem de relevância: arquivo inteiro quando cabe, intervalo citado quando excerpt é efetivo, maior prefixo de linhas completas quando não cabe e excerpt é efetivo, exclusão por budget ou por limite de arquivos caso contrário
  - Registrar tier e sinais por item, motivo e sinais por excluído, bytes por tier, tokens `unknown` e o estado truncado
  - Usar o cache de fingerprints para arquivos inteiros e o hash de intervalo da tarefa 3.3 para excerpts (sem implementação própria)
  - Concluído quando testes provarem: resumo de workspace sempre presente com zero bytes; capability sem declaração nunca recebe excerpt mesmo em `max`; prefixo e intervalo com hash do trecho; limite de arquivos aplicado; nenhum campo com conteúdo de arquivo; todo pack gerado passando na integridade; mesma seleção em duas execuções; e o hash de um excerpt gerado pelo broker igual ao recalculado pela reverificação para o mesmo intervalo
  - _Depends: 2.2, 3.1, 3.2, 3.3, 3.4_
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 4.1, 4.2, 7.1, 12.5_

- [x] 3.7 Estender o ContextPack a partir de um pedido de contexto do provider
  - Validar cada item pedido com as mesmas regras de caminho, segredo, presença na varredura, budget restante e limite de arquivos, incluindo os aprovados como `requested` e registrando os recusados com motivo
  - Preservar os itens anteriores e incrementar a rodada
  - Concluído quando testes provarem que itens fora da raiz, de segredo, inexistentes ou sem budget são recusados com motivo, os aprovados entram como `requested` e o pack estendido passa na integridade
  - _Requirements: 8.2_

- [x] 4. Integração no fluxo `ask`
- [x] 4.1 Ligar perfis, git e cache à fase de contexto do orquestrador
  - Usar o perfil da tarefa para o timeout de execução e para desligar o fallback de health em `economy`, registrando a limitação quando o primário falha
  - Na fase de contexto (depois da policy), consultar o git, abrir o cache de fingerprints, montar e validar o ContextPack e gravar o cache, levando avisos de git e cache às limitações do run
  - Manter um único provider executado por run em qualquer perfil
  - Ajustar o substituto de montagem de contexto usado pelos testes adversariais para aceitar os novos parâmetros nomeados
  - Adicionar ao provider adversarial um modo cuja capability declara suporte a excerpts
  - Concluído quando testes de orquestrador provarem que `economy` não tenta o fallback e `balanced` tenta, que runs `no_route` e `refused` não executam git, que o ContextPack gravado contém resumo de workspace, sinais e tiers, e que, pelo fluxo completo, a capability que declara excerpts recebe itens `excerpt` em `balanced` e `max` e nenhum em `economy`
  - _Depends: 3.2, 3.6_
  - _Requirements: 1.4, 1.6, 3.1, 3.4, 5.5, 9.1, 9.2, 9.3, 9.6_

- [x] 4.2 Implementar a negociação de contexto adicional no orquestrador
  - Tratar um resultado com pedido de contexto como rodada de negociação: recusar com o código específico quando a capability não declara suporte, quando as rodadas do perfil se esgotaram ou quando o pedido é inválido
  - Estender, validar e gravar o pack de cada rodada, levar seu hash ao receipt e reexecutar o provider, sem nunca gravar como resultado uma resposta que contém pedido
  - Adicionar ao provider adversarial de testes os modos de pedido válido, pedido em laço, pedido não declarado e pedido inválido
  - Concluído quando testes provarem: pedido válido em `balanced` gera o pack da rodada 1 e resultado final `ok`; o mesmo pedido em `economy` falha por limite; laço em `max` falha após 2 rodadas; pedido não declarado e inválido falham com seus códigos; nenhuma falha grava resultado
  - _Depends: 3.7_
  - _Requirements: 8.1, 8.3, 8.4, 8.5, 8.6_

- [x] 4.3 Aplicar reverificação pós-execução, divergência e tokens honestos
  - Após o resultado final, detectar divergência reportada e reverificar conforme o nível do perfil, aplicar o rebaixamento e terminar o run como `partial` quando houver divergência, registrando os caminhos no resultado e no receipt
  - Preservar valor e tipo de tokens informados pelo provider como medidos ou estimados e usar `unknown` caso contrário, sem derivar tokens de bytes
  - Fazer o provider de referência declarar revalidação por hash (o registro da estratégia no run fica com a tarefa 4.4)
  - Adicionar ao provider adversarial os modos de divergência reportada, alteração do arquivo durante a execução e tokens medidos
  - Concluído quando testes provarem que divergência reportada resulta em `partial` com evidência rebaixada, que a alteração durante a execução é detectada em `max` e `balanced` e não em `economy` (com limitação de não reverificação), e que tokens medidos pelo provider aparecem inalterados no resultado gravado
  - _Depends: 3.4_
  - _Requirements: 6.1, 6.2, 6.3, 6.7, 7.2, 7.3, 7.4, 9.1, 9.2, 9.3_

- [x] 4.4 Gravar a telemetria em todo desfecho e vinculá-la ao receipt
  - Instrumentar as fases do run com o registrador e gravar a telemetria antes do receipt em todos os caminhos de término, inclusive erro de uso e erro interno, levando seu hash ao receipt
  - Registrar a estratégia de revalidação declarada pelo provider, ou `undeclared` com limitação no receipt quando ausente
  - Concluído quando testes provarem telemetria presente, redigida e com hash igual ao do receipt em runs `ok`, `partial`, `refused`, `no_route`, `ambiguous` e `provider_failure`, no máximo um provider executado registrado em todo run de `ask` em qualquer perfil, um run antigo sem telemetria continuar legível, e um provider sem estratégia declarada gerar `undeclared` com limitação enquanto o echo gera `hash`
  - _Depends: 3.5, 4.3_
  - _Requirements: 6.5, 6.6, 9.4, 10.1, 10.2, 10.3, 10.4, 10.5_

- [x] 4.5 Exibir contexto e telemetria no `explain`
  - Mostrar tiers efetivos e bytes por tier, cada item com tier, intervalo e sinais, excluídos com motivo, o agregado sem sinal, o resumo git ou sua limitação, as rodadas de negociação, as divergências e uma linha de telemetria
  - Manter essas seções e seus testes identificáveis como contrato de saída de texto, pois `cross-forge-foundation` reescreve o `explain` sobre `ExplainReport` e deve preservá-los lendo os artefatos de contexto, das rodadas e de telemetria
  - Concluído quando um teste de CLI executar `ask` seguido de `explain` e encontrar essas seções no texto, e `explain --json` contiver a telemetria
  - _Depends: 4.4_
  - _Requirements: 4.4_

- [x] 5. Validação, medição final e documentação exigida
- [x] 5.1 Provar a diferença observável entre perfis e a integridade do repositório de ponta a ponta
  - Executar a mesma tarefa no mesmo workspace em `economy`, `balanced` e `max` e comparar, pela telemetria e pelo ContextPack, budget de contexto, limite de providers e nível de verificação executado
  - Executar `ask` pela CLI em um workspace git real e comparar o diretório git antes e depois
  - Concluído quando o teste de perfis exigir budgets e níveis de verificação distintos dois a dois e limite de providers de `max` maior que o de `economy` e `balanced`, e o teste de ponta a ponta confirmar o diretório git intacto
  - _Requirements: 3.2, 9.5_

- [x] 5.2 Remedir o benchmark e definir os budgets de regressão a partir do baseline
  - Atualizar o benchmark para medir contexto frio (cache de fingerprints desabilitado) e quente (cache populado) e incluir na saída arquivos hasheados e acertos de cache
  - Executar o benchmark com o cache de fingerprints e a nova seleção, confirmando que o ContextPack com cache quente não relê arquivos inteiros inalterados
  - Derivar os budgets iniciais (1,5× a mediana do baseline de cada medição) com a origem registrada e conferir a comparação contra as medições novas
  - Concluído quando o arquivo de budgets existir com valor, baseline de origem e fator para cada medição, e a comparação contra a medição final rodar e listar as regressões, se houver
  - _Depends: 2.2, 3.3, 3.6, 4.4_
  - _Requirements: 5.1, 11.3, 11.4_

- [x] 5.3 Documentar protocolo, autoria, arquitetura, segurança, ADRs e performance
  - Documentar no protocolo os tiers, intervalos, sinais, resumo de workspace, pedido de contexto e seus códigos, e a obrigação de revalidar o hash do conteúdo lido ou declarar a estratégia alternativa; repetir a obrigação e as declarações no guia de autoria de providers
  - Documentar no protocolo e no guia de autoria a semântica de `Evidence.hash` do design: sha256 de exatamente o conteúdo entregue no caminho da localização (arquivo inteiro, ou o intervalo do item quando ele tem linhas), nulo em qualquer outro caso, e a regra de divergência derivada dela
  - Na tabela de códigos do protocolo, incluir os novos códigos com link para `docs/errors.md`, a lista canônica testada de `cross-forge-foundation`
  - Atualizar a arquitetura (fluxo, perfis, estado com o cache de contexto do usuário, `economy` sem fallback) e a segurança (consulta git endurecida e suas limitações, cache fora do projeto)
  - Criar os ADRs 0015 (inteligência de contexto) e 0016 (sinais git somente leitura), números congelados entre as waves, e o documento de performance com procedimento, baseline, budgets e origem
  - Se esta wave alterar a versão do pacote, acrescentar na mesma mudança a linha correspondente da matriz de compatibilidade em `docs/versioning.md` exigida pelo teste de matriz de `real-provider-integration`
  - Concluído quando cada código `FORGE-CONTEXT-REQUEST-*` aparecer na tabela de códigos do protocolo com o link para `docs/errors.md`, a semântica de `Evidence.hash` estiver no protocolo e no guia de autoria, os ADRs 0015 e 0016 existirem com status aceito, o documento de performance apresentar os valores medidos com origem e, se a versão do pacote mudou, a matriz de compatibilidade tiver a linha nova
  - _Requirements: 6.4, 11.2, 11.3_

- [x] 5.4 Executar os gates finais
  - Rodar lint, checagem de tipos estrita, paridade de schemas e a suíte offline completa uma sessão por vez (com diretório temporário próprio se houver outra sessão), mais os testes de git e de segurança
  - Concluído quando lint, tipos, paridade de schemas e a suíte offline passarem sem falhas e sem testes novos fora da tabela de categorias
  - _Requirements: 12.1, 12.2_

## Implementation Notes
- Cross-spec review (minor, open): link protocol.md -> docs/errors.md only when errors.md exists (created by cross-forge-foundation after its gate 5.3).
- 1.3 (2026-10-04): `tests/test_forger.py` case_a artifact check skips `context-r*` (optional, permanent) and `telemetry` (TEMPORARY) — the task that makes the Forger write telemetry on every outcome (4.4) MUST restore the telemetry assertion. `explain --json` now always emits `context-r1`, `context-r2`, `telemetry` keys (null for old runs). `MAX_CONTEXT_REQUEST_ITEMS` still to add in 1.4 (validate_context_request); receipt hash-format checks for telemetry_sha256/context_round_sha256 in 1.4.
- 1.4 (2026-10-04): negative ContextPack.round → Codes.PROTO_SCHEMA (design lists only CONTEXT_BYTES/CONTEXT_PATH; neither fits). tier_bytes checks skipped when empty (old packs); broker task must fill tier_bytes with metadata 0 for v2 packs and test it passes validate_context_pack.
- 3.2 (2026-10-04): DESIGN ERRATA — step 1 is 5 git calls (rev-parse toplevel/git-dir, `symbolic-ref -q --short HEAD`, `rev-parse --verify -q HEAD`, `config --list --show-scope --includes -z`, status) under one 5 s budget; `--abbrev-ref HEAD` exits 128 with no commits. design.md "up to 4 git processes" is stale. SECURITY: design claim "fsmonitor/filters are the only keys that make status run a program" is WRONG — partial-clone lazy fetch runs the repo's transport (`ext::`, core.sshCommand); `git_env()` adds `GIT_NO_LAZY_FETCH=1` + `GIT_ALLOW_PROTOCOL=none` (regression test). Task 5.3 must record this in docs/security.md and ADR 0016. Semantics: `available` = repo located; `dirty` = any status entry in whole repo; `changed_files` = count inside workspace root (dirty=True with 0 possible). Any local `core.fsmonitor` value (even false) skips status. Follow-up: pipe-pump helpers duplicated from protocol/transport.py (share via protocol module later). Residual: global/system filters (git-lfs) not detected.
- 3.3 (2026-10-04): cache file `<cache_dir>/context/<sha256(root)[:12]>.json`; per-entry redaction filter (secret-shaped rel/resolved paths dropped with warning) before whole-doc check; cache_dir inside workspace → cache disabled with warning; `store.lines()/prefix()` count range bytes; every whole-file computation counts as a miss. Forger must call `store.save()` once per run and carry `store.warnings` into limitations. Windows ctime = creation time (weaker evidence). 5.3 docs: mention per-entry filter and in-workspace refusal.
- 3.4 (2026-10-04): context/verify.py API: DriftReport(drifted, checked, level, limitations), provider_reported_drift, items_to_verify, reverify, check_drift, apply_drift; DRIFT_LIMITATION_PREFIX='context-drift:', NOT_REVERIFIED_LIMITATION='context-not-reverified'. apply_drift returns same object with no drift and does NOT copy report.limitations — 3.5/4.3 must forward DriftReport.limitations to telemetry/receipt. Subject matching also used for demotion (safer). Follow-up: public hash_file in fingerprints to own whole-file hashing (verify has a local chunked copy).
- 3.1 (2026-10-04): context/relevance.py — parse_intent_refs(intent, scan), rank_candidates(task, globs, scan, changed, refs) -> (ranked, unmatched_files). Targets normalized against scan.root (absolute/`..` targets keep the `target:` signal; root/outside → none). SECURITY for 3.6: `IntentRefs.rejected` keys are raw intent tokens (may be secret-shaped) — the broker/RunStore must persist them only through redact; 3.6 test must cover a secret-shaped citation. Open (design-level, non-blocking): path-like words (`and/or`, `e.g.`, `Node.js`) yield `missing` rejections per design token rule; `#L2` single-line GitHub form unsupported.
- 3.5 (2026-10-04): forger/telemetry.py — TelemetryRecorder(run_id, profile, *, clock, now); `with rec.phase("scan"|"routing"|"context"|"provider")` (provider sums rounds); rec.count(<RunTelemetry counter field>, n) — record explicit zeros for "all measured"; set_effective_tiers, set_revalidation (None → "undeclared" + limitation "provider-revalidation-undeclared"), set_drift(report) copies DriftReport.limitations; build(). 4.4 must copy telemetry.limitations into the receipt, write via RunStore.write, set telemetry_sha256, restore the test_forger case_a telemetry assertion.
- 3.6/3.7 (2026-10-04): broker API — build_context_pack(task, provider_id, globs, scan, *, profile=None, capability_context=None, git=None, fingerprints=None); effective_tiers(profile, capability_context); extend_context_pack(pack, request, scan, *, profile, fingerprints). Broker copies git.limitations into pack; does NOT touch store.warnings/save (forger, 4.1). extend does NOT check capability request support / round limit / item count — 4.2 must raise CONTEXT_REQUEST_UNSUPPORTED/LIMIT and call validate_context_request first. Choices: cited range past EOF → whole file in build, `missing` in extend; non-fitting cited range → `budget` (no prefix fallback); duplicate request skipped silently; provider request reason not persisted; backslash/NUL paths → outside_root. Forger default pack now includes root dependency manifests and intent-cited files (Migration Strategy).
- 4.1 (2026-10-04): orchestrator `_build_context(trace, task, record, capability, scan, profile)` runs after policy (git → FingerprintStore(root) → build → finally save + warnings). For 4.2: move store creation to `_run` so negotiation can extend, save once after last extension, add warnings before `_finish`. Perf (for 5.2/5.3): each routed run spends ~0.7–1.3 s in 5 git processes when the workspace is inside a repo (tests' basetemp is inside the repo) — consider an autouse conftest fixture stubbing `orchestrator.read_git_state` unless opted in, and document cost.
- 4.2 (2026-10-04): `_execute_negotiated` returns `_Executed(status, result, pack, error, duration_ms)` (duration sums rounds). Structurally broken context_request → FORGE-PROTO-SCHEMA (design error table); only item count → INVALID. Each round gets full profile execute timeout (worst case max: 3 × 600 s ≈ 30 min) — 5.3 must document. For 4.3: drift/tokens on executed.result + executed.pack (last round pack) before result write; tokens currently hard-set unknown. For 4.4: provider phase = sum over rounds, negotiation_rounds = len(trace.context_round_shas), providers_executed = 1; write telemetry in `_finish`. Full suite NOT run (memory pressure, machine <1 GB free) — run in 5.4 gates.
- 4.3 (2026-10-04): `honest_tokens(Metric)` (measured/estimated with value ≥ 0 kept; else unknown). `_verify_context` writes DriftReport.limitations (e.g. context-not-reverified) and `context-drift: <path>` to receipt limitations already — 4.4 must DEDUPE when copying telemetry.limitations to the receipt. `_Trace.drift` holds the report for 4.4 set_drift. Echo hashes whole file; if echo ever declares excerpts it must hash the range or null.
- 4.4 (2026-10-04): health checks timed inside `routing`; `fallbacks_used` = len(RoutingDecision.fallbacks_used) (unhealthy providers tried, incl. primary → economy may record 1) — 5.3 must document this meaning. Telemetry build failure → limitation `telemetry-unavailable: <Type>: <msg>`, receipt still written, telemetry_sha256 None. For 4.5: explain --json already returns telemetry (null for old runs); unknown metrics listed in `unknowns`.
- 5.4 (2026-10-04): gates green on f637e2a+28b5ea6 — ruff, mypy (81 files), schema parity, full offline suite run in 3 file chunks sequentially (memory pressure: full single run got reaped), all exit 0.
