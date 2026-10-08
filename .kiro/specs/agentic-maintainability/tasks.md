# Implementation Plan — agentic-maintainability (Wave E)

> Pré-requisitos: as tarefas 1–4 dependem só da Wave A (já mesclada) e podem começar a qualquer momento. As tarefas 5.x exigem `real-provider-integration`, `context-intelligence-v2` e `cross-forge-foundation` implementadas e mescladas, porque consolidam os ADRs 0014–0019, os documentos `docs/real-providers.md`, `docs/versioning.md`, `docs/capabilities.md`, `docs/performance.md`, `docs/errors.md` e o exit code 6. Nada em `src/theforge/`, `schemas/`, `adapters/`, `.github/` ou `pyproject.toml` muda nesta spec. `.kiro/specs/` e `.kiro/steering/` continuam fora do git. Numeração de ADRs congelada: 0014/0017 `real-provider-integration`, 0015/0016 `context-intelligence-v2`, 0018/0019 `cross-forge-foundation`, 0020 esta spec. `cross-forge-foundation` tem gate de validação após sua tarefa 5 e pode ser entregue em duas metades (D1 multi-provider; D2 integridade, explain e erros): a dependência das tarefas 5.x é revalidada após cada metade mesclada e elas só fecham após a revalidação pós-D2.

- [x] 1. Fundação: ferramenta de auditoria e infraestrutura de testes
- [x] 1.1 Criar a base da ferramenta de auditoria de assets agentic e registrar os testes novos
  - Criar a ferramenta de manutenção fora do pacote, só com stdlib e tipada no modo estrito, com uma configuração declarativa versionada ao lado dela
  - Ler e validar a configuração (hosts com diretório de skills e arquivos de instrução, metadados de host, cópias de referência, placeholders de instalação, assets exclusivos, divergências aceitas, âncoras de invariantes, orçamentos, ponteiros, regras movidas), rejeitando chave desconhecida, tipo errado e motivo vazio com erro que nomeia a chave; as seções de invariantes, orçamentos, ponteiros e regras movidas são opcionais
  - Obter o inventário apenas de arquivos rastreados pelo git, sem escrita, sem fsmonitor e com ambiente mínimo, e normalizar todo texto lido para fins de linha LF
  - Registrar os dois arquivos de teste novos na tabela de categorias da suíte (paridade como integração, consistência de documentação como unidade)
  - Concluído quando testes carregarem a ferramenta pelo caminho, uma configuração inválida falhar com a chave nomeada, um arquivo não rastreado numa árvore git temporária não aparecer no inventário, CRLF e LF produzirem o mesmo texto normalizado, e ruff e mypy passarem sobre a ferramenta
  - _Requirements: 1.6, 2.6, 10.2, 10.3_

- [x] 2. Núcleo da auditoria
- [x] 2.1 Comparar skills equivalentes por perfil semântico
  - Agrupar as skills equivalentes pelo nome em cada host com diretório de skills e reportar skill ausente em algum host
  - Extrair de cada skill o perfil semântico (nome do frontmatter, caminhos de repositório referenciados, skills referenciadas, fases de `spec.json`, conjunto de arquivos de apoio sem metadados de host), normalizando placeholders de argumento e prefixos de invocação
  - Classificar como diferença de sintaxe tolerada quando o texto difere e o perfil é igual, e como drift quando algum elemento do perfil diverge, nomeando skill, hosts e elemento
  - Concluído quando testes sobre árvores temporárias provarem que versões com envelopes, cabeçalhos, `$1`/`{feature}` e `/kiro-`/`$kiro-`/`/kiro:` diferentes produzem o mesmo perfil, que um caminho referenciado só num host vira drift e que uma skill faltante num host é reportada com o host faltante
  - _Requirements: 1.1, 1.2, 2.2, 2.3_

