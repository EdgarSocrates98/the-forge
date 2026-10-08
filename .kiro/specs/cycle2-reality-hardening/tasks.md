# Implementation Plan — cycle2-reality-hardening (Wave A)

- [x] 1. Fundação: códigos de erro, infraestrutura de testes e contratos
- [x] 1.1 Centralizar os códigos de erro `FORGE-*` em uma fonte única
  - Criar a fonte única de constantes de erro na posição mais à esquerda da cadeia de dependências e reexportá-la pelo módulo de erros, sem importar o validador de integridade
  - Migrar todos os literais `FORGE-*` existentes (transporte, health, orquestrador) para as constantes, preservando exatamente os valores atuais
  - Declarar os códigos novos previstos no design (resultado, contexto, receipt, registry, manifest, policy, op)
  - Concluído quando nenhum literal `FORGE-` restar em `src/theforge` fora da fonte única (verificado por teste; testes, docs e fixtures fora do escopo) e a suíte existente continuar passando
  - _Requirements: 2.6_

- [x] 1.2 Reorganizar a infraestrutura de testes: categorias, bloqueio de rede e cache isolado
  - Registrar os markers `unit`, `contract`, `integration`, `e2e`, `slow`, `security`, `real_provider` e manter como seleção padrão tudo exceto `slow` e `real_provider`
  - Classificar cada arquivo de teste existente por uma tabela de categorias, pré-registrando também todos os arquivos de teste novos previstos no design; um arquivo sem categoria faz a coleta falhar (toda tarefa que criar arquivo de teste não previsto deve registrá-lo)
  - Mover o bloqueio de rede para o nível da sessão, cobrindo conexão, criação de conexão e resolução de nomes, permitindo loopback e soquetes locais, com marker de liberação explícita
  - Isolar o diretório de cache do usuário por teste, ao lado do isolamento de configuração já existente
  - Adicionar a ferramenta de build de pacote às dependências de desenvolvimento
  - Concluído quando `pytest -m unit` e `pytest -m security` selecionarem subconjuntos não vazios, um teste que tenta resolver um host externo falhar, e nenhum teste escrever fora de diretórios temporários
  - _Requirements: 7.5, 7.6_

- [x] 1.3 Endurecer o formato dos contratos e a leitura estrita
  - Validar o formato SHA-256 (64 hex minúsculos) em todos os campos de hash de artifact, arquivo de contexto e evidence
  - Adicionar o modo de desserialização estrita que rejeita campos desconhecidos em qualquer nível, mantendo o modo tolerante como padrão para dados de providers
  - Fechar os schemas publicados apenas dos artefatos que nunca cruzam o protocolo (routing, receipt, risk)
  - Concluído quando hash inválido gerar erro de contrato, o modo estrito rejeitar chave desconhecida aninhada enquanto o tolerante a aceita, e os testes de paridade de schema passarem
  - _Requirements: 1.5, 1.10_

- [x] 1.4 Adicionar os campos e contratos novos de forma aditiva
  - Incluir o `op` opcional na resposta do protocolo, o estado da capability no candidato de routing, a identidade observada do provider e o hash do artefato de risco no receipt, todos com default compatível
  - Criar o contrato `RiskAssessment` v1 com dimensões de risco, decisão de policy, origem declarativa e a limitação fixa sobre `operation_class`
  - Exportar o novo contrato e regenerar os schemas publicados
  - Concluído quando runs e respostas do Cycle 1 continuarem sendo lidos sem erro, `RiskAssessment` validar instâncias reais pelo schema publicado e a paridade de schemas passar
  - _Requirements: 3.8, 4.6, 6.5, 6.6_

- [x] 2. Núcleo: componentes independentes de validação, processo, ambiente, identidade, policy e routing
- [x] 2.1 (P) Implementar as invariantes relacionais de resultado, contexto e receipt
  - Validar unicidade de IDs de evidence e de findings, resolução de referências, contenção léxica de caminhos de artifact (sem abrir o caminho), producer (id e versão) e timestamps
  - Validar `ContextPack` (bytes usados versus budget e versus soma dos arquivos, caminhos contidos) e consistência de receipt de sucesso com o hash do resultado
  - Coletar todas as violações em ordem determinística e expor o código da primeira
  - Concluído quando cada invariante tiver ao menos um caso válido e um inválido testados, retornando o código específico esperado
  - _Boundary: Integrity_
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.6, 1.7, 1.8, 1.11, 2.6_

