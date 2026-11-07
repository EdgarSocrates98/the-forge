# Executive summary — Cycle 0.5

## Estado inicial

O ecossistema possui oito projetos com responsabilidades complementares,
manifests agentic e CLI próprios. A execução anterior deixou verdes os gates de
instalação/CLI do The Forge, o gate visual profundo do Portal, e as suítes
principais dos especialistas. Isso demonstra boa saúde local por repositório,
mas não prova interoperabilidade cross-repository.

## Decisão provisória

`CONDITIONAL GO` para construir o laboratório de compatibilidade e preparar a
decisão de uma futura API Sentinel Forge. Ainda não é aprovação do Cycle 0.5 e
não autoriza criar o novo repositório.

Condições de saída:

- baseline e contratos canônicos publicados;
- identidade `forge_id` sem ambiguidade;
- distinção explícita entre manifest declarado, superfície CLI e adaptador
  homologado;
- laboratório local com HTTP, OpenAPI, degradação determinística, evidência
  hash-addressed e diagnóstico real;
- testes negativos para versão, payload, referências, redaction, provider
  indisponível e instalação;
- decisão final separando capacidades que já pertencem ao API Forge, Doctor API,
  Data Sentinel, Code Atlas e Forge Lens.

## Risco mais importante

O maior risco não é falta de comandos; é a falsa sensação de integração causada
por nomes e manifests compatíveis. O The Forge deve continuar sendo o único
control plane, enquanto cada especialista fornece apenas seu domínio canônico.