- [x] 2.2 Comparar arquivos de apoio entre hosts e com as cópias de referência
  - Comparar o conteúdo normalizado de cada regra e template de skill entre os hosts
  - Comparar cada regra de skill com a cópia de referência versionada correspondente depois de aplicar os placeholders de instalação declarados; templates sem cópia de referência só são comparados entre hosts
  - Concluído quando testes provarem que a diferença de idioma de instalação não gera achado, que qualquer outra diferença gera drift de arquivo de apoio nomeando o arquivo, e que divergência entre hosts é reportada mesmo quando não há cópia de referência
  - _Requirements: 1.4, 2.4_

- [x] 2.3 Tratar assets exclusivos de host e divergências aceitas
  - Reportar como informativos os assets exclusivos declarados com motivo e como falha todo arquivo rastreado de diretório de host que não pertença a uma skill equivalente nem esteja declarado
  - Casar cada drift com as divergências aceitas registradas (skill, elemento, hosts, valor) e reclassificá-lo como aceito com a justificativa
  - Reportar como falha toda divergência aceita que não corresponde a nenhum drift atual
  - Concluído quando testes provarem que um asset exclusivo não declarado falha, um declarado aparece como informativo, um drift registrado deixa de falhar e uma entrada aceita sem drift correspondente falha pedindo sua remoção
  - _Requirements: 1.2, 1.3, 2.5_

- [x] 2.4 Verificar instruções de host: invariantes, orçamentos, ponteiros e regras movidas
  - Exigir o bloco de invariantes delimitado pelos marcadores em cada arquivo de instrução de cada host, com texto normalizado idêntico entre os arquivos e todas as âncoras obrigatórias presentes
  - Executar cada checagem só quando sua seção estiver declarada na configuração (seção ausente → nenhum achado de instrução), para que a baseline de 4.3 não dependa das instruções reescritas
  - Medir cada arquivo de instrução em bytes UTF-8 com fins de linha LF e comparar com o orçamento declarado
  - Exigir os ponteiros obrigatórios por arquivo de instrução e a presença de cada regra movida no destino declarado
  - Concluído quando testes sobre árvores temporárias provarem falha para bloco ausente, bloco divergente entre arquivos, âncora ausente, arquivo acima do orçamento, ponteiro ausente e regra movida ausente no destino, nenhum achado quando tudo está consistente, inclusive com um dos arquivos em CRLF, e nenhum achado de instrução quando as seções correspondentes não estão declaradas
  - _Requirements: 3.2, 3.3, 4.4, 4.6, 4.7_

- [x] 2.5 Emitir o relatório determinístico e a interface de linha de comando
  - Ordenar todos os achados de forma total e produzir o relatório em texto (tabela de skills por host, achados por categoria) e em JSON com chaves ordenadas
  - Oferecer a execução por linha de comando com opções de raiz do repositório e de caminho da configuração (padrões: o próprio repositório e a configuração versionada) e `--json`, com saída 0 sem falhas, 1 com falhas e 2 para erro de configuração ou de git, sem traceback
  - Os testes de subprocesso usam árvores temporárias inicializadas como repositório git com os arquivos adicionados ao índice, porque o inventário vem do git
  - Concluído quando duas execuções em subprocesso sobre o mesmo conteúdo produzirem saída idêntica, uma árvore com drift sair com 1 e listar o drift, uma configuração inválida sair com 2 e uma mensagem sem traceback, e o JSON for parseável
  - _Requirements: 1.1, 1.5, 1.6_

- [x] 3. (P) Registrar o ADR 0020 de fonte canônica de assets agentic e política de hooks
  - Registrar contexto (mirrors gerados por instalador, sintaxe por host, `AGENTS.md` compartilhado, comandos legados, steering local), alternativas (mirrors à mão com paridade testada; reinstalação de instalador com versão fixada; fonte canônica no repositório com renderização stdlib; plugin do Claude Code), critério de decisão, custo de migração e caminho recomendado com gatilho objetivo para migrar
  - Declarar que nenhuma migração é executada, que o pacote `theforge` nunca inclui nem requer os assets e como ficam os assets locais, incluindo os arquivos de steering
  - Registrar a política de hooks (só checagens focadas e determinísticas sobre os arquivos alterados; nunca a suíte completa a cada edição; sem rede) e a limitação da paridade por perfil
  - Concluído quando o ADR existir com número 0020, linha de status e as seções de alternativas, decisão, consequências e política de hooks
  - _Boundary: Adr0020_
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 8.1_