- [x] 2.2 Implementar os limites de manifest e a rejeição de globs catch-all
  - Definir os limites e o padrão de globs catch-all junto aos tipos de contrato, de onde validador e router os importam
  - Aplicar limites de quantidade de capabilities, keywords, globs, dependências e ações por manifest
  - Rejeitar globs catch-all e capabilities sem ações, reportando violações por capability
  - Não paralelo a 2.1: mesmo módulo de integridade
  - Concluído quando um manifest com 300 capabilities, uma capability com glob `*` e uma com 100 keywords produzirem as violações esperadas, e os manifests de referência não produzirem nenhuma
  - _Depends: 2.1_
  - _Requirements: 1.9, 3.2_

- [x] 2.3 (P) Implementar o início isolado e o encerramento da árvore de processos
  - POSIX: iniciar o provider em sessão própria e encerrar o grupo com término gracioso seguido de término forçado
  - Windows: iniciar suspenso, associar a um job com encerramento ao fechar, retomar, e usar encerramento recursivo como fallback registrando a limitação
  - Incluir no teste um provider auxiliar próprio que cria um processo neto
  - Concluído quando um provider de teste que cria um processo neto e é encerrado deixar o neto inexistente em Linux e Windows
  - _Boundary: ProcTree_
  - _Requirements: 2.5_

- [x] 2.4 (P) Tornar a negociação de protocolo robusta a entradas malformadas
  - Aceitar apenas versões no formato do protocolo, deduplicar, ignorar entradas malformadas e tornar a escolha independente da ordem
  - Concluído quando os casos `[v1]`, `[v1,v2]`, `[v2]`, malformado, duplicado e formato desconhecido produzirem resultado determinístico sem erro interno
  - _Boundary: Negotiate_
  - _Requirements: 2.7_

- [x] 2.5 (P) Endurecer o ambiente entregue a providers
  - Associar cada variável permitida a uma justificativa explícita
  - Aplicar uma segunda passada que remove variáveis com padrões de credencial (nuvem, tokens, SSH agent, proxies com credenciais, registries)
  - Concluído quando um ambiente de origem contendo uma variável de cada categoria de credencial resultar em ambiente de provider sem nenhuma delas, mantendo as variáveis obrigatórias do sistema
  - _Boundary: SafeEnv_
  - _Requirements: 5.1, 5.2, 5.3_

- [x] 2.6 (P) Implementar fingerprint de provider, diretório de cache do usuário e resolução de argv relativo
  - Calcular a identidade observada do provider (executável resolvido, tamanho e data dos arquivos do argv, digest canônico)
  - Determinar o diretório de cache do usuário por plataforma com override por variável de ambiente
  - Resolver entradas relativas do argv relativas ao arquivo de configuração, com erro de uso claro para caminhos inexistentes
  - Concluído quando alterar a data de modificação do script do provider mudar o digest, o diretório de cache respeitar o override, e uma configuração com argv relativo funcionar a partir de outro diretório de trabalho
  - _Boundary: Identity, Registry config_
  - _Requirements: 4.5, 5.4_

- [x] 2.7 (P) Implementar o policy engine e a avaliação de risco
  - Derivar as dimensões de risco de `operation_class` e da necessidade de rede declarada, deixando credenciais e cross-account como desconhecidas
  - Avaliar a decisão pela regra mais severa entre dimensões ativas, com tabela padrão por trust para mutação local
  - Carregar policy do usuário (pode afrouxar ou endurecer) e do projeto (só endurece, tentativa de afrouxar gera aviso)
  - Concluído quando a tabela padrão produzir `allow/ask/deny` esperados para cada classe de operação e trust, `read_only` com rede produzir `ask`, `deny` resistir a aprovação e a avaliação registrar origem declarativa
  - _Boundary: Policy_
  - _Depends: 1.4_
  - _Requirements: 4.2, 5.6, 6.2, 6.5, 6.6_

