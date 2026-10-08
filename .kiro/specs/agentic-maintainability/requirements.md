# Requirements Document

## Project Description (Input)
**Quem tem o problema:** mantenedores de The Forge e os agentes de código (Claude Code, Codex, Devin e demais hosts) que trabalham no repositório.

**Situação atual:** os mirrors de assets agentic (`.claude/`, `.agents/`, `.codex/`, `.devin/`) são mantidos à mão, sem teste de drift; 17 skills kiro existem em 3 mirrors com diferenças de sintaxe por host; `.claude/commands/kiro` só existe no Claude; o AGENTS.md não carrega as invariantes do projeto; o CLAUDE.md mistura regras do Forge com instruções Kiro extensas; `.kiro/steering/` só ganhou o roadmap neste ciclo; há arquivos soltos na raiz (ex.: `(3`, `dict[str`, `tuple[str`); documentação e ADRs precisam refletir o Cycle 2.

**O que deve mudar:** teste de drift semântico entre hosts, invariantes do projeto presentes nas instruções de todos os hosts, CLAUDE.md curto, proposta (sem migração automática) de fonte canônica/plugin de assets agentic, documentação e ADRs consolidados e relatório final do Cycle 2. Abordagem: auditar e testar antes de migrar; nenhuma migração grande sem benefício. Fora de escopo: migração automática para plugin e mudanças no runtime.

## Introduction
As Waves A–D do Cycle 2 entregaram um core endurecido, adapters reais, contexto v2 e coordenação cross-forge. Esta spec entrega a Wave E, a última do ciclo: torna os assets agentic do repositório (skills, comandos e instruções por host) verificáveis contra drift, garante que as invariantes do projeto cheguem a todos os hosts de agentes suportados com o menor contexto sempre carregado possível, registra uma proposta de fonte canônica para esses assets sem migrá-los, consolida a documentação e os ADRs do ciclo e produz o relatório final do Cycle 2.

A abordagem é auditar e testar antes de mudar. Nada nesta spec altera o comportamento do runtime `theforge`: o pacote continua stdlib-only e as mudanças ficam em documentação, instruções de agentes, assets agentic versionados e verificações de manutenção.

Termos usados abaixo:
- **Host**: ferramenta de agente de código suportada pelo repositório (Claude Code, Codex, Devin).
- **Assets agentic versionados**: arquivos de skills, comandos, agentes e instruções de host rastreados pelo git (hoje `.claude/skills/kiro-*`, `.claude/commands/kiro/`, `.agents/skills/kiro-*`, `.devin/skills/kiro-*`, `.codex/agents/`, `.kiro/settings/`, `CLAUDE.md`, `AGENTS.md`).
- **Assets locais não versionados**: arquivos agentic deliberadamente fora do git por decisão do mantenedor (`.kiro/specs/`, `.kiro/steering/`, `.claude/agents/`, `.agents/skills/source-command-*` e similares).
- **Skills equivalentes**: a mesma skill (mesmo nome) presente em mais de um host.

## Boundary Context
- **In scope**: auditoria e relatório de drift dos assets agentic versionados; verificação automatizada de paridade semântica entre skills equivalentes, tolerante a diferenças de sintaxe de host; bloco de invariantes do projeto presente nas instruções de todos os hosts; redução do CLAUDE.md e do AGENTS.md sem perda de comportamento; tratamento dos comandos Kiro exclusivos do Claude; proposta documentada (ADR) de fonte canônica e de empacotamento como plugin; política para hooks de desenvolvimento; higiene da raiz do repositório; consolidação de README, `docs/` e índice de ADRs; ADR da fonte canônica de assets agentic; verificação de que os ADRs exigidos pelo ciclo existem; relatório final do Cycle 2.
- **Out of scope**: migração automática dos assets para plugin ou para uma fonte canônica gerada; qualquer mudança no runtime `theforge` (contratos, CLI, routing, protocolo, registry, contexto, policy); versionar assets locais não versionados (`.kiro/specs/`, `.kiro/steering/` e demais); criar os arquivos de steering `product.md`, `tech.md` e `structure.md`; reescrever o conteúdo técnico das seções de documentação que pertencem às specs anteriores; os ADRs 0014–0019, que pertencem às specs anteriores.
- **Adjacent expectations**:
  - `real-provider-integration` entrega os ADRs 0014 e 0017 e os documentos `docs/real-providers.md`, `docs/versioning.md` e `docs/capabilities.md`; `context-intelligence-v2` entrega os ADRs 0015 e 0016 e `docs/performance.md`; `cross-forge-foundation` entrega os ADRs 0018 e 0019, `docs/errors.md` (lista canônica de códigos), o exit code 6 (divergência de integridade em `explain` e `replay --mode verify`) e os comandos `plan`, `workspace show` e `replay`. A numeração desses ADRs é fixa. Esta spec consolida e verifica esses artefatos; não os redefine.
  - Mudança em `ExplainReport`, na taxonomia de códigos, nos códigos publicados ou nos exit codes (gatilho declarado por `cross-forge-foundation`) exige que esta spec revalide a documentação consolidada e as verificações automatizadas de documentação.
  - A paridade de schemas publicados continua sendo a verificação já existente no CI; esta spec só a confirma na consolidação final.
  - Os resultados medidos do relatório final vêm do que as specs anteriores registraram ou do que for medido na consolidação; esta spec não inventa números.

