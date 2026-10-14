# SUPER PROMPT — THE FORGE
## Homologação de Integração, Interoperabilidade e Certificação E2E do Ecossistema

**Programa:** The Forge — Ecosystem Integration Certification  
**Versão:** 1.0  
**Escopo:** 9 repositórios oficiais  
**Modo:** Audit → Plan → Implement → Validate → Certify  
**Prioridade:** P0 — Foundation for Ecosystem Maturity  
**Idioma:** Português brasileiro para documentação operacional; contratos e identificadores técnicos seguem as convenções existentes.

---

# 0. MISSÃO

Você atuará como uma equipe sênior multidisciplinar de arquitetura, engenharia de software, engenharia agentic, QA, segurança, DevEx, platform engineering e SRE.

Sua missão é realizar uma **homologação completa, profunda e baseada em evidências da integração entre os nove repositórios do ecossistema The Forge**.

A homologação deve verificar não somente que os projetos funcionam individualmente, mas que conseguem interoperar por meio de contratos explícitos, capacidades negociáveis, protocolos compatíveis e orquestração segura.

Você deve:

1. Auditar as branches `main` dos nove repositórios.
2. Identificar implementações reais, documentação desatualizada, funcionalidades incompletas e divergências entre contratos.
3. Verificar a independência funcional e arquitetural de cada Forja.
4. Validar a interoperabilidade entre The Forge e todas as Forjas especialistas.
5. Validar Forge CLI e Forge Portal como interfaces opcionais.
6. Verificar descoberta, registro, roteamento e negociação de capacidades.
7. Homologar skills, agents, subagents, coordenadores e ferramentas MCP.
8. Validar integração com Claude Code, Codex, Devin e Copilot, dentro das capacidades efetivamente disponíveis.
9. Executar testes reais de instalação, atualização, reinstalação, reparação e desinstalação.
10. Construir e executar cenários E2E envolvendo duas ou mais Forjas.
11. Verificar segurança, rastreabilidade, governança, observabilidade e economia de contexto.
12. Implementar correções necessárias, respeitando os limites de cada repositório.
13. Construir uma suíte permanente de certificação de integração.
14. Produzir relatório técnico detalhado e evidências reproduzíveis.
15. Determinar objetivamente se o ecossistema pode ser considerado homologado.

**Princípio fundamental: uma homologação não é uma declaração de sucesso. É uma demonstração reproduzível de conformidade.**

Nunca declare uma funcionalidade homologada apenas porque existe documentação, um teste mockado ou um comando que retorna exit code zero.

## 0.1 CONTRATO DE EXECUÇÃO, CUSTO E PRIORIDADE

Este documento é o contrato operacional da homologação. O executor deve trabalhar
primeiro sobre os gaps e critérios deste prompt, mantendo rastreabilidade entre
requisito, mudança, teste, evidência e PR. Não abrir frentes fora dos nove
repositórios sem justificativa registrada.

### Ordem obrigatória de custo

1. Descoberta estática e contratos locais.
2. Testes focados no caminho alterado.
3. Smoke de integração real, somente com os repositórios envolvidos.
4. Matriz completa, cenários caros e testes cross-cloud apenas em execução
   manual/nightly ou quando um gate obrigatório exigir.

Uma suíte completa não deve rodar três vezes em cada PR por causa de uma mudança
de documentação, instalador ou workflow. Matrizes repetidas precisam de motivo,
limite de tempo, artefato de evidência e resultado explícito. Cancelar execução
duplicada é permitido quando seu SHA ficou obsoleto; registrar o cancelamento e
nunca tratá-lo como `PASS`.

Todo relatório deve separar `PASS`, `FAIL`, `BLOCKED`, `NOT_TESTED` e `SKIPPED`,
informar duração e custo relativo, e apontar o comando que reproduz o gate. Um
gate rápido de PR pode provar regressão local; ele nunca substitui silenciosamente
um gate completo exigido pela certificação.

### Prioridade desta evolução

Quando a tarefa mencionar `prompt_evo_auditabilidade.md`, tratar este documento
como artefato principal: melhorar critérios, evidências, limites e fluxo antes de
expandir código. A auditoria do `spark-forge-aws` deve ser simplificada por
camadas, preservando provas reais e deslocando somente verificações caras para
nightly/manual. Não remover testes, relaxar thresholds ou trocar execução real por
mock para reduzir custo.

---

# 1. REPOSITÓRIOS OFICIAIS

Auditar obrigatoriamente:

| Repositório | Responsabilidade |
|---|---|
| https://github.com/EdgarSocrates98/the-forge | Control plane, descoberta, roteamento e orquestração |
| https://github.com/EdgarSocrates98/forge-cli | Bootstrap, instalação e configuração |
| https://github.com/EdgarSocrates98/forge-portal | Interface visual e operação |
| https://github.com/EdgarSocrates98/api-forge | Engenharia agentic de APIs |
| https://github.com/EdgarSocrates98/spark-forge-aws | Engenharia de dados em AWS |
| https://github.com/EdgarSocrates98/spark-forge-azure | Engenharia de dados em Azure |
| https://github.com/EdgarSocrates98/platform-forge | Infraestrutura, plataforma e DevOps |
| https://github.com/EdgarSocrates98/forge-doctor-data | Diagnóstico determinístico de dados |
| https://github.com/EdgarSocrates98/forge-doctor-api | Diagnóstico determinístico de APIs |

Não assumir que as implementações seguem perfeitamente a documentação.

**O código executável, os contratos, os testes e o comportamento observado prevalecem sobre declarações nos READMEs.**

Repositórios adicionais só poderão ser propostos se houver justificativa arquitetural comprovada.

Não criar um `forge-contracts`, `forge-kernel`, `forge-lab` ou qualquer novo repositório automaticamente.

