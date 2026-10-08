# Brief: real-provider-integration

## Problem
Spark Forge (`spark-forge-aws` 0.5.0) e API Forge (`apiforge` 0.1.0) reais não falam Forge Protocol; integração provada só contra fixtures.

## Current State
Nenhum adapter real. Spark Forge: JSON em stdout, erros texto/exit 2, 133 tools com dispatcher `call_tool`, `collect_*` usa AWS, escreve `.sparkforge/` no cwd, Python >=3.10, deps PyYAML/jsonschema. API Forge: Python >=3.12,<3.13 (não instalado nesta máquina), matriz pública de capabilities (`api.analyze`, `api.next-step`, …) com state/risk, erros `AF-*` texto em stderr, escreve `.apiforge/economy.jsonl` no cwd.

## Desired Outcome
describe/health/execute reais de ambos os Forges via Forge Protocol, capabilities read-only/offline por padrão, conformance offline + integração, matriz de compatibilidade, taxonomia de capabilities e ADR de ownership de adapters.

## Approach
Recomendação das auditorias: entrada nativa pequena em cada Forge (Spark: shell sobre `adapters.tools.call_tool`; API: shell sobre `apiforge_call`/CapabilityResult) se o dono aceitar; senão adapter separado executando no venv do especialista. Decidir em ADR.

## Scope
- **In**: requisitos semente abaixo (orig. Requirements 7, 8, 9, 10 de `cycle2-reality-hardening`, gerados em 2026-10-02 a partir de `prompt_evo_passo1.md` e auditoria do código).
- **Out**: tudo que pertence a outras specs do roadmap `.kiro/steering/roadmap.md`.

## Boundary Candidates
- Adapter Spark Forge (lado do especialista ou pacote separado)
- Adapter API Forge
- Conformance de integração em The Forge
- Taxonomia/validação de capability IDs no core

## Out of Boundary
- Lógica de domínio (Spark/OpenAPI)
- RoutingPlan/graph/workspace internos do API Forge
- Capabilities com credenciais/rede (`collect_*`, `external.apply`)

## Upstream / Downstream
- **Upstream**: cycle2-reality-hardening (invariantes de contrato, policy, env, cwd, erros de protocolo)
- **Downstream**: cross-forge-foundation

## Existing Spec Touchpoints
- **Extends**: núcleo do Cycle 1 (`src/theforge/`)
- **Adjacent**: demais specs do Cycle 2 em `.kiro/steering/roadmap.md`

## Constraints
Runtime stdlib-only (Python >= 3.11, 0 deps runtime); integração só via Forge Protocol; routing determinístico; nenhum sucesso sem `ExecutionResult` válido; tudo persistido passa por `security.redact`; sem forge-kernel; sem conhecimento de domínio no core.

## Requirements Seed
Requisitos já revisados (EARS) a reaproveitar na fase de requirements; renumerar localmente.

### Seed 7 (orig. Requirement 7): Integração real com Spark Forge
**Objective:** As a usuário de dados, I want que The Forge descubra, verifique e execute o Spark Forge real via Forge Protocol, so that tarefas de engenharia de dados sejam delegadas ao especialista real e não a fixtures.

#### Acceptance Criteria
1. When o Spark Forge real está instalado e registrado, The Forge shall obter seu manifest via describe com capabilities derivadas da superfície real do Spark Forge.
2. When health é solicitado, The Forge shall obter estado de saúde do Spark Forge real sem acesso à rede nem credenciais.
3. When uma tarefa roteada ao Spark Forge é executada, The Forge shall receber um `ExecutionResult` válido com evidências e findings rastreáveis aos findings nativos do Spark Forge.
4. If o Spark Forge reporta erro nativo, The Forge shall convertê-lo em resposta de protocolo estruturada (recusa ou erro com código) em vez de falha de transporte genérica.
5. The The Forge shall expor do Spark Forge, por padrão, apenas capabilities read-only e offline; capabilities que exigem credenciais AWS ou rede shall não ser executáveis por padrão.
6. While o Spark Forge executa, The Forge shall garantir que estado e journal nativos do Spark Forge não sejam gravados no workspace do usuário sem que isso seja declarado e permitido pela policy.
7. If a saída do Spark Forge excederia o limite do protocolo, The Forge shall receber referências a artifacts ou resultado paginado em vez de falha por tamanho.
8. If o Spark Forge não está instalado ou não está acessível, The Forge shall reportá-lo como ausente com mensagem acionável e não falhar com erro interno.
9. The The Forge shall não reimplementar regras, análise ou conhecimento de domínio do Spark Forge.