## Requirements

### Requirement 1: Auditoria de drift dos assets agentic
**Objective:** As a mantenedor, I want um relatório reproduzível das diferenças entre os assets agentic de cada host, so that eu saiba quais divergências são de sintaxe de host e quais mudam o comportamento dos agentes.

#### Acceptance Criteria
1. When o mantenedor executa a auditoria de assets agentic, The Forge shall examinar os assets agentic versionados de `.claude/`, `.agents/`, `.codex/` e `.devin/` e emitir um relatório com, para cada skill equivalente, os hosts em que existe e as divergências semânticas encontradas.
2. The Forge shall classificar cada diferença encontrada pela auditoria como diferença de sintaxe de host tolerada, divergência semântica aceita com justificativa registrada, ou drift.
3. The Forge shall listar no relatório da auditoria os assets presentes em um único host e, para cada um, se é exclusivo de host por decisão registrada ou um asset faltante nos demais hosts.
4. The Forge shall comparar também os arquivos de apoio das skills (regras e templates) com as cópias de referência versionadas em `.kiro/settings/` e reportar qualquer divergência que não seja substituição de placeholder de instalação.
5. When a auditoria é executada duas vezes sobre o mesmo conteúdo, The Forge shall produzir relatórios idênticos.
6. The Forge shall executar a auditoria sem rede, sem modificar nenhum arquivo do repositório e sem depender de assets locais não versionados.

### Requirement 2: Verificação automatizada de paridade entre hosts
**Objective:** As a mantenedor, I want que a suíte de testes falhe quando skills equivalentes divergirem em conteúdo semanticamente compartilhável, so that o drift entre hosts seja detectado no pull request e não pelo comportamento errado de um agente.

#### Acceptance Criteria
1. If o conteúdo semanticamente compartilhável de skills equivalentes diverge entre hosts e a divergência não está registrada como aceita, the suíte de testes offline shall falhar identificando a skill, os hosts e o elemento divergente.
2. The suíte de testes offline shall tolerar diferenças de sintaxe específicas de host, incluindo cabeçalho de metadados, envelopes de marcação, prefixo de invocação de skill, forma do argumento da feature e terminologia de delegação a subagentes.
3. If uma skill existe em um host e falta em outro host que deveria tê-la, the suíte de testes offline shall falhar identificando a skill e o host faltante.
4. If um arquivo de apoio de uma skill (regra ou template) diverge entre hosts ou da cópia de referência em `.kiro/settings/`, além da substituição de placeholder de instalação, the suíte de testes offline shall falhar identificando o arquivo.
5. If uma divergência registrada como aceita deixa de existir, the suíte de testes offline shall falhar pedindo a remoção do registro, de modo que o registro de divergências aceitas nunca fique desatualizado.
6. The suíte de testes offline shall executar a verificação de paridade na mesma execução que já roda no gate de pull request, sem novo job de CI e sem dependência nova.

### Requirement 3: Invariantes do projeto em todos os hosts
**Objective:** As a mantenedor, I want que as invariantes do projeto estejam nas instruções de todos os hosts suportados, so that Claude, Codex e Devin respeitem as mesmas regras de arquitetura e de verificação.