- [x] 2.8 (P) Reescrever a pontuação de routing por presença de tipos de sinal
  - Decidir apenas pela presença de cada tipo de sinal, mantendo contagens só para explicação
  - Tratar como não discriminante o sinal comum a todos os candidatos que pontuaram, registrando a limitação
  - Excluir do routing capabilities de providers sem a operação de execução
  - Propagar o estado da capability ao candidato e rebaixar a confiança quando o selecionado for heurístico ou não resolvido
  - Ordenar entradas antes de processar para independência de ordem
  - Atualizar intencionalmente as asserções de `rank_key` dos testes de routing existentes para o novo formato
  - Concluído quando as decisões de referência (caso de dados, caso de API, Glue, OpenAPI) permanecerem iguais com os testes atualizados, um provider de spam nunca vencer o provider de dados no caso de referência, e permutações de ordem de providers e arquivos produzirem a mesma decisão
  - _Boundary: Router_
  - _Depends: 1.4_
  - _Requirements: 2.1, 3.1, 3.2, 3.3, 3.7, 3.8, 3.11_

- [x] 3. Integração: transporte, registry, persistência, orquestração e CLI
- [x] 3.1 Atualizar os providers de referência para as regras novas
  - Fazer o provider builtin e o provider de fixtures emitirem `op` na resposta, versão de producer igual à do manifest, hashes e timestamps válidos
  - Fazer os transportes falsos dos testes existentes retornarem producer consistente com o manifest
  - Concluído quando echo, fixtures e fakes passarem por todas as validações de integridade e a suíte existente continuar verde
  - _Depends: 2.1_
  - _Requirements: 1.6, 2.2_

- [x] 3.2 Integrar o transporte com o encerramento de árvore e a validação de envelope
  - Usar o início isolado e encerrar a árvore em timeout, excesso de saída e em qualquer saída anormal do chamador
  - Validar `op` quando presente, mantendo a ordem JSON, schema, request_id, op e protocolo
  - Manter stderr truncado e redigido, nunca persistido bruto
  - Adicionar ao provider adversarial os modos usados aqui (inundação de stderr, op divergente)
  - Concluído quando os modos de timeout, excesso de stdout, excesso de stderr e op divergente produzirem os códigos esperados sem processos remanescentes
  - _Depends: 2.3_
  - _Requirements: 2.2, 2.3, 2.4, 2.5_

- [x] 3.3 Mover o cache do registry para o diretório do usuário com formato novo
  - Persistir entradas de cache v2 com fingerprint no diretório de cache do usuário, com escrita atômica de nome único e falhas de escrita como aviso
  - Ler o cache em modo estrito e invalidar entradas cujo fingerprint ou entrada mudou
  - Remover o diretório de cache legado do workspace na inicialização e no refresh, com aviso, e deixar de criá-lo na inicialização do workspace
  - Migrar as asserções dos testes de registry e doctor que dependiam de `.forge/registry` para o cache isolado
  - Concluído quando nenhum arquivo de cache existir sob `.forge`, alterar o script do provider forçar novo describe, e dois registries gravando o mesmo cache não falharem
  - _Depends: 2.6_
  - _Requirements: 4.4, 4.5_

- [x] 3.4 Endurecer describe, health e a revalidação no registry
  - Executar describe e health em diretório temporário controlado
  - Verificar producer (id e versão) em describe e health e aplicar os limites de manifest, excluindo capabilities violadoras com aviso
  - Oferecer revalidação de uma lista de providers retornando situação atual, alterada ou inacessível
  - Adicionar ao provider adversarial os modos de producer divergente em describe e health e um probe de diretório de trabalho em describe e health
  - Adicionar teste que garante que nenhum chamador do core invoca o transporte sem diretório de trabalho controlado
  - Concluído quando providers com producer divergente em describe ou health forem rejeitados, o cwd observado nunca for o do chamador, e a revalidação detectar um manifest alterado
  - _Depends: 2.1, 2.2, 3.1, 3.3_
  - _Requirements: 1.6, 1.9, 4.1, 4.3, 5.4_