- [x] 4. Assets e instruções do repositório
- [x] 4.1 (P) Remover os comandos Kiro legados exclusivos do Claude
  - Remover os 11 comandos de `.claude/commands/kiro/`, cada um coberto por uma skill equivalente do Claude (`spec-impl` coberto por `kiro-impl`)
  - Concluído quando não houver nenhum arquivo rastreado sob `.claude/commands/` e cada comando removido tiver skill equivalente existente em `.claude/skills/`
  - _Boundary: LegacyCommandRemoval_
  - _Requirements: 4.8_

- [x] 4.2 (P) Limpar a raiz do repositório e proteger contra arquivos acidentais
  - Remover da raiz os arquivos criados por redirecionamento acidental de shell (`tuple[str` e, se presentes, `(3` e `dict[str`)
  - Acrescentar à suíte de paridade a verificação de que toda entrada da raiz tem nome no padrão de nomes do projeto
  - Concluído quando a raiz não tiver entradas fora do padrão e o teste falhar ao criar temporariamente uma entrada com `[` no nome numa cópia de teste da verificação
  - _Boundary: RootHygiene (também edita a suíte de paridade)_
  - _Requirements: 6.1, 6.2_

- [x] 4.3 Declarar a configuração real dos hosts e estabelecer a baseline da auditoria
  - Declarar os três hosts, o metadado do Codex por skill, a cópia de referência das regras, o placeholder de idioma de instalação (sem ainda declarar invariantes, orçamentos, ponteiros nem regras movidas, que entram em 4.7) e o agente de revisão cross-spec do Codex como exclusivo de host com motivo
  - Rodar a auditoria sobre o repositório real; corrigir no mirror divergente todo drift que mude comportamento e registrar como aceita, com justificativa, toda divergência de fraseado (esperadas: textos de saída de `kiro-spec-quick` e nota de estilo de `kiro-steering`)
  - Concluído quando a auditoria do repositório real sair com 0, listar as 17 skills nos três hosts, não acusar asset exclusivo não declarado e cada divergência aceita tiver motivo não vazio
  - _Depends: 4.1_
  - _Requirements: 1.1, 1.3, 2.1, 2.3_

- [x] 4.4 Escrever o guia de desenvolvimento com agentes
  - Criar `docs/agentic.md` com: hosts suportados (arquivo de instrução, diretório de skills, prefixo de invocação), workflow Kiro (fases, aprovação em 3 fases, `-y` só para fast-track, status), assets versionados vs locais e a decisão de não versionar specs e steering, manutenção dos mirrors (editar os três hosts na mesma mudança, rodar a auditoria, registrar aceitas, procedimento após reinstalar o instalador Kiro), como mudar as invariantes nos dois arquivos juntos, orçamentos de tamanho, correspondência dos comandos legados para as skills e resumo da política de hooks
  - Na seção de hooks, resumir a política e linkar o ADR 0020
  - Concluído quando o documento contiver cada regra Kiro hoje presente no `CLAUDE.md` e no `AGENTS.md` que sairá deles, a tabela de correspondência dos 11 comandos removidos e os orçamentos de 2 500 e 6 000 bytes, e o link para o ADR 0020 resolver
  - _Depends: 3_
  - _Requirements: 3.4, 4.1, 4.3, 4.5, 4.8, 5.4, 5.6_

