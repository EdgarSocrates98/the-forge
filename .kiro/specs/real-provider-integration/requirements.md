# Requirements Document

## Project Description (Input)
Wave B do Cycle 2 de The Forge. Quem tem o problema: usuários de dados/APIs e mantenedores de The Forge, que hoje só conseguem provar a integração do control plane contra providers fixture. Situação atual: Spark Forge (`spark-forge-aws` 0.5.0) e API Forge (`apiforge` 0.1.0) reais não falam Forge Protocol (Spark: JSON em stdout, erros texto/exit 2, 133 tools via `call_tool`, `collect_*` usa AWS, escreve `.sparkforge/` no cwd; API: Python >=3.12,<3.13, matriz pública de capabilities com state/risk, erros `AF-*` em stderr, escreve `.apiforge/economy.jsonl` no cwd). O que deve mudar: describe/health/execute reais de ambos os Forges via Forge Protocol, capabilities read-only/offline por padrão, conformance offline + integração, matriz de compatibilidade, regras de versionamento, taxonomia de capabilities e ADR de ownership de adapters. Ver `brief.md` (requisitos semente 7–10 de `cycle2-reality-hardening`).

## Introduction

A Wave A (`cycle2-reality-hardening`, implementada) endureceu o core: integridade de resultados, verificação de `producer`, limites de manifest, trust/cache/identidade, ambiente mínimo do provider, cwd controlado e policy/risk. A integração, porém, continua provada só contra providers fixture (`echo-forge`, `fixture-spark`, `fixture-api`). Spark Forge e API Forge reais não falam Forge Protocol, e o workflow `real-providers.yml` já faz checkout dos repositórios irmãos sem que exista um contrato que diga aos testes onde eles estão nem como executá-los.

Esta spec entrega a Wave B: os dois Forges reais passam a ser descobertos, verificados e executados via Forge Protocol, expondo por padrão só capabilities read-only e offline; a conformance passa a ter um nível offline e um nível de integração; versionamento e compatibilidade ficam explícitos e testados; e o catálogo de capabilities ganha uma taxonomia validada. Escolhas de mecanismo (onde ficam os adapters, como a superfície nativa é traduzida, estrutura de arquivos) pertencem ao design e aos ADRs.

## Boundary Context
- **In scope**: describe/health/execute reais de Spark Forge e API Forge via Forge Protocol; exposição padrão restrita a capabilities read-only/offline; tradução de erros nativos em respostas de protocolo; contenção de arquivos auxiliares nativos fora do workspace do usuário; resultados grandes por referência; conformance offline e de integração, incluindo o contrato de ambiente que diz aos testes onde estão os Forges reais; regras de versionamento, validação de versão declarada e matriz de compatibilidade; taxonomia de capabilities com validação, sobreposição, aliases e depreciação; ADRs de local dos adapters e de taxonomia.
- **Out of scope**: lógica, regras ou conhecimento de domínio de Spark/OpenAPI no core; routing interno, grafo de impacto e workspace do API Forge; capabilities que exigem credenciais ou rede (`collect_*` do Spark Forge, mutação externa do API Forge); tiers de contexto, sinais git, cache de fingerprints, economy, telemetria e baseline de performance (`context-intelligence-v2`); `ExecutionPlan`, handoff entre providers, prova cross-forge, taxonomia formal de códigos `FORGE-*`, explain/replay (`cross-forge-foundation`); instalação automática de Forges; sandbox de SO.
- **Adjacent expectations**:
  - Os invariantes da Wave A (integridade de resultado, `producer`, limites de manifest, trust, ambiente mínimo, cwd controlado, policy) valem para os Forges reais sem exceção; esta spec não os afrouxa.
  - Mudanças nos repositórios irmãos, se o ADR de local dos adapters optar por elas, precisam ser mínimas e aceitas pelo dono de cada repositório.
  - `cross-forge-foundation` consome as capabilities reais e os resultados produzidos aqui; esta spec não define composição entre providers.
  - Novos códigos de erro seguem as famílias `FORGE-*` existentes; a taxonomia formal de códigos é de `cross-forge-foundation`.

