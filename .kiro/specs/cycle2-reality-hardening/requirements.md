# Requirements Document

## Project Description (Input)

**Fonte completa:** `prompt_evo_passo1.md` (THE FORGER — CYCLE 2: Reality Validation, Hardening, Real Forge Integration, Context Intelligence & Cross-Forge Foundation).

### Quem tem o problema
Mantenedores e usuários de The Forge (control plane WHO/WHEN/HOW) que precisam coordenar os Forges especialistas reais — Spark Forge (`spark-forge-aws`) e API Forge (`api-forge`) — a partir de um núcleo determinístico, stdlib-only e governado.

### Situação atual
- Cycle 1 entregue: CLI, Registry, Routing determinístico, Context Broker por globs + budget em bytes, Forge Protocol v1 (subprocess + JSON), Runs/receipts, Security (`redact`, `safe_env`, trust model).
- Integração provada apenas contra fixtures (`echo-forge`, `fixture-spark`, `fixture-api`), não contra os Forges reais.
- Lacunas conhecidas: validação semântica fraca de contratos, cache do registry envenenável em `project/.forge/registry`, TOCTOU entre hash do ContextPack e leitura pelo provider, `operation_class` apenas declarativo, score de routing vulnerável a spam de sinais, economy quase cosmética, sem CI, contratos reservados não ativados, drift possível entre mirrors agentic e CLAUDE.md inflado.

### O que deve mudar
Transformar "Forge Protocol + deterministic local core" em base comprovada contra Spark Forge REAL + API Forge REAL, sem overengineering, em waves: A — Hardening; B — Reality; C — Context Intelligence v2; D — Cross-Forge Foundation; E — Agentic Maintainability.

### Restrições invariantes
Runtime stdlib-only (Python ≥ 3.11, 0 deps runtime); integração só via Forge Protocol; routing determinístico (ambíguo ≠ chute; sem LLM obrigatório); nenhum sucesso sem `ExecutionResult` válido; tudo persistido passa por `security.redact`; sem forge-kernel; sem conhecimento de domínio no core; nada de web UI, server, database, orchestrator distribuído, remote registry ou installer automático.

## Introduction

O Cycle 2 de The Forge endurece o core entregue no Cycle 1 e o prova contra os dois Forges especialistas reais. A auditoria inicial (2026-10-02) confirmou, com evidência no código:

- **Core (`the-forger` 0.1.0, `forge/v1`)**: 11 contratos ativos; validação semântica ausente para unicidade de IDs de evidence/finding, resolução de `evidence_ids`, contenção de paths de artifact, formato de hash e consistência receipt↔result; `execute` chamado sem verificar `ops` do manifest; `producer` não validado em describe/health; `trusted` e `local` diferem apenas no desempate de routing; cache do registry auto-hasheado dentro do workspace; describe/health herdam o cwd do chamador; routing sem teto de sinais e confiança binária; contexto sem git, sem cache e sem revalidação pós-execução; sem CI; contratos reservados (`ExecutionPlan`, `VerificationResult`, `RiskAssessment`, `WorkspaceDescriptor`, `GraphNode`/`GraphEdge`, `InstallationPlan`) inexistentes em código; sem `replay`/`--debug`; AGENTS.md sem as invariantes do projeto; `.kiro/steering/` ausente.
- **Spark Forge (`sparkforge-aws` 0.5.0)**: Python ≥ 3.10, deps PyYAML/jsonschema; saída JSON em stdout, erros em texto em stderr com exit 2; 133 tools com dispatcher único e anotações read-only/write; somente `collect_*` usa AWS/rede; estado escrito em `.sparkforge/` no cwd; nenhum suporte a Forge Protocol.
- **API Forge (`apiforge` 0.1.0)**: Python `>=3.12,<3.13`; matriz pública de capabilities (`api.analyze`, `api.next-step`, `database.inspect`, …) com `state` e `risk`; saída JSON em stdout, erros `AF-*` em texto em stderr; escreve `.apiforge/economy.jsonl` no cwd; tokens lidos do ambiente apenas em verbos de rede; nenhum suporte a Forge Protocol.

Os requisitos abaixo descrevem o comportamento observável que o Cycle 2 deve entregar. Escolhas de mecanismo (local dos adapters, formato de cache, estrutura de módulos) pertencem ao design e aos ADRs.

## Boundary Context