- [x] 3.5 Persistir o artefato de risco e validar receipts no armazenamento de runs
  - Incluir o artefato de risco na sequência de artefatos do run
  - Oferecer leitura tipada estrita de artefatos próprios e manter a leitura em dicionário para compatibilidade
  - Exigir que todo receipt gravado passe pela validação de consistência com o hash real do resultado
  - Concluído quando um receipt de sucesso sem hash de resultado for recusado na gravação e runs antigos continuarem legíveis
  - _Depends: 1.4, 2.1_
  - _Requirements: 1.8, 1.10, 6.1_

- [x] 3.6 Reescrever routing final, revalidação e fallback na orquestração
  - Revalidar todos os candidatos pontuados antes da decisão final, refazendo o routing uma única vez quando houver mudança e falhando explicitamente numa segunda divergência
  - Gravar a decisão de routing somente após revalidação e fallback
  - Restringir fallback a candidatos com a mesma capability e ação, e falhar explicitamente sem fallback compatível
  - Manter a verificação defensiva da operação de execução antes de seguir
  - Concluído quando um cache adulterado de provider não selecionado for detectado antes da decisão final e um fallback de outra capability nunca for escolhido
  - _Depends: 2.8, 3.4_
  - _Requirements: 2.1, 3.9, 3.10, 4.3_

- [x] 3.7 Integrar policy, risco e identidade na orquestração
  - Adicionar ao pedido de execução o conjunto de aprovações por capability
  - Adicionar ao provider adversarial os modos de mutação local e destrutivo usados nos testes desta tarefa
  - Avaliar a policy e gravar o artefato de risco antes de iniciar o processo de execução
  - Recusar com instrução de desbloqueio quando a decisão for `ask` sem aprovação, e recusar com motivo quando for `deny`
  - Registrar no receipt a identidade observada do provider e o hash do artefato de risco
  - Concluído quando um provider de mutação local com trust `local` for recusado sem aprovação e executado com aprovação, e o receipt contiver fingerprint e hash de risco
  - _Depends: 2.6, 2.7, 3.5, 3.6_
  - _Requirements: 4.6, 6.1, 6.3, 6.4_

- [x] 3.8 Aplicar as validações de integridade antes e depois da execução
  - Validar o pack de contexto antes de gravá-lo e enviá-lo, tratando violação como erro do core
  - Validar o resultado contra o producer esperado (id e versão do manifest) após a execução, sem gravar resultado inválido
  - Adicionar ao provider adversarial os modos de integridade de resultado usados aqui (evidence e finding duplicados, referência pendente, artifact absoluto e com travessia, hash inválido, versão de producer divergente)
  - Concluído quando resultados com evidence duplicada, referência pendente, artifact fora da raiz ou producer divergente terminarem em falha de provider com o código específico e sem artefato de resultado gravado
  - _Depends: 3.7_
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.6, 1.7_

- [x] 3.9 Expor aprovação e risco na CLI
  - Aceitar aprovações repetíveis por capability no comando de execução
  - Mostrar a decisão de policy e as dimensões de risco na explicação do run quando o artefato existir
  - Concluído quando a execução recusada por policy sair com o código de recusa e mensagem de desbloqueio, e a explicação listar decisão, regra e dimensões
  - _Depends: 3.7_
  - _Requirements: 6.3, 6.4_

- [x] 4. Validação adversarial e cenários ponta a ponta
- [x] 4.1 Completar o provider adversarial e testar cada ataque pelo fluxo completo
  - Adicionar os modos restantes: timestamp e status inválidos, ausência de execução, protocolos malformados e duplicados, processo neto via provider, spam de capabilities e keywords, glob amplo, probe completo de ambiente cobrindo describe, health e execute
  - Exercitar pelo orquestrador completo todos os modos (os adicionados em 3.2, 3.4, 3.7 e 3.8 e os desta tarefa)
  - Concluído quando cada modo terminar no outcome e código esperados, sem artefato de resultado gravado nos casos inválidos e sem processos remanescentes
  - _Depends: 3.8_
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.6, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.8_