## Requirements

### Requirement 1: Integração real com Spark Forge
**Objective:** As a usuário de dados, I want que The Forge descubra, verifique e execute o Spark Forge real via Forge Protocol, so that tarefas de engenharia de dados sejam delegadas ao especialista real e não a fixtures.

#### Acceptance Criteria
1. When o Spark Forge real está instalado e registrado como provider, The Forge shall obter seu manifest via describe com capabilities derivadas da superfície real de tools do Spark Forge.
2. When health é solicitado ao Spark Forge registrado, The Forge shall obter o estado de saúde do Spark Forge real sem acesso à rede e sem credenciais.
3. When uma tarefa roteada ao Spark Forge é executada, The Forge shall receber um `ExecutionResult` válido cujas evidências e findings são rastreáveis aos findings nativos do Spark Forge.
4. If o Spark Forge reporta erro nativo durante uma operação, The Forge shall recebê-lo como resposta de protocolo estruturada (recusa ou erro com código e detalhe) em vez de falha de transporte genérica.
5. The The Forge shall expor do Spark Forge, por padrão, apenas capabilities read-only e offline; tools que exigem credenciais AWS ou rede shall não ser executáveis por padrão e shall constar como não expostas nas limitações do manifest.
6. While o Spark Forge executa, The Forge shall garantir que estado e journal nativos do Spark Forge não sejam gravados no workspace do usuário fora do diretório de trabalho do run.
7. If a saída nativa do Spark Forge excederia o limite de tamanho do protocolo, The Forge shall receber um resultado parcial com referências a artifacts em vez de falha por tamanho.
8. If o Spark Forge não está instalado ou não está acessível, The Forge shall reportar o provider como ausente ou indisponível com mensagem acionável e sem erro interno.
9. The The Forge shall não reimplementar regras, análises ou conhecimento de domínio do Spark Forge.

### Requirement 2: Integração real com API Forge
**Objective:** As a engenheiro de APIs, I want que The Forge descubra, verifique e execute o API Forge real via Forge Protocol, so that tarefas de API e serviços sejam delegadas ao especialista real.

#### Acceptance Criteria
1. When o API Forge real está instalado em seu próprio interpretador e registrado como provider, The Forge shall obter seu manifest via describe com capabilities derivadas da matriz pública de capabilities do API Forge.
2. When health é solicitado ao API Forge registrado, The Forge shall obter o estado de saúde do API Forge real sem acesso à rede e sem credenciais.
3. When uma tarefa roteada ao API Forge é executada, The Forge shall receber um `ExecutionResult` válido cujas evidências referenciam a evidência nativa do API Forge sem remodelar seus conceitos internos de routing, grafo ou workspace.
4. If o API Forge reporta erro nativo (`AF-*`) ou recusa de governança, The Forge shall recebê-lo como resposta de protocolo estruturada que preserva o código nativo.
5. The The Forge shall expor do API Forge, por padrão, apenas capabilities com estado `supported` ou `heuristic` e risco `read_only`; capabilities `unsupported`, que exigem rede ou credenciais, ou de mutação externa shall não ser executáveis.
6. While o API Forge executa, The Forge shall garantir que arquivos auxiliares do API Forge (ledger de economy, cache) não sejam gravados no workspace do usuário fora do diretório de trabalho do run.
7. If o interpretador exigido pelo API Forge não está disponível, The Forge shall reportar o provider como indisponível com o motivo explícito (interpretador ausente ou versão incompatível).
8. If a saída nativa do API Forge excederia o limite de tamanho do protocolo, The Forge shall receber um resultado parcial com referências a artifacts em vez de falha por tamanho.
9. The The Forge shall não duplicar conceitos já existentes no API Forge (routing interno, impacto em grafo, workspace, evidência nativa).

### Requirement 3: Conformance offline e de integração
**Objective:** As a mantenedor, I want níveis separados de conformance e um contrato de ambiente explícito para os Forges reais, so that a compatibilidade com providers reais seja verificável sem tornar a suíte principal dependente deles.