- [x] 4.5 Reescrever o `CLAUDE.md` com invariantes e regras persistentes curtas
  - Escrever o bloco de invariantes entre os marcadores, com escopo explícito: core (`src/theforge`) stdlib-only, Python ≥ 3.11 e nunca importando especialistas; adapters (`adapters/`) instalados no interpretador de cada especialista (piso 3.10), únicos a importar `sparkforge`/`apiforge`; Forge Protocol; routing determinístico com `ambiguous`; nenhum sucesso sem `ExecutionResult`; tudo que o core persiste passa por `security.redact`, com `.forge/runs/<id>/work/` (dados do provider) fora dessa regra, e credenciais nunca no env dos providers; nenhum domínio no core; contratos `theforge/<Name>/v1` com o comando de regeneração; setup de desenvolvimento com os adapters editáveis (`python -m pip install -e .[dev] -e ./adapters/sparkforge -e ./adapters/apiforge`, conforme `real-provider-integration`) e comandos de teste, lint e tipos
  - Manter a regra de idioma, os ponteiros para `docs/agentic.md`, `docs/architecture.md`, `docs/protocol.md`, `docs/adr/` e o local das skills do Claude
  - Concluído quando o arquivo tiver no máximo 2 500 bytes e nenhuma regra removida deixar de estar em `docs/agentic.md`
  - _Requirements: 3.1, 3.2, 4.1, 4.7_

- [x] 4.6 Consolidar o `AGENTS.md` num único documento para Codex e Devin
  - Substituir os dois blocos concatenados por um documento com o mesmo bloco de invariantes do `CLAUDE.md`, uma seção comum (regra de idioma, workflow Kiro resumido com link para `docs/agentic.md`) e seções próprias de Codex (`.agents/skills`, `$kiro-*`, subagentes e fallback inline identificado) e de Devin Local/CLI (`.devin/skills`, `/kiro-*`, delegação, escritores sequenciais, fallback inline)
  - Concluído quando o arquivo tiver no máximo 6 000 bytes, nenhuma seção duplicada e o bloco de invariantes idêntico ao do `CLAUDE.md`
  - _Requirements: 3.1, 3.2, 4.2, 4.7_

- [x] 4.7 Ativar as verificações de instrução e de paridade sobre o repositório real
  - Declarar na configuração as âncoras obrigatórias das invariantes (incluindo as de escopo core/adapters, a fronteira de redação de `work/` e o setup com adapters editáveis), os orçamentos, os ponteiros por arquivo e cada regra movida com origem e destino
  - Acrescentar à suíte de paridade os testes sobre o repositório real, um por categoria de falha, com mensagem que lista os achados, pulando com motivo explícito só quando o git não estiver disponível
  - Concluído quando a suíte offline passar com a auditoria do repositório real sem achados de falha, e falhar ao alterar uma linha do bloco de invariantes em só um dos arquivos de instrução
  - _Requirements: 2.1, 2.6, 3.3, 4.3, 4.4, 4.5, 4.6_

- [x] 5. Consolidação da documentação do ciclo (exige as Waves B, C e D mescladas)
- [x] 5.1 Criar o índice de ADRs com o mapa das decisões exigidas
  - Listar todo ADR com número, título linkado e status, e mapear as 8 decisões exigidas pelo ciclo ao ADR e à spec dona
  - Conferir a presença dos ADRs exigidos nos números congelados (0014, 0015, 0017, 0018, além de 0009–0011), sem numeração alternativa; se algum faltar, parar e reportar bloqueio da spec dona em vez de redigir o ADR
  - Concluído quando todo arquivo de ADR aparecer no índice e as 8 decisões apontarem para arquivos existentes
  - _Depends: 3_
  - _Requirements: 8.1, 8.2, 8.4_

- [x] 5.2 Consolidar README e documentos de `docs/`
  - Atualizar no README o estado do ciclo (Cycle 2 concluído, uma linha por wave), o índice de todos os documentos existentes (incluindo `docs/agentic.md`, o índice de ADRs e os documentos das Waves B–D; o link do relatório entra em 5.3), a tabela de exit codes igual à de `docs/cli.md` com o exit 6 (divergência de integridade em `explain` e `replay --mode verify`), o setup de desenvolvimento com os adapters editáveis e o comando da auditoria em "Desenvolvimento"
  - Garantir que `docs/protocol.md` e todo documento com tabela de códigos `FORGE-*` linkem `docs/errors.md` como lista canônica, sem reescrever as tabelas das specs donas
  - Conferir que a versão vigente de `theforge.__version__` tem linha na matriz de `docs/versioning.md` (teste de matriz de compatibilidade verde); se não tiver, registrar bloqueio da wave que fez o bump
  - Remover marcas de wave obsoletas dos títulos de arquitetura e segurança e corrigir links e exemplos residuais, sem reescrever seções técnicas das specs donas; registrar para o relatório qualquer seção técnica desatualizada encontrada
  - Confirmar que `theforge` aparece como nome canônico e `forge` como alias no README e na documentação da CLI, e que a regeneração de schemas não produz diferença
  - Concluído quando o README linkar todos os documentos existentes em `docs/`, as duas tabelas de exit codes coincidirem, `docs/protocol.md` linkar `docs/errors.md`, a versão vigente tiver linha na matriz e a regeneração de schemas não alterar `schemas/`
  - _Depends: 4.4, 5.1_
  - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.7_