#### Acceptance Criteria
1. The Forge shall incluir nas instruções de projeto lidas por cada host suportado as invariantes, com escopo explícito entre o core (`src/theforge`) e os adapters (`adapters/`): runtime do core stdlib-only (Python >= 3.11, dependências só em extras de desenvolvimento); integração do core com providers só via Forge Protocol, sem import de especialistas no core (os adapters, distribuídos à parte e instalados no interpretador de cada especialista, são o único lugar que os importa); routing determinístico, em que ambiguidade vira `ambiguous` e nunca um chute, sem LLM no core; nenhum sucesso sem `ExecutionResult` válido; tudo que o core persiste passa por `security.redact` (dados escritos pelo provider no diretório de trabalho do run ficam fora dessa regra) e credenciais nunca chegam ao ambiente dos providers; nenhum conhecimento de domínio no core; contratos `theforge/<Name>/v1` com regeneração dos schemas publicados ao mudar um contrato; e os comandos de setup de desenvolvimento, teste, lint e tipos.
2. The Forge shall manter o texto das invariantes idêntico entre as instruções de todos os hosts.
3. If as invariantes faltam nas instruções de algum host suportado ou divergem entre hosts, the suíte de testes offline shall falhar identificando o arquivo de instruções e a invariante ausente ou divergente.
4. When o comando de setup de desenvolvimento, de teste, de lint, de tipos ou de regeneração de schemas documentado nas invariantes muda, The Forge shall atualizá-lo nas instruções de todos os hosts na mesma mudança.

### Requirement 4: Instruções de host curtas e sem perda de comportamento
**Objective:** As a mantenedor, I want que as instruções sempre carregadas pelos hosts contenham só regras persistentes curtas, so that cada sessão de agente gaste menos contexto sem perder regras.

#### Acceptance Criteria
1. The Forge shall reduzir o CLAUDE.md às invariantes e a regras persistentes curtas, movendo os detalhes de workflow Kiro redundantes para skills ou para documentação versionada.
2. The Forge shall consolidar o AGENTS.md em um único documento sem seções duplicadas, mantendo as instruções específicas de cada host que o lê.
3. The Forge shall definir um orçamento de tamanho documentado para o CLAUDE.md e para o AGENTS.md.
4. If o CLAUDE.md ou o AGENTS.md excede seu orçamento de tamanho, the suíte de testes offline shall falhar identificando o arquivo, o tamanho e o orçamento.
5. The Forge shall registrar, para cada regra removida do CLAUDE.md ou do AGENTS.md, o local versionado onde a regra continua disponível.
6. If uma regra registrada como movida não está presente no local versionado indicado, the suíte de testes offline shall falhar identificando a regra e o local.
7. The Forge shall manter nas instruções de cada host a indicação de onde encontrar o workflow Kiro, a regra de idioma das specs e o local das skills daquele host.
8. If um comando Kiro exclusivo de um host é coberto por uma skill equivalente do mesmo host, The Forge shall remover o comando duplicado e documentar a correspondência do comando antigo para a skill.

### Requirement 5: Proposta de fonte canônica e política de hooks
**Objective:** As a mantenedor, I want uma decisão registrada sobre a fonte canônica dos assets agentic e sobre empacotá-los como plugin, so that a próxima evolução seja planejada com custo e benefício conhecidos, sem migração prematura.

#### Acceptance Criteria
1. The Forge shall registrar em um ADR a proposta de fonte canônica dos assets agentic e de empacotamento como plugin, com as alternativas avaliadas, o critério de decisão, o custo de migração e o caminho recomendado.
2. The Forge shall manter o runtime `theforge` independente dos assets agentic em qualquer alternativa proposta, sem dependência de runtime nova e sem que o pacote publicado inclua ou exija esses assets.
3. The Forge shall entregar a proposta sem executar nenhuma migração automática dos assets para a fonte canônica ou para plugin.
4. The Forge shall registrar na proposta o tratamento dos assets locais não versionados, incluindo os arquivos de steering, sem torná-los obrigatórios para o repositório versionado.
5. Where hooks são adicionados ao workflow de desenvolvimento, The Forge shall restringi-los a checagens focadas e determinísticas (lint focado nos arquivos alterados, testes relevantes à mudança, paridade de schemas, paridade de assets agentic) e nunca executar a suíte completa a cada edição.
6. The Forge shall documentar a política de hooks junto da proposta de fonte canônica.

### Requirement 6: Higiene da raiz do repositório
**Objective:** As a mantenedor, I want que a raiz do repositório não acumule arquivos acidentais, so that agentes e pessoas não confundam artefatos soltos com arquivos do projeto.

#### Acceptance Criteria
1. The Forge shall remover da raiz do repositório os arquivos acidentais criados por redirecionamento de shell, como `(3`, `dict[str` e `tuple[str`.
2. If a raiz do repositório contém uma entrada cujo nome tem caracteres fora do padrão de nomes do projeto, the suíte de testes offline shall falhar identificando a entrada.