Preferir incorporar a certificação ao ecossistema existente, sem criar acoplamento desnecessário.

---

# 2. DIRETRIZES ARQUITETURAIS INEGOCIÁVEIS

## 2.1 Independência absoluta das Forjas

Cada Forja deve funcionar sem:

- The Forge instalado.
- Forge CLI instalado.
- Forge Portal instalado.
- Outras Forjas especialistas instaladas.
- Conectividade externa, quando a operação for declarada offline.
- Provedor de LLM, quando a funcionalidade for declarada determinística.

The Forge não deve se tornar uma dependência obrigatória dos especialistas.

Forge CLI não deve fornecer lógica de domínio aos especialistas.

Forge Portal não deve implementar novamente os motores internos das Forjas.

Os Doctors devem continuar utilizáveis independentemente das respectivas Forjas especialistas.

**Teste obrigatório:** executar cada Forja isoladamente em ambiente limpo, com somente as dependências declaradas.

## 2.2 Responsabilidades

### Forge CLI

Responsável por descoberta de distribuições, instalação, atualização, gerenciamento de versões, configuração inicial e reparação.

Não deve assumir responsabilidade pela lógica de engenharia de dados, APIs ou infraestrutura.

### Forge Portal

Responsável por apresentação, onboarding, exploração, observabilidade e ações autorizadas.

Não deve substituir contratos, inventar estados ou implementar um segundo motor de instalação.

### The Forge

Responsável por descoberta, negociação, seleção de especialistas, coordenação e integração dos resultados.

Não deve duplicar motores especialistas.

### Forjas especialistas

Responsáveis pelas suas capacidades técnicas e contratos operacionais.

### Forge Doctors

Responsáveis por diagnósticos determinísticos e relatórios baseados em evidências.

Podem complementar análises dos especialistas sem depender deles.

## 2.3 Limites de autonomia

Nenhum agente pode receber permissão de executar alterações apenas porque outro agente sugeriu uma ação.

Planejamento não equivale a autorização.

Recomendação não equivale a execução.

Um relatório gerado por LLM não equivale a evidência validada.

Toda alteração deve respeitar as permissões explícitas do operador e os limites estabelecidos pelo ambiente.

---

# 3. ESTRATÉGIA DE EXECUÇÃO

A homologação deve acontecer em oito fases sequenciais, com gates de aprovação.

| Fase | Descrição | Entrega |
|---|---|---|
| H0 | Auditoria e baseline das mains | Inventory & Gap Report |
| H1 | Independência e portabilidade | Independence Certification |
| H2 | Contratos e descoberta | Contract Compatibility Report |
| H3 | CLI, Portal e ciclo de instalação | Developer Experience Certification |
| H4 | Hosts, MCP e agentes | Agentic Interoperability Report |
| H5 | Workflows multi-Forge | E2E Evidence Report |
| H6 | Segurança, resiliência e observabilidade | Operational Readiness Report |
| H7 | Regressão, release e certificação final | Ecosystem Certification Report |

Cada fase deve produzir evidências antes de avançar.

Bloqueios críticos devem ser corrigidos antes de certificar as fases dependentes.

Quando um ambiente externo não estiver disponível, registrar `BLOCKED` ou `NOT_TESTED`, sem apresentar testes simulados como comprovação de integração real.

---

# H0 — AUDITORIA DAS NOVE MAINS

## H0.1 Inventário técnico

Para cada repositório, identificar:

- Commit SHA atual da `main`.
- Branches e PRs relevantes em aberto.
- Linguagens e runtimes suportados.
- Dependências obrigatórias e opcionais.
- CLI e comandos publicados.
- Instaladores, bootstrap e mecanismos portáteis.
- Schemas, manifestos e contratos.
- Skills, agents e subagents disponíveis.
- Implementação MCP, quando existente.
- Integração com hosts.
- Compatibilidade com Forge Portal.
- Compatibilidade com The Forge.
- Testes unitários, integração, contratos e E2E.
- Configuração de CI/CD.
- Releases e versionamento.
- Configurações de segurança.
- Documentação operacional.
- Débitos técnicos com impacto na integração.

Capturar SHAs antes de iniciar alterações.

Nunca misturar resultado de uma versão com outra sem documentar a mudança.

## H0.2 Inspeção de arquitetura

Localizar e avaliar os manifestos reais, incluindo, quando presentes:

- `forge.json`
- `forge.agentic.json`
- `pyproject.toml`
- `package.json`
- `AGENTS.md`
- `CLAUDE.md`
- `.mcp.json`
- Contratos de instalação.
- Contratos de capabilities.
- Contratos de evidence e receipts.
- Adaptadores de providers.
- Manifestos de distribuição.
- Especificações e ADRs.

Não presumir que um caminho de arquivo está presente em todos os repositórios.

Descobrir os arquivos equivalentes existentes.

## H0.3 Classificação de gaps

Classificar cada problema:

**P0 — Critical**

Quebra de segurança, corrupção, perda de dados, dependência circular, operação destrutiva indevida, contrato incompatível que bloqueia integração essencial.

**P1 — High**

Falha de integração real, instalação inconsistente, MCP quebrado, roteamento incorreto, estado divergente entre CLI e Portal.

**P2 — Medium**

Inconsistência funcional, observabilidade insuficiente, documentação incorreta, lacunas de cobertura.

**P3 — Low**

Polish visual, mensagens, organização interna e melhorias não bloqueantes.

Entregar:

`docs/homologation/00-audit-baseline.md`

`docs/homologation/00-gap-register.md`

`docs/homologation/00-compatibility-matrix.md`

---

# H1 — INDEPENDÊNCIA, PORTABILIDADE E DISTRIBUIÇÃO

## H1.1 Instalação isolada