- **Decomposição (2026-10-02)**: o escopo original do Cycle 2 foi dividido por wave em `.kiro/steering/roadmap.md`. Esta spec cobre a **Wave A — Hardening + CI**. Os requisitos originais 7–14 e 16–18 foram movidos como sementes para `real-provider-integration`, `context-intelligence-v2`, `cross-forge-foundation` e `agentic-maintainability` (ver `brief.md` de cada uma).
- **In scope**: invariantes semânticas de contratos; robustez adversarial de protocol, routing, registry/trust/cache e ambiente de provider; fundação de policy/risk; CI e quality gates.
- **Out of scope**: adapters reais e conformance de integração; taxonomia de capabilities; Context Intelligence v2 e economy; contratos multi-provider, explain/replay/taxonomia formal de erros; paridade agentic e consolidação de documentação; tudo listado como fora do Cycle 2 (web UI, server, database, forge-kernel, LLM routing obrigatório, sandbox de SO obrigatório).
- **Adjacent expectations**:
  - Os cenários de routing com tarefas de dados e de API são verificados nesta spec com providers de teste que declaram sinais equivalentes; a prova contra os Forges reais pertence a `real-provider-integration`.
  - Novos códigos de erro introduzidos aqui seguem as famílias `FORGE-*` existentes; a taxonomia formal é consolidada em `cross-forge-foundation`.
  - Policy e `RiskAssessment` definidos aqui são consumidos pelos adapters reais e pelo executor de planos das waves seguintes.
## Requirements

### Requirement 1: Invariantes semânticas de contratos
**Objective:** As a mantenedor de The Forge, I want que todo contrato recebido ou produzido seja validado semanticamente além de tipos, so that estados inválidos nunca sejam aceitos como sucesso.

#### Acceptance Criteria
1. If um `ExecutionResult` contém dois ou mais itens de evidence com o mesmo ID, The Forge shall rejeitar o resultado, registrar o run como falha de provider com código de erro específico e não reportar sucesso.
2. If um `ExecutionResult` contém dois ou mais findings com o mesmo ID, The Forge shall rejeitar o resultado com código de erro específico.
3. If um finding referencia um `evidence_id` inexistente no mesmo resultado, The Forge shall rejeitar o resultado e identificar a referência pendente na mensagem de erro.
4. If um artifact declara caminho absoluto, caminho com componente de travessia ou caminho que resolve fora da raiz controlada do run, The Forge shall rejeitar o resultado sem acessar o caminho.
5. If qualquer campo de hash declarado como SHA-256 não corresponde ao formato de 64 caracteres hexadecimais minúsculos, The Forge shall rejeitar o contrato que o contém.
6. If o `producer` (id ou versão) de um resultado, resposta de describe ou resposta de health diverge do provider registrado que foi invocado, The Forge shall rejeitar a resposta com código de erro de producer.
7. If um `ContextPack` declara `used_bytes` maior que `budget_bytes` ou diferente da soma dos bytes dos arquivos listados, The Forge shall rejeitar o pack.
8. If um receipt com status de sucesso não referencia o hash do resultado persistido, The Forge shall tratá-lo como inválido na verificação.
9. If um manifest declara IDs de capability duplicados, ação padrão fora da lista de ações ou capability sem ações, The Forge shall marcar o provider como inválido e excluí-lo do routing.
10. The The Forge shall rejeitar campos desconhecidos em contratos produzidos pelo próprio core e documentar a política de tolerância a campos desconhecidos em contratos vindos de providers.
11. The The Forge shall ter testes que cubram cada invariante deste requisito com ao menos um caso válido e um inválido.

### Requirement 2: Robustez do Forge Protocol contra providers adversariais
**Objective:** As a operador de The Forge, I want que providers maliciosos ou defeituosos não consigam produzir sucesso falso nem degradar o host, so that toda integração seja governada pelo protocolo.