- [x] 4.2 (P) Adicionar testes baseados em propriedades para decodificação
  - Gerar entradas arbitrárias para cada contrato exportado e para respostas do protocolo
  - Concluído quando nenhuma entrada gerada produzir exceção diferente de erro de contrato
  - _Boundary: TestHarness:fuzz_
  - _Requirements: 2.9_

- [x] 4.3 (P) Testar isolamento de ambiente e diretório de trabalho de ponta a ponta
  - Definir no processo pai uma variável de cada categoria de credencial e verificar ausência no provider em describe, health e execute
  - Verificar que o diretório de trabalho observado em cada operação é controlado por The Forge
  - Concluído quando o probe de ambiente e o probe de diretório passarem nas três operações em Linux e Windows
  - _Boundary: TestHarness:env_
  - _Depends: 3.2, 3.4, 4.1_
  - _Requirements: 5.1, 5.2, 5.4_

- [x] 4.4 (P) Testar a segurança do cache do registry
  - Cobrir cache fora do workspace, adulteração de provider não selecionado que forçaria empate, invalidação por fingerprint, gravação concorrente, remoção do legado e identidade no receipt
  - Concluído quando todos os cenários passarem sem depender da ordem de execução dos testes
  - _Boundary: TestHarness:cache_
  - _Depends: 3.6, 3.7_
  - _Requirements: 4.3, 4.4, 4.5, 4.6_

- [x] 4.5 Testar os cenários de routing, fallback, trust e aprovação ponta a ponta
  - Tarefa de Glue lento roteia só para a capability de dados; contrato OpenAPI só para a de API; "melhore performance" sem sinais retorna ambíguo
  - Provider de dados indisponível sem fallback de mesma capability falha explicitamente
  - `providers.toml` de projeto com trust elevado é rebaixado e não executa sem autorização
  - Aprovação pela CLI libera execução de mutação local e é registrada no risco
  - Concluído quando todos os cenários passarem pela CLI e pelo orquestrador
  - _Depends: 3.9, 4.1_
  - _Requirements: 3.4, 3.5, 3.6, 3.9, 3.10, 4.1, 6.3, 6.4_

- [x] 5. CI e quality gates
- [x] 5.1 Criar os scripts de gate de dependências e instalação limpa
  - Criar o diretório de scripts de CI e substituir os testes de zero dependências e de instalação limpa existentes no teste de empacotamento por chamadas aos novos scripts (sem duplicar gates; a instalação passa a ser do wheel, não do repositório)
  - Gate de zero dependências: falhar se o projeto declarar dependência de runtime ou se o wheel contiver requisito sem marcador de extra
  - Gate de instalação limpa: ambiente virtual novo fora do repositório, instalação do wheel, checagem de consistência, entry points `theforge` e `forge`, e execução de doctor, init e da capability de eco
  - Executar ambos localmente em um teste marcado como lento
  - Concluído quando o teste lento passar localmente e falhar ao introduzir uma dependência de runtime artificial
  - _Requirements: 7.2, 7.3, 7.4_

- [x] 5.2 Criar o workflow de CI de pull request
  - Matriz Linux e Windows com Python 3.11 a 3.14, sem falha rápida, executando lint, tipos, paridade de schemas e testes offline
  - Job de empacotamento executando build e os dois gates
  - Permissões mínimas e checkout sem persistir credenciais
  - Concluído quando o workflow for válido sintaticamente e todos os comandos dele passarem localmente na plataforma disponível
  - _Requirements: 7.1, 7.2, 7.3, 7.4_

- [x] 5.3 (P) Criar os workflows de compatibilidade e de providers reais
  - Compatibilidade semanal e manual em macOS, fora do gate de PR
  - Providers reais manual e semanal, não bloqueante, com checkout dos repositórios irmãos usando token apenas nos passos de checkout e executando apenas testes marcados como provider real
  - Concluído quando ambos os workflows forem válidos sintaticamente e a seleção de provider real executar zero testes sem erro
  - _Boundary: CIWorkflows_
  - _Requirements: 7.7, 7.8_