Testar cada Forja em um diretório limpo.

Verificar:

1. Bootstrap independente.
2. Instalação por wheel ou pacote, conforme a arquitetura do projeto.
3. Execução sem checkout original.
4. Registro correto de instalação.
5. Executável acessível pelo PATH.
6. Ausência de imports obrigatórios de outros repositórios Forge.
7. Execução de comandos básicos.
8. Operação offline das funcionalidades declaradas offline.
9. Desinstalação sem apagar arquivos do usuário.
10. Reinstalação sem duplicar assets.

O fato de utilizar contratos compatíveis não deve implicar dependência do código-fonte de outro projeto.

## H1.2 Matriz de sistemas

Homologar prioritariamente:

- Linux.
- Windows.
- macOS, quando houver runner ou ambiente disponível.

Registrar claramente o que foi executado em cada plataforma.

Usar versões suportadas de Python, Node.js e demais ferramentas de acordo com os manifestos reais.

Não exigir que todos os projetos utilizem a mesma versão de Python.

## H1.3 Perfis e escopos

Testar, quando suportados:

- `minimal`
- `recommended`
- `full`
- `project`
- `workspace`
- `user`

Validar semântica real dos perfis, especialmente quais componentes são instalados e por quê.

## H1.4 Gestão de arquivos

Testar:

- Dry-run.
- Idempotência.
- Ledger de propriedade.
- Detecção de drift.
- Reparação.
- Atualização.
- Downgrade suportado.
- Rollback em falha.
- Desinstalação.
- Preservação de arquivos modificados pelo usuário.
- Proteção contra path traversal.
- Proteção contra symlinks e paths externos ao escopo.

**Critério de aceite:** cada Forja permanece operacional, instalável e removível sem The Forge, Forge CLI e Forge Portal.

---

# H2 — CONTRATOS E CAPABILITY NEGOTIATION

Esta fase é essencial.

O ecossistema não deve depender de conhecimento implícito ou de heurísticas frágeis para reconhecer especialistas.

## H2.1 Inventariar contratos existentes

Inspecionar versões reais de contratos como:

- SpecialistAgenticManifest.
- InstallReceipt.
- PortalApi.
- Capabilities.
- Provider registry.
- Evidence.
- Findings.
- RunResult.
- Agent handoff.
- Workspace graph.

Os nomes acima são referências de investigação; verificar seus nomes e schemas efetivos.

Não inventar uma segunda implementação se já existir contrato equivalente.

## H2.2 Validar descoberta

The Forge deve ser capaz de:

1. Descobrir uma Forja registrada.
2. Ler seu manifesto.
3. Identificar suas capabilities.
4. Verificar versões compatíveis.
5. Identificar dependências opcionais.
6. Identificar comandos e ferramentas disponíveis.
7. Detectar componentes indisponíveis.
8. Rejeitar manifests inválidos.
9. Atualizar o registry sem apagar entradas manuais.
10. Explicar a decisão de roteamento.

## H2.3 Negociação

Criar cenários com:

- Provider ausente.
- Provider incompatível.
- Provider desatualizado.
- Capability desconhecida.
- Múltiplos providers válidos.
- Providers com sobreposição de capacidades.
- Provider parcialmente instalado.
- Provider com MCP indisponível.
- Provider funcionando somente em modo standalone.

As decisões precisam ser determinísticas sempre que entradas e políticas forem equivalentes.

Quando houver ambiguidade que não possa ser resolvida com segurança, exigir decisão explícita ou retornar recusa estruturada.

## H2.4 Compatibilidade de versões

Implementar testes de compatibilidade:

- Mesma major version.
- Evolução minor aditiva.
- Evolução patch.
- Campo opcional desconhecido.
- Campo obrigatório ausente.
- Quebra de schema.
- Capability removida.
- Manifesto com versão futura.
- Manifesto com versão antiga.

Usar versionamento semântico onde fizer sentido e houver contrato para isso.

Não aplicar compatibilidade automática a mudanças semanticamente incompatíveis.

## H2.5 Testes de contrato

Construir fixtures de provedores válidos e inválidos.

Implementar testes de consumidor e provedor.

Validar entradas, saídas, schemas, códigos de erro, ordenação, correlação de runs e tratamento de falhas.

Não depender exclusivamente de snapshots de texto.

**Critério de aceite:** The Forge reconhece, valida e seleciona especialistas a partir de capacidades declaradas e contratos verificados, sem hardcode de implementações individuais.

---

# H3 — HOMOLOGAÇÃO FORGE CLI E FORGE PORTAL

Esta fase deve aproveitar as implementações existentes e as evoluções já planejadas para os seis ciclos de CLI e Portal.

Não recriar funcionalidades antes de avaliar a implementação real.

## H3.1 Forge CLI

Testar um usuário iniciando do zero.

Fluxo esperado:

1. Executar Forge CLI.
2. Descobrir Forjas disponíveis.
3. Selecionar uma ou mais.
4. Escolher perfil e escopo.
5. Identificar ferramentas existentes.
6. Exibir dependências ausentes.
7. Planejar instalação.
8. Solicitar aprovação.
9. Instalar e configurar.
10. Validar o resultado.
11. Exibir próximos comandos.
12. Oferecer diagnóstico de instalação.

Validar especialmente:

- Interface interativa.
- Modo não interativo.
- Descoberta de ambiente.
- Seleção de componentes.
- Criação de `.env`.
- Validação de variáveis.
- Preservação de segredos.
- Instalação parcial.
- Falha em uma Forja sem corromper as demais.
- Reinstalação.
- Atualização de versões.
- Rollback.
- Reparo.
- Desinstalação.
- Mensagens em PT-BR.
- Integridade dos receipts.

O CLI deve utilizar interfaces públicas oficiais de cada Forja.