#### Acceptance Criteria
1. If o manifest de um provider não declara a operação `execute`, The Forge shall recusar a execução antes de iniciar o processo e reportar código de erro de operação não suportada.
2. If um provider retorna `request_id`, `protocol`, `kind` ou `op` diferentes do pedido, The Forge shall rejeitar a resposta com código de erro de protocolo.
3. If um provider escreve em stdout além do limite configurado, The Forge shall encerrar o processo e reportar código de erro de tamanho excedido.
4. If um provider escreve em stderr além do limite configurado, The Forge shall truncar o conteúdo retido, aplicar redação e nunca persistir stderr sem redação.
5. If um provider excede o timeout, The Forge shall encerrar o processo e todos os processos filhos que ele criou e reportar código de erro de timeout.
6. If um provider retorna JSON inválido, schema inesperado, status desconhecido, timestamp malformado ou código de saída diferente de zero sem resposta válida, The Forge shall registrar falha de provider e não reportar sucesso.
7. When a negociação de protocolo recebe as listas `[v1]`, `[v1,v2]`, `[v2]`, versão malformada, versão duplicada ou formato desconhecido, The Forge shall selecionar a maior versão maior comum ou marcar o provider como incompatível, de forma determinística e sem erro interno.
8. The The Forge shall manter um provider de teste adversarial que exercite cada ataque listado neste requisito e no Requirement 1, incluindo spam de capabilities.
9. The The Forge shall aplicar testes baseados em propriedades à decodificação de contratos e envelopes, garantindo que nenhuma entrada arbitrária produza erro interno não tratado.

### Requirement 3: Routing determinístico resistente a manipulação
**Objective:** As a usuário de The Forge, I want que o routing permaneça determinístico e não seja vencido por providers que declaram sinais em excesso, so that a escolha do especialista seja justa e explicável.

#### Acceptance Criteria
1. The The Forge shall produzir o mesmo resultado semântico de routing para o mesmo TaskSpec, registry, arquivos e dependências, independentemente da ordem de descoberta de providers e da ordem do sistema de arquivos.
2. If um provider declara keywords duplicadas, centenas de keywords, globs excessivamente amplos ou dependências genéricas, The Forge shall limitar a contribuição de cada tipo de sinal de modo que o volume declarado sozinho não vença o routing.
3. If nenhum candidato atinge o critério mínimo de evidência de sinais ou os dois melhores candidatos empatam, The Forge shall retornar `ambiguous` com os candidatos e não executar nenhum provider.
4. When a tarefa "melhore performance" é submetida sem contexto suficiente e com um provider de dados e um provider de API registrados, The Forge shall retornar `ambiguous`.
5. When a tarefa "Analise este Glue job lento" é submetida em workspace com sinais de dados, The Forge shall selecionar exclusivamente o provider que declara a capability de dados correspondente.
6. When a tarefa "Revise este contrato OpenAPI" é submetida em workspace com sinais de API, The Forge shall selecionar exclusivamente o provider que declara a capability de API correspondente.
7. Where o nível de confiança for estendido além de `high`/`low`, The Forge shall definir para cada nível um critério objetivo documentado e testado.
8. The The Forge shall distinguir capabilities declaradas como `supported`, `heuristic` e `unresolved` no resultado de routing e na explicação, sem tratá-las como equivalentes.
9. When um fallback é aplicado, The Forge shall selecionar apenas providers que suportem a mesma capability e ação solicitada e registrar cada tentativa e motivo.
10. If o provider selecionado está indisponível e nenhum fallback compatível existe, The Forge shall falhar explicitamente com o motivo, sem executar provider incompatível.
11. The The Forge shall manter testes adversariais de routing para keyword spam, gaming de provider, glob amplo, dependência genérica, keyword duplicada, nomes de arquivo comuns, repositório ambíguo e monorepo.

### Requirement 4: Trust, cache do registry e identidade de provider
**Objective:** As a operador de The Forge, I want que o nível de confiança não possa ser escalado e que o cache do registry não possa falsificar capabilities, so that apenas providers autorizados executem com as capabilities que realmente declaram.

#### Acceptance Criteria
1. When um `providers.toml` de projeto declara `trust = trusted` (ou qualquer nível acima de `unverified`), The Forge shall ignorar o valor, registrar o provider como `unverified`, emitir aviso e não executá-lo sem autorização explícita.
2. The The Forge shall documentar a diferença comportamental concreta entre `builtin`, `trusted`, `local`, `unverified` e `blocked`; if `trusted` e `local` não tiverem diferença além de desempate, The Forge shall documentar a intenção futura ou simplificar o modelo.
3. If o cache do registry foi alterado por terceiros de forma que suas capabilities divirjam do manifest real do provider, The Forge shall detectar a divergência, descartar o cache e redescobrir o provider antes de rotear.
4. The The Forge shall armazenar o cache de registry de providers confiáveis em local não gravável pelo conteúdo do projeto analisado e migrar caches existentes sem perda de funcionalidade.
5. When o executável, a versão ou o fingerprint local de um provider muda, The Forge shall invalidar a entrada de cache correspondente.
6. The The Forge shall registrar no receipt a identidade observada do provider (caminho do executável, versão e fingerprint local) e documentar que o hash do manifest não prova identidade.
7. The The Forge shall produzir pesquisa/ADR sobre evolução de identidade de provider (assinatura, publisher, hash de pacote) sem torná-la obrigatória neste ciclo.