- [x] 6. Decisões e documentação exigidas pelos requisitos
- [x] 6.1 Registrar os ADRs da Wave A
  - Local do cache do registry, modelo de policy (incluindo a diferença concreta entre trusted e local), matriz de suporte de CI (macOS e Python 3.14), pesquisa de sandbox de SO e identidade de provider
  - Concluído quando os cinco ADRs existirem no diretório de ADRs seguindo o formato dos existentes
  - _Requirements: 4.2, 4.7, 5.7, 7.8_

- [x] 6.2 Atualizar a documentação de protocolo, autoria de provider, segurança, CLI e arquitetura
  - Política de campos desconhecidos, `op`, producer com versão, regras de caminho de artifact e formato de hash, limites de manifest e catch-all
  - Justificativa de cada variável de ambiente, cwd não é sandbox, `operation_class` é declaração, semântica de trust e flag de aprovação
  - Concluído quando cada regra nova do design aparecer na documentação correspondente
  - _Requirements: 1.10, 4.2, 5.3, 5.5, 5.6_

- [x] 7. Verificação final da wave
  - Executar lint, checagem de tipos, regeneração e paridade de schemas, suíte padrão, suíte lenta e categorias de segurança
  - Concluído quando todos os comandos passarem com evidência fresca e nenhuma dependência de runtime existir
  - _Requirements: 1.11, 7.1, 7.3_