Não incorporar lógica privada de instalação dos especialistas.

### H3.1.1 Instaladores cross-shell e variáveis de ambiente

Auditar e corrigir `install.sh` e `install.ps1` existentes em cada repositório,
sem criar instalador fictício para projeto que não publica esses arquivos.

O contrato mínimo de ambos é:

- detectar Python compatível e explicar o desbloqueio quando ausente ou incompatível;
- ser idempotente, preservar checkout e arquivos do usuário, e registrar receipt;
- instalar em ambiente isolado, publicar launcher e variáveis com prefixo estável
  derivado de `forge_id`;
- no Windows, persistir variáveis no escopo do usuário (`HKCU\\Environment`), sem
  exigir administrador;
- quando `install.sh` rodar no Windows via Git Bash, persistir também um
  `~/.config/forjas/env.sh` compatível com Bash, atualizar `PATH` sem duplicatas e
  imprimir comando de reload; quando executado com `source`, atualizar a sessão
  chamadora;
- no PowerShell, informar que processos pais não podem ser alterados por um
  script filho, permitir dot-source para refresh da sessão e orientar abertura de
  novo terminal;
- nunca gravar tokens, segredos ou conteúdo bruto em variáveis, receipts ou logs.

Aceite exige prova em pelo menos: POSIX shell, PowerShell/Windows e Git Bash em
Windows (quando ambiente disponível), incluindo primeira instalação, repetição,
PATH já contendo launcher, PATH ausente, falha de Python e reload de ambiente.

## H3.2 Forge Portal

Testar as capacidades efetivamente implementadas:

- Catálogo de Forjas.
- Estado de instalação.
- Status de hosts.
- Componentes.
- Skills.
- Agents.
- MCP.
- Documentação.
- Federation.
- Graph Studio.
- Operações.
- Logs.
- Histórico de execução.
- Diagnósticos.
- Segurança de ações.

Não presumir que todas essas telas ou funcionalidades já existem.

Mapear o que está implementado, o que está incompleto e o que pertence ao roadmap futuro.

## H3.3 Consistência CLI ↔ Portal

Executar operações por ambas as interfaces.

Confirmar que:

- A instalação feita pelo CLI aparece corretamente no Portal.
- A atualização feita por um caminho é reconhecida pelo outro.
- O Portal não apresenta instalação inexistente.
- O drift é detectado consistentemente.
- Receipts são preservados.
- Erros são apresentados com causalidade.
- O mesmo estado gera a mesma interpretação operacional.
- O Portal não invoca endpoints mutáveis sem aprovação.

## H3.4 Segurança local

Validar:

- Bind em loopback por padrão.
- Autenticação de sessão.
- CORS e Origin.
- CSRF, quando aplicável.
- Validação de payload.
- Limites de tamanho.
- Proteção contra command injection.
- Proteção contra path traversal.
- Restrições de acesso ao filesystem.
- Não exposição de tokens e secrets.
- Ausência de comandos arbitrários originados pela interface.
- Plano e confirmação obrigatórios para operações mutáveis.

**Critério de aceite:** CLI e Portal podem ser utilizados separadamente, operam sobre os serviços reais das Forjas e apresentam estados consistentes.

---

# H4 — HOSTS, MCP, SKILLS E AGENTES

## H4.1 Hosts suportados

Montar uma matriz de certificação para:

- Claude Code.
- OpenAI Codex.
- Devin.
- GitHub Copilot.

Para cada host, verificar:

- Forma real de instalação.
- Descoberta de skills.
- Descoberta de agents.
- Suporte a subagents.
- MCP.
- Escopos suportados.
- Arquivos de configuração.
- Limites conhecidos.
- Remoção.
- Drift.
- Compatibilidade com multi-repo.

Não presumir equivalência entre hosts.

Se um host não suportar determinada capacidade, registrar a limitação e utilizar o mecanismo nativo compatível, quando existente.

## H4.2 MCP

Para cada servidor MCP disponível:

1. Validar inicialização.
2. Realizar handshake.
3. Listar ferramentas.
4. Validar schemas.
5. Executar ferramenta read-only segura.
6. Validar resposta.
7. Testar timeout.
8. Testar processo encerrado.
9. Testar payload inválido.
10. Verificar bloqueio de operações não permitidas.
11. Verificar instalação em múltiplos hosts.
12. Verificar desinstalação e remoção de configuração gerenciada.

Comprovar que o host consegue iniciar o MCP por meio da configuração instalada.

Não confundir a existência do servidor Python com uma configuração MCP funcional no host.

## H4.3 Agentes e subagents

Auditar:

- Catálogos de agentes.
- Especialização.
- Responsabilidade.
- Ferramentas autorizadas.
- Escopo de atuação.
- Contratos de entrada e saída.
- Políticas de escalonamento.
- Critérios de seleção.
- Tratamento de erros.
- Coordenação.
- Handoffs.
- Contexto fornecido.
- Consumo de tokens.
- Recusas.

Verificar que agentes não se apresentam como especializados em capacidades inexistentes.

## H4.4 Handoff entre agentes

Exemplo:

```text
User Request
    |
    v
The Forge
    |
    v
Capability Discovery
    |
    v
Specialist Selection
    |
    v
Context Resolution
    |
    v
Specialist Agent
    |
    v
Deterministic Tools
    |
    v
Evidence Validation
    |
    v
Handoff Result
    |
    v
The Forge
    |
    v
Final Receipt
```

Verificar que todo handoff transporta apenas o contexto necessário.

Exigir identidade da execução, origem da evidência, versão do provider e estado final.

Não propagar secrets, traces completos ou documentos desnecessários entre especialistas.

## H4.5 Política de contexto

Testar:

- Contexto vazio.
- Contexto mínimo.
- Contexto de workspace.
- Contexto multi-repo.
- Contexto com arquivos grandes.
- Contexto com informações sensíveis.
- Contexto incompatível com a capability.
- Resumos e referências a evidências.
- Limites máximos de payload.
- Deduplicação.

**Critério de aceite:** hosts suportados conseguem consumir os componentes declarados, e os handoffs entre agentes preservam contratos, proveniência e limites de segurança.

---

# H5 — TESTES END-TO-END MULTI-FORGE

Construir um laboratório local de homologação com fixtures e projetos de exemplo.

Priorizar repositórios descartáveis e artefatos sintéticos.

Não utilizar recursos AWS ou Azure de produção.

## Cenário E2E-01 — Fresh Install

**Participantes:** Forge CLI, The Forge, Forge Portal.

Fluxo:

1. Partir de ambiente limpo.
2. Instalar Forge CLI.
3. Instalar The Forge e duas Forjas especialistas.
4. Executar preflight.
5. Registrar providers.
6. Sincronizar capabilities.
7. Configurar host suportado.
8. Abrir o Portal.
9. Verificar catálogo e estado.
10. Executar um diagnóstico seguro.
11. Produzir receipt.

**Aceite:** todo o fluxo é reproduzível, sem configuração manual não documentada.

## Cenário E2E-02 — Data Engineering AWS

**Participantes:** The Forge, Forge Doctor Data, Spark Forge AWS.

Criar um projeto PySpark com:

- Código não otimizado.
- Join potencialmente custoso.
- Problema de qualidade.
- Artefatos de plano Spark.
- Metadata Iceberg.
- Configuração Glue sintética.

Fluxo:

1. The Forge recebe a solicitação.
2. Descobre os especialistas.
3. Forge Doctor Data executa diagnóstico.
4. Spark Forge AWS analisa artefatos.
5. Evidências são correlacionadas.
6. Produzir findings sem duplicação indevida.
7. Gerar recomendações.
8. Validar fontes.
9. Emitir relatório e receipt.

**Aceite:** o resultado distingue evidência, hipótese, recomendação e informação desconhecida.

## Cenário E2E-03 — API Engineering

**Participantes:** The Forge, Forge Doctor API, API Forge.

Criar uma API de teste com:

- Contrato OpenAPI.
- Implementação parcial.
- Erro de compatibilidade.
- Problema de validação.
- Testes automatizados.

Fluxo:

1. Diagnóstico determinístico.
2. Descoberta da capability correta.
3. Planejamento pela API Forge.
4. Proposta de correção.
5. Aplicação somente em sandbox ou worktree autorizado.
6. Execução de testes.
7. Comparação entre estado anterior e posterior.
8. Receipt final.

**Aceite:** nenhuma correção é declarada válida sem execução dos testes correspondentes.

## Cenário E2E-04 — Infraestrutura e Plataforma

**Participantes:** The Forge, Platform Forge, API Forge.

Criar exemplo com:

- API.
- Terraform.
- Docker.
- Kubernetes.
- GitHub Actions.

Solicitação:

"Analise os riscos de infraestrutura e implantação desta API."

Validar:

- Seleção correta de especialistas.
- Análise dos artefatos.
- Correlação API ↔ plataforma.
- Findings com proveniência.
- Ausência de duplicação de responsabilidades.
- Plano de correção.
- Blast radius quando existir evidência suficiente.
- Nenhuma mutação em infraestrutura real.

## Cenário E2E-05 — Engenharia de Dados Azure

**Participantes:** The Forge, Forge Doctor Data, Spark Forge Azure.

Criar fixtures de:

- PySpark.
- Pipeline de dados.
- Configuração Azure.
- Artefatos compatíveis com os serviços realmente suportados pelo projeto.

Validar diagnóstico, descoberta, roteamento e interoperabilidade com o Doctor.

A homologação deve verificar as capacidades implementadas, sem afirmar suporte integral a todos os serviços Azure.

## Cenário E2E-06 — Cross-Cloud

**Participantes:** The Forge, Spark Forge AWS, Spark Forge Azure.

Solicitação:

"Compare riscos e estratégias de migração de um pipeline Spark entre AWS e Azure."

Validar:

- Descoberta de ambas as capacidades.
- Seleção de especialistas.
- Contexto separado por cloud.
- Compatibilidade de findings.
- Identificação explícita de diferenças técnicas.
- Plano de migração sem assumir equivalência entre serviços.
- Síntese com proveniência.

**Aceite:** a coordenação não mistura fatos de AWS e Azure nem inventa compatibilidade entre runtimes.

## Cenário E2E-07 — Multi-Repo Workspace

Criar workspace contendo:

```text
workspace/
├── api/
├── data-aws/
├── data-azure/
├── infrastructure/
└── contracts/
```

Testar:

- Discovery.
- Relações entre repositórios.
- Contexto bounded.
- Escopos.
- Handoff.
- Falhas parciais.
- Isolamento de arquivos.
- Reprodutibilidade.
- Execução independente de cada Forja.

## Cenário E2E-08 — Resiliência

Durante uma execução:

1. Encerrar um provider.
2. Simular timeout.
3. Invalidar temporariamente um manifesto.
4. Remover uma capability.
5. Simular MCP não disponível.
6. Interromper operação antes de confirmação.

Validar:

- Falhas explícitas.
- Ausência de corrupção.
- Estados terminais consistentes.
- Retry somente quando seguro.
- Idempotência.
- Recuperação.
- Relatórios parciais quando cabíveis.
- Ausência de resultados inventados.

## Cenário E2E-09 — Ciclo de vida

Executar:

```text
Install
  → Discover
  → Configure
  → Validate
  → Run
  → Update
  → Detect Drift
  → Repair
  → Revalidate
  → Uninstall
```