#### Acceptance Criteria
1. The The Forge shall oferecer conformance offline dos adapters dos Forges reais, executável sem rede, sem AWS, sem credenciais e sem os repositórios irmãos, como parte da suíte principal.
2. The The Forge shall oferecer conformance de integração, executável contra Spark Forge e API Forge reais e selecionável separadamente da suíte principal.
3. The The Forge shall documentar o contrato de ambiente da conformance de integração: quais variáveis indicam o interpretador de cada Forge real e qual variável torna a ausência de pré-requisitos uma falha em vez de um skip.
4. If o interpretador de um Forge real não está configurado, não existe ou não tem o Forge instalado, The Forge shall pular a conformance de integração daquele Forge com motivo explícito, sem falhar a suíte principal.
5. Where a execução declara que os Forges reais são obrigatórios, The Forge shall falhar a conformance de integração quando algum pré-requisito estiver ausente, em vez de pular.
6. The The Forge shall cobrir na conformance de integração, para cada Forge real: describe, health, execute de ao menos uma capability exposta, provider ausente e divergência de versão.
7. When a conformance de integração roda no workflow agendado de providers reais, The Forge shall executá-la contra os dois Forges reais e tornar falhas visíveis no resultado do workflow, sem bloquear pull requests.

### Requirement 4: Versionamento e compatibilidade
**Objective:** As a mantenedor, I want regras explícitas de versionamento e uma matriz de compatibilidade testada, so that a evolução de The Forge, do protocolo e dos adapters não quebre integrações em silêncio.

#### Acceptance Criteria
1. The The Forge shall documentar separadamente as regras de versão de pacote, versão de protocolo, versão de schema de contrato, versão de provider e evolução de capability.
2. The The Forge shall manter uma matriz de compatibilidade entre a versão de The Forge, a versão maior do Forge Protocol, as versões dos adapters de Spark Forge e API Forge e as versões dos Forges especialistas suportadas, com janela de suporte documentada.
3. The The Forge shall verificar por teste que a matriz de compatibilidade cobre a versão atual de The Forge e as versões atuais dos adapters.
4. If um provider declara versão que não segue versionamento semântico, The Forge shall marcar o provider como inválido, excluí-lo do routing e reportar a versão malformada.
5. If um adapter é executado contra uma versão do Forge especialista fora da janela suportada, The Forge shall reportar o provider como degradado ou indisponível com a versão encontrada e a janela esperada.
6. The The Forge shall registrar ADR sobre o local dos adapters (dentro de The Forge, nativo em cada Forge ou pacote separado) avaliando acoplamento, independência de release, compatibilidade retroativa, ownership, instalação, segurança, testes e version skew.

### Requirement 5: Taxonomia de capabilities
**Objective:** As a autor de provider, I want regras claras para nomear e evoluir capabilities, so that o catálogo cresça sem caos e sem capabilities genéricas ou específicas demais.

#### Acceptance Criteria
1. The The Forge shall definir regras documentadas de namespace, subject, granularidade, ações, sobreposição entre providers, versionamento, depreciação e aliases de capabilities.
2. If um manifest declara capability ou ação que viola as regras de formato da taxonomia, The Forge shall rejeitar a capability com aviso e marcar o provider como inválido quando nenhuma capability restar.
3. The The Forge shall derivar o conjunto inicial de capabilities de Spark Forge e API Forge da auditoria das superfícies reais, registrando a correspondência entre cada capability e a superfície nativa de origem.
4. When dois ou mais providers roteáveis declaram a mesma capability, The Forge shall resolver a escolha pelas regras de routing existentes e registrar a sobreposição e o critério de desempate na decisão de routing.
5. Where um manifest declara aliases ou capabilities depreciadas, The Forge shall resolver um pedido por alias para a capability canônica de forma determinística e avisar sobre a depreciação na decisão de routing e na listagem de capabilities.
6. If um manifest declara alias que colide com outro alias ou com o ID de uma capability do mesmo manifest, The Forge shall marcar o provider como inválido.
7. The The Forge shall registrar ADR de taxonomia de capabilities.