### Requirement 5: Ambiente, diretório de trabalho e limites de isolamento
**Objective:** As a operador de The Forge, I want que providers recebam apenas o ambiente mínimo e que os limites reais de isolamento estejam documentados, so that credenciais não vazem e não haja falsa sensação de sandbox.

#### Acceptance Criteria
1. The The Forge shall não repassar ao provider variáveis de credenciais AWS, tokens GitHub, socket de SSH agent, variáveis de credenciais de nuvem, variáveis de proxy com credenciais nem caminhos de arquivos de credenciais.
2. The The Forge shall ter testes que provem a ausência de cada categoria de credencial listada no critério 1 no ambiente recebido pelo provider.
3. The The Forge shall documentar a justificativa de cada variável mantida no ambiente do provider e remover as que não forem necessárias.
4. When The Forge invoca describe, health ou execute, The Forge shall executar o provider em diretório de trabalho controlado por The Forge, não no diretório corrente do chamador.
5. The The Forge shall documentar explicitamente que o diretório de trabalho não é sandbox e que o provider pode acessar o sistema de arquivos com as permissões do usuário.
6. The The Forge shall documentar que `operation_class` é uma declaração do provider e não um mecanismo de enforcement.
7. The The Forge shall produzir pesquisa/ADR de sandbox em nível de SO para Linux, macOS e Windows, sem torná-la dependência do ciclo.

### Requirement 6: Fundação de policy e risco
**Objective:** As a operador de The Forge, I want que cada execução passe por uma decisão de policy baseada no risco declarado, so that operações perigosas não executem silenciosamente.

#### Acceptance Criteria
1. When uma execução é solicitada, The Forge shall produzir uma decisão de policy `allow`, `ask` ou `deny` antes de iniciar o provider e registrá-la no run.
2. The The Forge shall aplicar por padrão: `read_only` → `allow`; mutação local → decisão conforme policy configurada; mutação externa → exigir aprovação explícita; destrutiva → `deny`.
3. If a decisão é `ask` e nenhuma aprovação explícita foi fornecida na invocação, The Forge shall não executar e retornar status de recusa com a ação necessária para desbloquear.
4. If a decisão é `deny`, The Forge shall não executar e registrar o motivo.
5. The The Forge shall produzir um `RiskAssessment` por execução cobrindo ao menos as dimensões read-only, mutação local, leitura externa, mutação externa, destrutiva, credenciais e cross-account, marcando como desconhecida qualquer dimensão não declarada.
6. The The Forge shall registrar no `RiskAssessment` que a classificação deriva da declaração do provider.

### Requirement 7: CI e quality gates
**Objective:** As a mantenedor, I want CI real com gates mecânicos, so that regressões de comportamento, empacotamento, dependências e offline sejam bloqueadas automaticamente.

#### Acceptance Criteria
1. When um pull request é aberto ou atualizado, the CI shall executar testes, lint, checagem de tipos e paridade de schemas em Linux e Windows para Python 3.11, 3.12 e 3.13.
2. The CI shall construir sdist e wheel, instalar o wheel em ambiente novo e executar `theforge doctor`, `theforge init` e uma tarefa com a capability de eco, sem usar instalação editável.
3. The CI shall falhar se o projeto declarar qualquer dependência de runtime.
4. The CI shall verificar metadados do pacote e os entry points `theforge` (canônico) e `forge` (alias).
5. The The Forge shall classificar testes nas categorias unit, contract, integration, e2e, slow, security e real-provider, selecionáveis individualmente.
6. If um teste da suíte offline tenta acessar a rede, the test suite shall falhar esse teste.
7. The CI shall executar testes de providers reais em workflow separado que não bloqueia o CI principal de PR, acionável manualmente ou agendado.
8. The The Forge shall documentar a decisão de custo/benefício de CI em macOS e de suporte a Python 3.14.