Todos os estados devem ser verificáveis.

## Cenário E2E-10 — Independência após remoção do orquestrador

1. Instalar três Forjas.
2. Integrar ao The Forge.
3. Validar interoperabilidade.
4. Desinstalar The Forge.
5. Executar as três Forjas individualmente.
6. Confirmar funcionamento.
7. Verificar integridade dos arquivos e configurações.
8. Confirmar ausência de referências obrigatórias ao orquestrador.

**Este cenário é um gate P0 e não pode ser dispensado.**

---

# H6 — SEGURANÇA, RESILIÊNCIA E OBSERVABILIDADE

## H6.1 Segurança

Realizar testes contra:

- Prompt injection em arquivos e documentação.
- Manifestos maliciosos.
- MCP tools não autorizadas.
- Command injection.
- Path traversal.
- Symlink escape.
- Configurações adulteradas.
- Vazamento de secrets.
- Execução de scripts externos não aprovados.
- Escalonamento indevido entre agents.
- Supply chain de dependências.
- Integridade de artefatos instalados.
- Confusão entre ambiente de teste e produção.

Qualquer entrada externa deve ser considerada não confiável até passar pelos validadores apropriados.

## H6.2 Falhas transacionais

Avaliar:

- Interrupção de instalação.
- Escrita parcial.
- Registro incompleto.
- Falha de permissão.
- Disco cheio.
- Timeout.
- Processo encerrado.
- Corrupção controlada de fixtures.
- Falha após aplicação parcial.
- Reexecução de operação previamente concluída.

Garantir comportamento seguro e recuperação documentada.

## H6.3 Observabilidade federada

Verificar se o ecossistema permite correlacionar:

- Run ID.
- Provider.
- Capability.
- Versão.
- Agent.
- Tool.
- Início e término.
- Estado.
- Duração.
- Findings.
- Evidence.
- Receipt.
- Falhas.
- Consumo de tokens, quando mensurável.
- Custo, quando mensurável.

O Portal deve apresentar apenas métricas efetivamente disponíveis.

Nunca preencher campos desconhecidos com valores fictícios.

## H6.4 Economia de contexto

Comparar estratégias existentes:

- Seleção de contexto.
- Deduplicação.
- Resumos.
- Referências em vez de payloads completos.
- Compressão.
- Caching.
- Lazy loading de skills.
- Handoffs compactos.
- Seleção especializada de ferramentas.

Construir benchmarks com entradas e modelos controlados.

**Não exigir ganhos percentuais arbitrários.**

A aprovação depende de medição reproduzível, ausência de regressões relevantes e documentação do custo/benefício.

---

# H7 — REGRESSÃO, CI E CERTIFICAÇÃO

## H7.1 Suíte permanente

Implementar uma suíte federada de homologação, preferencialmente no The Forge, sem torná-la dependência dos demais repositórios.

Organizar, adaptando ao layout atual:

```text
tests/
└── ecosystem/
    ├── contracts/
    ├── independence/
    ├── installation/
    ├── discovery/
    ├── routing/
    ├── portal/
    ├── hosts/
    ├── mcp/
    ├── agents/
    ├── security/
    ├── resilience/
    └── e2e/

fixtures/
└── ecosystem/
    ├── api/
    ├── spark-aws/
    ├── spark-azure/
    ├── infrastructure/
    └── manifests/

docs/
└── homologation/
    ├── 00-audit-baseline.md
    ├── 00-gap-register.md
    ├── 00-compatibility-matrix.md
    ├── contract-certification.md
    ├── independence-certification.md
    ├── host-compatibility.md
    ├── e2e-evidence.md
    ├── security-report.md
    └── final-certification.md
```

Não impor essa estrutura se já existir uma organização equivalente adequada.

## H7.2 Camadas de testes

**L0 — Static checks**

Lint, tipos, schemas, dependências e consistência de arquivos.

**L1 — Unit**

Comportamento local de componentes.

**L2 — Contract**

Compatibilidade de versões, providers e consumidores.

**L3 — Integration**

Dois ou mais componentes reais trabalhando em conjunto.

**L4 — End-to-end**

Fluxo completo entre múltiplos repositórios.

**L5 — Operational**

Falhas, recuperação, segurança e ciclo de vida.

**L6 — External hosts**

Execução verificada nos hosts suportados e disponíveis.

Mocks são permitidos nas camadas apropriadas, mas não substituem testes reais em L3–L6.

## H7.3 CI/CD

Definir:

- Pipeline rápida para PRs.
- Pipeline de integração entre Forjas.
- Nightly para cenários de maior custo.
- Matriz de sistemas operacionais.
- Testes de compatibilidade entre releases.
- Artefatos de evidência.
- Logs sanitizados.
- Política de retenção.
- Proteção contra regressões.

Priorizar testes locais e gratuitos.

Aplicar separação explícita de pipelines:

- **PR rápido:** lint, contratos, testes focados e smoke real do caminho alterado;
- **push da main:** suíte necessária para regressão direta;
- **nightly/manual:** matrizes completas de Python/OS, wheels duplicados somente
  quando cada OS acrescentar uma prova diferente, auditorias lentas e E2E externos.

Cada job caro deve declarar timeout coerente, motivo de execução e artefato. Não
executar o mesmo gate pesado em dois sistemas operacionais se a segunda execução
não testar comportamento específico daquele sistema. A redução de custo deve ser
demonstrada por duração observada, sem perder cobertura obrigatória.

Clouds e hosts pagos devem ser opcionais, com limites de orçamento e execução explicitamente autorizada.

Se a cota de GitHub Actions estiver indisponível, executar homologação local e registrar a ausência do gate remoto.

Não marcar CI como aprovada sem execução.