- [x] 5.3 Escrever o relatório final do Cycle 2
  - Acrescentar ao README o link do relatório no estado do ciclo e no índice de documentos
  - Escrever as 11 seções exigidas a partir do que as Waves A–D entregaram, citando specs só pelo nome, sem links para `.kiro/`, com versões tiradas da matriz de `docs/versioning.md` e nomes finais de artefatos do run (ex.: `workspace-descriptor`)
  - Em "Resultados medidos", uma tabela com métrica, valor e origem (comando e data, workflow e run, ou documento), marcando "não medido" quando não houver fonte
  - Em "Prova cross-forge", declarar se a prova real rodou e, se não rodou neste ambiente, o motivo (ex.: Python 3.12 do API Forge ausente) e o substituto offline usado
  - Concluído quando o relatório tiver as 11 seções, toda linha de resultado medido tiver origem ou "não medido", nenhuma prova não executada for apresentada como executada e o README linkar o relatório
  - _Depends: 5.2_
  - _Requirements: 9.1, 9.2, 9.3, 9.4_

- [x] 5.4 Automatizar a verificação de links, índice e nome canônico da CLI
  - Verificar que todo link relativo de README, instruções de host e `docs/` resolve para arquivo existente e nenhum aponta para assets locais não versionados (registros históricos do ciclo 1 isentos só da resolução de links)
  - Verificar que o README linka todo documento de `docs/`, o índice de ADRs e o relatório, e que os exemplos de comando usam `theforge` e o alias `forge` só aparece em prosa
  - Verificar que `docs/errors.md` é tratado como lista canônica: indexado no README, linkado por `docs/protocol.md` e por todo documento com tabela de códigos `FORGE-*` (o conteúdo contra a taxonomia continua com o teste da Wave D)
  - Concluído quando a suíte offline passar sobre a documentação consolidada e cada verificação falhar ao introduzir, numa cópia temporária, o defeito correspondente (link quebrado, link para `.kiro/`, documento fora do índice, exemplo com `forge`, tabela de códigos sem link para `errors.md`)
  - _Requirements: 7.1, 7.2, 7.3, 7.5, 9.4, 10.4_

- [x] 5.5 Automatizar a verificação de exit codes, índice de ADRs e relatório
  - Verificar a igualdade das tabelas de exit codes do README e da documentação da CLI com os desfechos da CLI mais os exit codes fixos `{1, 2, 5, 6, 70, 130}`, marcados como gatilho de revalidação da Wave D; o 6 é a divergência de integridade emitida por `explain` e por `replay --mode verify` com divergência, fora do mapa de status
  - Verificar o índice de ADRs (números únicos, linha de status, todo arquivo indexado, decisões exigidas com mensagem que nomeia a spec dona) e as 11 seções do relatório com a coluna de origem preenchida
  - Concluído quando a suíte offline passar e cada verificação falhar ao introduzir, numa cópia temporária, o defeito correspondente (exit code faltando, ADR fora do índice, número de ADR duplicado, seção do relatório removida, origem vazia)
  - _Requirements: 7.6, 8.3, 9.2, 9.5_