### Requirement 7: Documentação consolidada do ciclo
**Objective:** As a mantenedor e autor de provider, I want documentação coerente com o comportamento final do Cycle 2, so that ninguém precise ler as specs para entender o produto.

#### Acceptance Criteria
1. When o comportamento de protocolo, segurança, CLI, contexto ou routing muda no Cycle 2, The Forge shall refletir a mudança no README, na arquitetura, no protocolo, no guia de autoria de provider, na segurança e na CLI, preservando o conteúdo técnico entregue pelas specs anteriores.
2. The Forge shall apresentar no README o estado do ciclo e um índice que alcança todo documento de `docs/` e o índice de ADRs.
3. The Forge shall documentar `theforge` como nome canônico da CLI e `forge` como alias de conveniência no README e na documentação da CLI, e usar `theforge` em todos os exemplos de comando.
4. The Forge shall apresentar a mesma tabela de exit codes no README e na documentação da CLI, cobrindo todo exit code que a CLI emite.
5. If um link relativo da documentação versionada aponta para um arquivo inexistente ou para assets locais não versionados, the suíte de testes offline shall falhar identificando o documento e o link.
6. If a tabela de exit codes do README diverge da documentação da CLI ou omite um exit code emitido pela CLI, the suíte de testes offline shall falhar identificando o exit code.
7. When um contrato muda, The Forge shall regenerar os schemas publicados e manter a verificação de paridade de schemas passando.

### Requirement 8: ADRs do ciclo
**Objective:** As a mantenedor, I want que as decisões arquiteturais do Cycle 2 estejam registradas e localizáveis, so that elas sejam rastreáveis no próximo ciclo.

#### Acceptance Criteria
1. The Forge shall ter ADRs registrados para: ownership dos adapters reais, taxonomia de capabilities, matriz de suporte de CI, integridade de contexto, local do cache do registry, modelo de execução multi-provider, fonte canônica de assets agentic e modelo de policy.
2. The Forge shall manter um índice de ADRs que lista cada ADR com número, título e status, e que mapeia cada decisão exigida no critério 1 ao ADR que a registra.
3. If um ADR exigido no critério 1 está ausente, um arquivo de ADR não aparece no índice, dois ADRs compartilham um número ou um ADR não declara status, the suíte de testes offline shall falhar identificando o ADR.
4. If um ADR exigido pertence a uma spec anterior e está ausente no momento da consolidação, The Forge shall reportar a ausência como bloqueio da spec dona em vez de redigir o ADR por ela.

### Requirement 9: Relatório final do Cycle 2
**Objective:** As a mantenedor, I want um relatório final do ciclo com resultados verificáveis, so that o próximo ciclo comece de um retrato honesto do que foi entregue e do que ficou para trás.

#### Acceptance Criteria
1. The Forge shall publicar na documentação versionada um relatório final do Cycle 2 com as seções: implementado, mudanças de arquitetura, integração real Spark/API, melhorias de contexto e economy, hardening de segurança, CI, prova cross-forge, resultados medidos, limitações, adiamentos intencionais e próximo ciclo recomendado.
2. The Forge shall indicar, para cada resultado medido do relatório, a origem da medição (comando, workflow ou documento e data) ou marcá-lo explicitamente como não medido.
3. If uma prova ou medição com Forges reais não pôde ser executada no ambiente da consolidação, The Forge shall registrar no relatório o motivo e o substituto offline usado, sem apresentá-la como executada.
4. The Forge shall manter o relatório legível sem acesso a assets locais não versionados, sem links para `.kiro/`.
5. If o relatório final omite uma das seções exigidas no critério 1, the suíte de testes offline shall falhar identificando a seção ausente.

### Requirement 10: Fronteira com o runtime e com assets locais
**Objective:** As a mantenedor, I want que o trabalho de manutenção agentic não altere o produto nem dependa do ambiente local de quem o executa, so that o gate de CI continue determinístico e o runtime continue stdlib-only.

#### Acceptance Criteria
1. The Forge shall entregar esta spec sem alterar o comportamento do runtime `theforge`, sem dependência de runtime nova e sem mudar contratos publicados.
2. The Forge shall executar todas as verificações automatizadas desta spec de forma determinística, offline e com o mesmo resultado em Linux e Windows.
3. While assets locais não versionados estão presentes na cópia de trabalho, the suíte de testes offline shall produzir o mesmo resultado que produziria sem eles.
4. The Forge shall manter os assets locais não versionados fora do git, sem que nenhuma verificação, documento versionado ou instrução de host dependa deles.