## Implementation Notes
- 1.1: tests/test_codes.py guard flags ANY string constant (incl. docstrings) containing FORGE- in src/theforge outside contracts/codes.py; reference codes by `Codes.X` name in prose. Use .venv\Scripts\python.exe (3.11), system python 3.14 lacks deps. Never git-add .kiro/.
- 1.2: conftest network guard does not patch socket.gethostbyname*/gethostbyaddr nor _socket.socket.connect; harden in 4.x if touched. allow_network applies only after autouse _network_policy runs. docs/assets/logo.png is a pre-existing untracked user file: never stage it.
- 1.3: from_dict(strict=True) available but not yet wired (3.3/3.5). Receipt *_sha256 fields not format-checked yet: cover in 2.1 validate_receipt (req 1.5). Tests use manifest_sha256="h" in test_forger/test_router. Docs part of 1.10 is in 6.2.
- 2.1: added Codes.CONTEXT_PATH (FORGE-CONTEXT-PATH) for escaping ContextPack file paths (controller-accepted, not in original design list). Integrity exports IntegrityError/Violation from theforge.contracts. Path check is lexical: rejects backslash, leading /, drive letters, .. segments.
- 2.2 design correction (controller): catch-all = `*`, `**`, `**/*`, `*.*`, `**/*.*` only; extension globs (`*.md`, `*.scala`) are allowed (echo/fixtures use them).
- 2.2: validate_manifest_limits field=="capabilities" → provider invalid; field startswith "capabilities[i]" → exclude capability i (for 3.4). Router must import is_catch_all_glob from contracts.types (2.8).
- 2.3: POSIX kill_tree path NOT executed locally (no working WSL/Docker); Linux proof deferred to CI (5.2) — must pass before /kiro-validate-impl GO. Follow-ups: fall back to taskkill if TerminateJobObject fails; capture GetLastError before CloseHandle in spawn error path.
- Snyk now authenticated: run `"$(npm prefix -g)/snyk.cmd" code test --json` (PowerShell: Join-Path (npm prefix -g) snyk.cmd). Baseline: 8 pre-existing LOW notes (schema.py CLI path, test helpers, test_security.py:14). Avoid literal credential-looking values in tests (Snyk HardcodedNonCryptoSecret).
- 2.6 (corrected in 6.1: relative argv resolved against providers.toml dir, not cwd): load_entries raises UsageError for any positional relative arg containing a separator that is not an existing FILE (directories and URLs too) — document in 6.2/ADR 0013 (or relax to exists()). identity.py docstring references ADR 0013 (create in 6.1).
- 2.7: policy evaluate(capability=) builds unlock "--approve <capability>"; rule names "default|user|project.<key>". read_only with trust blocked evaluates allow — 3.x wiring MUST keep blocked providers out before policy. Follow-up (non-blocking): warn on duplicate flattened keys (quoted vs [rules.local_mutation]) and resolve to most severe.
- 2.8: router adds guard "winner must be unique top at raw presence (shared included)" else ambiguous; shared-signal rule is per PROVIDER, only with >=2 providers. Monorepo+OpenAPI intent is now ambiguous (2 vs 2).
- 2.8 ESCALATED GAP: (a) is_catch_all_glob matches only literal forms; globs like "?*" or "**/?*" bypass → broaden to "glob with no literal alphanumeric char is catch-all" (do in 4.1, contracts.types); (b) a generic dependency/keywords declared by ONE trusted provider can still beat a specific 2-type provider — not solvable without domain knowledge; documented limitation, mitigated by trust (only user-configured providers route). Record in 6.2/ADR.
- 3.6 MUST fix orchestrator _fallback_order: `len(rank_key)==1` short-circuit now admits weak signal candidates (types<2, other capabilities) as fallbacks.
- 3.1: bad_forge reply() now always includes op; tests needing missing/wrong op must add dedicated modes (wrong-op/no-op) in 3.2.
- 3.2: transport readers use os.read and own/close their pipes; _end_tree (kill_tree+close) runs after root exit and in finally. Degraded Windows no-Job mode: grandchild survives, call bounded (~10s) — document in 6.2/ADR. Optional: skip redundant second _join. bad_forge modes added: wrong-op, no-op, stderr-flood(-crash), spawn-grandchild-timeout, exit-leave-grandchild.
- 3.3: cache file <cache>/registry/<id>-<digest12>.json; stale per-digest files not pruned (shared cache); RegistryCacheEntry.fingerprint stores digest only; remove_legacy_cache in state.py; Registry.cached_ids() feeds status. Follow-up for 4.4: add test that symlinked .forge/registry is unlinked without deleting target.
- 3.4: revalidate(ids) never writes cache; on "changed" the orchestrator (3.6) must invalidate(id) then records()+route() once. No in-use record → "changed". Registry.provider_cwd() helper gives per-call temp cwd. Warnings may duplicate across refresh+revalidate (cosmetic).
- 3.5: RunStore.write("receipt") validates against persisted_sha256(run,"result") recomputed from disk; refuses before writing. tests/test_forger.py::test_case_a_end_to_end skips "risk" in ARTIFACTS loop — 3.7 MUST remove that skip.
- 3.6: orchestrator _final_route revalidates all candidates (redo once on changed/unreachable; second changed → REGISTRY_MANIFEST_CHANGED); routing written once; fallback = same capability + resolved action + routable + rank>=MIN on signal path; _require_op → refused PROTO_OP_UNSUPPORTED. Controller fix: explicit = bool(requested_capability).
- 3.7: Forger._apply_policy runs after _require_op, before context/execute; writes risk; ask→refused POLICY_APPROVAL_REQUIRED unlock "--approve <cap>", deny→POLICY_DENIED. AskRequest.approvals frozenset. Receipt carries executable/fingerprint/observed_version/risk_sha256; policy warnings → receipt limitations "policy: ...". bad_forge modes mutating/destructive added.
- 3.8: bad_forge execute modes added: dup-evidence, dup-finding, dangling-ref, artifact-absolute, artifact-traversal, bad-hash, bad-artifact-hash, bad-timestamp, wrong-version-producer. Inconsistent context pack → provider_failure Codes.INTERNAL (detail has CONTEXT_* code).
- 3.9: ask --approve CAPABILITY (append); explain shows Risk/Policy/Dimensions lines ("Risk: not recorded" when absent). Optional: show policy.reason in text explain for deny; CLI-level deny test in 4.5.
- 4.1: full suite ~7min on this host (adversarial sweep ~220s: 51 modes x subprocess spawns). NEVER run two pytest sessions concurrently (memory pressure, PersistenceError flake). Catch-all: no alnum after dropping negated/ranged bracket classes; positive literal classes count; str.isalnum. Sweep SWEEP table must list every bad_forge mode (AST coverage test). Consider pytest-xdist for CI in 5.2 if needed.
- 4.2: fuzz derandomize=True. Follow-ups: deep-but-under-limit Any payloads may RecursionError in redact/canonical_json (check in persistence/redaction work); check_sha256/manifest messages repr untrusted strings unbounded (could reuse contracts.base._brief).
- 4.3: tests/test_env_isolation.py drives describe/health/execute via core path with recording transport filtered by producer id (builtin echo also described). env-probe-full reports cwd in health+execute only (describe cwd would churn manifest hash -> MANIFEST_CHANGED). Linux proof deferred to CI 5.2. Watch: Windows temp-dir `not exists()` assert may flake under file locks (ignore_cleanup_errors).
- 4.4: pytest-randomly absent; order independence via reverse explicit node ids (NEVER pass an empty id list: runs full suite). Windows concurrent os.replace drops some cache writes as WinError 5 warnings (by design). Optional: assert writer success count >0 in concurrency tests.
- 4.5: FOLLOW-UP: Registry.entries() appends config warnings to self.warnings on every call (dupes accumulate in long-lived Registry); CLI _warn dedupes via dict.fromkeys (symptom). Move dedupe into Registry and drop CLI dedupe. Demoted project provider w/o authorization -> ambiguous (echo weak candidates). fixture_forge.py accepts --unhealthy.
- 5.1: gate tests live in tests/test_packaging.py (design named test_ci_gates.py; FILE_MARKERS entry unused). Local slow wheel build downloads hatchling (slow marker allows network). addopts --basetemp=.pytest_tmp is SHARED: concurrent pytest sessions delete each other's tmp dirs -> parallel runs must pass their own --basetemp. Snyk CLI flags check_zero_deps.py ZipFile(wheel) as PT (LOW, operator-supplied CI path; inline deepcode ignore not honored by CLI) -> accepted false positive.
- 5.2: ci.yml uses actions/checkout@v7 + setup-python@v7 (verified real); PyYAML added to [dev] for workflow structure tests. Local full suite ~3min (894 pass). Linux + py3.12-3.14 (incl. POSIX kill_tree, env isolation on Linux) ONLY proven by first real GitHub run -> must be green before /kiro-validate-impl GO. Follow-ups: pin actions to SHAs; sdist excludes for local untracked dirs (.tokensave/, .kiro/) — CI checkout unaffected.
- 5.3: real-providers.yml uses secret SIBLING_REPOS_TOKEN (fallback github.token; siblings public) — record in 6.1/6.2 docs along with sibling paths siblings/spark-forge-aws, siblings/api-forge (no env contract yet; Wave B defines). continue-on-error redundant (no PR trigger) — consider dropping in Wave B for failure visibility.
- 6.2: FOLLOW-UP (security gap, code change): execute envelope Response.producer is never checked (only ExecutionResult.producer via validate_result); describe/health check envelope producer. Req 1.6 still met. docs/protocol.md documents current behavior. README "Status: ciclo 1" stale. security.md paraphrases CREDENTIAL_PATTERNS — keep in sync.
- 7 (2026-10-03, Windows/py3.11): ruff OK, mypy OK (58 files), schema regen+parity OK, default suite 905 passed/2 skipped (env skips), slow 2 passed, security 290 passed, zero-deps gate OK. Linux/macOS/py3.12-3.14 pending first GitHub CI run.
- Post-validation follow-ups RESOLVED (2026-10-03, 3bad9a5..01b9f19, reviewed APPROVED round 3): 2.1 explicit --capability with only non-executing possible executors -> refused FORGE-PROTO-OP-UNSUPPORTED (conservative: never while another declarer could execute; unknown manifests block blame); router notes relevant non-executing providers; execute envelope producer checked; explain text shows state=; Registry dedupes warnings at source (CLI dedupe removed); actions pinned to SHAs (checkout v7.0.1 3d3c42e5, setup-python v7.0.0 5fda3b95) + test; check_zero_deps reads wheel via directory listing (Snyk back to 8 baseline LOW); README status. Suite 913 passed. STILL OPEN: registry cache write bypasses security.redact (decide redact vs ADR 0009 exception); first green GitHub CI run before validate-impl GO.