- [x] 6. Validação final
  - Preparar o ambiente com `python -m pip install -e .[dev] -e ./adapters/sparkforge -e ./adapters/apiforge` (conformance offline exige os adapters)
  - Rodar lint, tipos estritos, paridade de schemas, a auditoria por linha de comando e a suíte offline completa, incluindo o teste da matriz de compatibilidade (versão vigente com linha em `docs/versioning.md`)
  - Confirmar que nenhum arquivo de `src/theforge/`, `schemas/`, `adapters/`, `.github/` ou `pyproject.toml` mudou, que nenhuma dependência nova entrou e que `.kiro/specs/` e `.kiro/steering/` continuam não rastreados
  - Concluído quando lint, tipos, paridade de schemas, auditoria, matriz de compatibilidade e suíte offline passarem, o diff dessas áreas for vazio e nenhum teste novo ficar fora da tabela de categorias
  - _Requirements: 2.6, 7.7, 10.1, 10.2, 10.4_

## Implementation Notes
- Cross-spec review (minor, open): CLAUDE.md 2,500-byte budget is tight (scoped invariants block ~1,880 bytes) — write tersely or re-measure and adjust agentic.toml budget deliberately, recording why.
- (2026-10-04) Notice from cross-forge-foundation gate 5.3: multi-provider half (a) is complete on feat/cycle2-wave-d — re-check consolidation (docs, exit codes incl. `planned`→0 pending D 7.x, ADR index) per this spec's dependency on D 5.3; re-check again after D 9.3.
- 1.1 (2026-10-04): scripts/agentic/audit_assets.py API: load_config(path)->AgenticConfig (AgenticConfigError 'invalid key ...'), tracked_files(repo) (AgenticGitError → exit 2 in 2.5; --cached lists deleted-but-tracked files), normalize_text, read_text, DEFAULT_CONFIG. MovedRule from/to → source/target. Tests reuse MINIMAL_CONFIG/FULL_CONFIG, _git, _snapshot, requires_git.
- 3 (2026-10-04): ADR 0020 written. Possible gap req 5.2: hatch default sdist would ship versioned .claude/.agents/.devin/.codex as plain source (wheel is clean) — decide in 5.x/6 (exclude from sdist in pyproject). 5.1 index row 'fonte canônica de assets agentic' → ADR 0020. Link docs/agentic.md from ADR once 4.4 creates it.
- 4.1/4.2 (2026-10-04): commands→skills mapping: spec-init→kiro-spec-init, spec-requirements→kiro-spec-requirements, spec-design→kiro-spec-design, spec-tasks→kiro-spec-tasks, spec-impl→kiro-impl, spec-status→kiro-spec-status, steering→kiro-steering, steering-custom→kiro-steering-custom, validate-gap/design/impl→kiro-validate-*. Root check lives in tests/test_root_hygiene.py (design put it in test_agentic_parity.py — fold in later optional).
- 4.3/4.4 (2026-10-04): audit exits 0 (32 host-syntax info, 3 accepted, 1 host-only). ears-format.md diff = install language only. Guide uses invariants markers <!-- theforge:invariants:begin --> / <!-- theforge:invariants:end --> and anchor '3-phase approval workflow' for 4.5–4.7. .kiro/steering holds only roadmap.md.
- 5.1/5.2 (2026-10-04): DEVIATION accepted by controller: pyproject.toml sdist excludes agentic dirs + .kiro + .tokensave + CLAUDE/AGENTS.md (sdist was leaking local untracked .kiro specs) — task 6 'pyproject unchanged' check must allow this. 5.3 report: note architecture.md 'Direção de imports' wording 'Waves A–C' stale. Snyk ReDoS (MEDIUM) in audit placeholder fixed.
- 5.4/5.5 (2026-10-04): report must be docs/reports/cycle-2.md with the 11 REPORT_SECTIONS as exact '## <title>' headings (see tests/test_docs_consistency.py), 'Resultados medidos' table with non-empty 'Origem' column ('não medido' when no source), no .kiro links, README must index the report.
- 6 (2026-10-04): final validation GREEN on 153ccc0: ruff, mypy 119, schema parity, audit exit 0, offline suite 2859 passed/5 skipped in 3 chunks, slow 4, harness 17; protected-area diff vs wave-d = pyproject.toml sdist excludes only (accepted deviation); .kiro specs/steering untracked.