---

# 8. CASOS NEGATIVOS OBRIGATÓRIOS

Implementar uma tabela de testes negativos que inclua, no mínimo:

| Falha provocada | Resultado esperado |
|---|---|
| Provider inexistente | Erro explícito e explicado |
| Manifesto inválido | Rejeição sem efeitos colaterais |
| Contrato incompatível | Negociação recusada |
| MCP indisponível | Diagnóstico sem inventar execução |
| Host não instalado | Informação de indisponibilidade |
| Skills duplicadas | Detecção de conflito |
| Agent não autorizado | Execução bloqueada |
| Arquivo do usuário modificado | Preservação |
| Instalação interrompida | Estado recuperável |
| Portal sem sessão válida | Operação bloqueada |
| Path fora do workspace | Acesso recusado |
| Dependência circular | Falha de validação |
| Evidence inconsistente | Resultado não certificado |
| Provider removido | Registry atualizado sem perda de entradas manuais |
| Segredo em logs | Teste falha |
| The Forge desinstalado | Especialistas continuam funcionando |

---

# 9. AGENTES E ORGANIZAÇÃO DA HOMOLOGAÇÃO

Usar os agentes e mecanismos de orquestração existentes quando adequados.

Não criar agentes redundantes sem necessidade.

Papéis necessários:

### Ecosystem Certification Coordinator

Coordena fases, dependências, gates e relatório final.

### Architecture & Contract Auditor

Valida fronteiras arquiteturais, independência e contratos.

### Installation & Portability Auditor

Valida bootstrap, versões, PATH, escopos e lifecycle.

### MCP & Host Compatibility Auditor

Valida ferramentas, servidores, protocolos e hosts.

### Agentic Workflow Auditor

Valida descoberta de agents, delegação e handoffs.

### Security Reviewer

Avalia ameaças, permissões, isolamento e entradas maliciosas.

### E2E Test Engineer

Constrói fixtures, cenários e verificadores reproduzíveis.

### Evidence & Release Certifier

Confirma que toda aprovação possui evidência verificável.

Cada papel deve produzir resultados estruturados e verificáveis.

Se forem usados subagents em paralelo, exigir fronteiras claras de arquivos e responsabilidade.

Não permitir que dois agentes modifiquem simultaneamente os mesmos contratos sem coordenação.

---

# 10. MODELO DE EVIDÊNCIA

Para cada caso de teste, registrar:

```json
{
  "test_id": "E2E-001",
  "description": "Fresh ecosystem installation",
  "status": "PASS",
  "repositories": [
    {
      "name": "the-forge",
      "commit_sha": "<sha-real>"
    }
  ],
  "environment": {
    "os": "<detected>",
    "runtime": "<detected>"
  },
  "execution": {
    "command": "<executed-command>",
    "exit_code": 0
  },
  "evidence": [
    "<relative-path-to-evidence>"
  ],
  "limitations": []
}
```

O exemplo acima representa o formato desejado, não um teste já executado.

Estados aceitos:

- `PASS`
- `FAIL`
- `BLOCKED`
- `NOT_TESTED`
- `NOT_APPLICABLE`

`NOT_APPLICABLE` exige justificativa técnica.

`BLOCKED` deve informar o impedimento e o procedimento para desbloqueio.

Toda evidência deve referenciar o commit e o ambiente exatos.

Evitar salvar secrets, dados pessoais, credenciais e tokens em logs ou artefatos.

---

# 11. POLÍTICA DE CORREÇÕES

Você está autorizado a implementar correções necessárias à homologação em branches de trabalho.

Porém:

1. Não modificar contratos estáveis sem análise de impacto.
2. Não quebrar compatibilidade silenciosamente.
3. Não adicionar dependências obrigatórias entre Forjas.
4. Não introduzir ferramentas externas sem justificativa.
5. Não eliminar testes para obter uma suíte verde.
6. Não alterar thresholds para esconder regressões.
7. Não substituir testes reais por mocks.
8. Não fazer force push.
9. Não alterar histórico Git.
10. Não apagar PRs, Actions ou evidências históricas.
11. Não modificar infraestrutura de produção.
12. Não publicar pacotes nem criar releases automaticamente.
13. Não fazer merge automático na `main`.

Usar branches e PRs separados por repositório quando necessário.

Agrupar correções de acordo com responsabilidade e dependências.

Solicitar aprovação explícita para merges, releases, publicações e ações externas de risco.

---

# 12. CRITÉRIOS DE CERTIFICAÇÃO

## Certified

Somente quando:

- Todos os P0 estão resolvidos.
- Todos os P1 obrigatórios estão resolvidos.
- Os contratos essenciais estão validados.
- As nove Forjas passaram nos testes de independência aplicáveis.
- Descoberta e roteamento reais foram verificados.
- Os cenários E2E obrigatórios passaram.
- Instalação e desinstalação não violam propriedade de arquivos.
- Os limites de segurança foram validados.
- Os testes de regressão executados passaram.
- Existe evidência reproduzível para cada gate obrigatório.

## Conditionally Certified

Permitido somente quando:

- Não existem P0 abertos.
- Os fluxos essenciais estão funcionais.
- Restam limitações não críticas documentadas.
- Os gates ausentes são explicitamente identificados.
- Há um plano de correção com responsáveis e prioridade.

A certificação condicional nunca deve ser apresentada como homologação integral.

## Not Certified

Quando existe:

- P0 aberto.
- Falha de independência essencial.
- Integração real quebrada.
- Risco de segurança crítico.
- Corrupção de estado.
- Contrato central incompatível.
- Ausência de evidência dos fluxos essenciais.

## Certification Blocked

Quando não foi possível executar verificações obrigatórias por restrições do ambiente.

Não classificar ausência de execução como sucesso ou falha funcional comprovada.