### Seed 8 (orig. Requirement 8): Integração real com API Forge
**Objective:** As a engenheiro de APIs, I want que The Forge descubra, verifique e execute o API Forge real via Forge Protocol, so that tarefas de API e serviços sejam delegadas ao especialista real.

#### Acceptance Criteria
1. When o API Forge real está instalado em seu próprio interpretador e registrado, The Forge shall obter seu manifest via describe com capabilities derivadas da matriz pública de capabilities do API Forge.
2. When health é solicitado, The Forge shall obter estado de saúde do API Forge real sem acesso à rede nem credenciais.
3. When uma tarefa roteada ao API Forge é executada, The Forge shall receber um `ExecutionResult` válido cujas evidências referenciam a evidência nativa do API Forge sem remodelar seus conceitos internos de routing, grafo ou workspace.
4. If o API Forge reporta erro nativo (`AF-*`) ou recusa de governança, The Forge shall convertê-lo em resposta de protocolo estruturada preservando o código nativo.
5. The The Forge shall expor do API Forge, por padrão, apenas capabilities com estado `supported` ou `heuristic` e risco `read_only`; capabilities `unsupported` ou de mutação externa shall não ser executáveis.
6. While o API Forge executa, The Forge shall garantir que arquivos auxiliares do API Forge (ledger de economy, cache) não sejam gravados no workspace do usuário sem declaração e permissão de policy.
7. If o interpretador exigido pelo API Forge não está disponível, The Forge shall reportar o provider como indisponível com motivo explícito.
8. The The Forge shall não duplicar conceitos já existentes no API Forge (routing interno, graph impact, workspace, evidence nativa).

### Seed 9 (orig. Requirement 9): Conformance, compatibilidade e versionamento
**Objective:** As a mantenedor, I want níveis separados de conformance e regras explícitas de versionamento, so that a compatibilidade com providers reais seja verificável e a evolução não quebre integrações.

#### Acceptance Criteria
1. The The Forge shall oferecer conformance offline, executável sem rede, AWS, credenciais ou repositórios irmãos, e conformance de integração, executável contra Spark Forge e API Forge reais.
2. When os repositórios irmãos ou seus interpretadores não estão disponíveis, The Forge shall pular a conformance de integração com motivo explícito, sem falhar a suíte principal.
3. The The Forge shall cobrir em conformance de integração: describe, health, execute, ausência do provider e divergência de versão (version skew).
4. The The Forge shall documentar separadamente regras de versão de pacote, versão de protocolo, versão de schema de contrato, versão de provider e evolução de capability.
5. The The Forge shall manter matriz de compatibilidade testada entre versão de The Forge, versão maior do Forge Protocol e versões dos adapters de Spark Forge e API Forge, com janela de suporte documentada.
6. The The Forge shall validar a versão declarada pelo provider segundo versionamento semântico e reportar versões malformadas.
7. The The Forge shall registrar ADR sobre local dos adapters (dentro de The Forge, nativo no Forge ou pacote separado) avaliando acoplamento, independência de release, compatibilidade retroativa, ownership, instalação, segurança, testes e version skew.

### Seed 10 (orig. Requirement 10): Taxonomia de capabilities
**Objective:** As a autor de provider, I want regras claras para nomear e evoluir capabilities, so that o catálogo cresça sem caos e sem capabilities genéricas ou específicas demais.

#### Acceptance Criteria
1. The The Forge shall definir regras documentadas de namespace, subject, granularidade, ações, sobreposição entre providers, versionamento, depreciação e aliases de capabilities.
2. If um manifest declara capability que viola as regras de formato da taxonomia, The Forge shall marcar o provider como inválido ou a capability como rejeitada, com aviso.
3. The The Forge shall derivar o conjunto inicial de capabilities de Spark Forge e API Forge da auditoria das superfícies reais, não de lista inventada.
4. When dois providers declaram a mesma capability, The Forge shall resolver a escolha pelas regras de routing e explicar a sobreposição.
5. Where aliases ou capabilities depreciadas são declaradas, The Forge shall resolvê-las de forma determinística e avisar sobre a depreciação.
6. The The Forge shall registrar ADR de taxonomia de capabilities.