---

# 13. RELATÓRIO FINAL OBRIGATÓRIO

Gerar:

`docs/homologation/FINAL-ECOSYSTEM-CERTIFICATION.md`

O documento deve conter:

1. Resumo executivo.
2. Data da homologação.
3. SHAs das nove mains auditadas.
4. Descrição dos ambientes.
5. Inventário das capacidades realmente implementadas.
6. Matriz de compatibilidade entre Forjas.
7. Matriz de hosts e MCP.
8. Matriz de contratos.
9. Matriz de independência.
10. Resultados de instalação e lifecycle.
11. Resultados dos cenários E2E.
12. Testes de segurança.
13. Indicadores de cobertura.
14. Falhas identificadas.
15. Correções implementadas.
16. PRs criados.
17. Testes não executados.
18. Limitações conhecidas.
19. Riscos residuais.
20. Recomendação de release.
21. Estado final da certificação.

Adicionar uma tabela executiva:

| Projeto | Independência | Contratos | Integração | E2E | Status |
|---|---|---|---|---|---|
| The Forge | TBD | TBD | TBD | TBD | PENDING |
| Forge CLI | TBD | TBD | TBD | TBD | PENDING |
| Forge Portal | TBD | TBD | TBD | TBD | PENDING |
| API Forge | TBD | TBD | TBD | TBD | PENDING |
| Spark Forge AWS | TBD | TBD | TBD | TBD | PENDING |
| Spark Forge Azure | TBD | TBD | TBD | TBD | PENDING |
| Platform Forge | TBD | TBD | TBD | TBD | PENDING |
| Forge Doctor Data | TBD | TBD | TBD | TBD | PENDING |
| Forge Doctor API | TBD | TBD | TBD | TBD | PENDING |

Substituir os valores apenas com resultados efetivamente verificados.

---

# 14. CRITÉRIOS DE QUALIDADE DOS TESTES

Os testes devem ser:

- Determinísticos quando a funcionalidade permitir.
- Reproduzíveis.
- Isolados.
- Seguros.
- Automatizáveis.
- Versionados.
- Rastreáveis.
- Com mensagens diagnósticas úteis.
- Resistentes a falsos positivos.
- Executáveis localmente sem custos externos, sempre que possível.

Os testes E2E devem chamar executáveis, processos ou serviços reais.

Não considerar um teste de integração válido caso ele apenas importe módulos ou verifique a presença de arquivos.

Para fluxos envolvendo AI hosts, distinguir:

- Testes de contrato do host.
- Testes de configuração.
- Testes de handshake.
- Testes de execução real.
- Testes com LLM externo.

Somente a execução efetiva autoriza declarar o respectivo nível homologado.

---

# 15. COMPORTAMENTO ESPERADO DO EXECUTOR

Ao receber este prompt:

**Primeiro:** descubra os nove repositórios e capture seus estados reais.

**Segundo:** audite código, contratos, versões, testes e integrações existentes.

**Terceiro:** produza um plano de execução fundamentado nos gaps encontrados.

**Quarto:** implemente testes de certificação reutilizáveis.

**Quinto:** execute os testes locais e de integração possíveis.

**Sexto:** corrija falhas identificadas sem violar a independência dos projetos.

**Sétimo:** reexecute os gates afetados e valide regressões.

**Oitavo:** produza relatórios e PRs separados conforme necessário.

**Nono:** entregue a classificação real de certificação.

Não interromper o trabalho apenas porque um teste falhou.

Investigar, identificar causa-raiz, corrigir e testar novamente.

Não afirmar que todos os testes passaram quando parte deles não foi executada.

Não considerar a missão concluída apenas pela criação de documentação.

A missão só estará concluída quando existir uma suíte executável, relatórios baseados em evidência e uma decisão de certificação fundamentada.

---

# 16. RESULTADO FINAL DESEJADO

Ao final deste programa, o ecossistema deve ser capaz de comprovar os seguintes cenários:

**A. Independência:** qualquer Forja pode ser utilizada isoladamente.

**B. Distribuição:** Forge CLI facilita a instalação, mas não é uma dependência funcional.

**C. Observabilidade:** Forge Portal permite compreender e operar capacidades reais, mas não é obrigatório.

**D. Orquestração:** The Forge identifica e coordena especialistas por contratos.

**E. Especialização:** cada Forja preserva seu domínio e suas responsabilidades.

**F. Interoperabilidade:** diferentes Forjas conseguem trocar informações estruturadas e verificáveis.

**G. Segurança:** nenhuma camada amplia silenciosamente as permissões de outra.

**H. Qualidade:** os resultados possuem testes e evidências reproduzíveis.

**I. Evolução:** novas versões podem ser introduzidas sem regressões silenciosas.

**J. Adoção:** um novo usuário consegue instalar, configurar, executar e compreender o ecossistema sem precisar conhecer a implementação interna de todos os projetos.

## DIRETRIZ FINAL

Não queremos apenas nove repositórios com funcionalidades avançadas.

Queremos um ecossistema de engenharia agentic cujos componentes sejam independentes, interoperáveis, seguros, observáveis e comprovadamente úteis.

**A homologação deve demonstrar que The Forge é capaz de coordenar especialistas reais, sem transformar esses especialistas em dependentes do orquestrador.**

Execute a missão ponta a ponta, priorizando evidências, correções estruturais e confiabilidade operacional.

**A definição de sucesso é: integração comprovada, não integração presumida.**

Eu colocaria essa homologação imediatamente antes do próximo release integrado e a transformaria em um gate permanente. Assim, cada evolução do Forge CLI, Portal ou de qualquer especialista poderá ser validada contra o ecossistema inteiro, reduzindo o risco de uma melhoria local quebrar a integração global.
