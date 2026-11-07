# Cycle 1 — integração governada e prontidão operacional

## Decisão

Iniciar o Ciclo 1 como evolução de integração do ecossistema existente.
Não criar `api-sentinel-forge` enquanto os gates abaixo não forem satisfeitos.
O Sentinel continua sendo uma composição futura de evidências, não um novo
analisador, roteador, banco de traces ou frontend.

## Ordem de execução

| Ordem | Frente | Resultado verificável | Prioridade |
|---|---|---|---|
| 1 | Registry local | sincronização aprovada e isolada dos providers; `describe` e `health` routáveis | P0 |
| 2 | Adapters | adapters estreitos para Data Sentinel, Code Atlas, Forge Lens e Agent Bridge, sem importar `theforge`, com `describe`, `health`, `execute` e replay determinístico | P0 |
| 3 | Contratos negativos | testes produtor/consumidor para tipo ausente, schema incompatível, capability inexistente, origem não autorizada e receipt incompleto | P0 |
| 4 | Laboratório real | repetir o laboratório API Operations com provider routável e preservar receipt, traces e hashes | P0 |
| 5 | PortalApi | endpoints de investigação alimentados pelos receipts reais, com estado `unavailable` explícito quando não houver provider | P1 |
| 6 | UX federada | matriz comum de `--help`, `--version`, instalação dry-run, JSON estruturado, TTY/TTY não interativo e mensagens de erro para os oito repositórios | P1 |
| 7 | Cloud | homologação AWS/Azure somente com credenciais e autorização explícitas; nunca bloquear o caminho local | P2 |

## Gate de adapters

Cada adapter precisa demonstrar:

- distribuição independente, sem dependência runtime do The Forge;
- protocolo `forge/v1`, envelope determinístico e códigos de erro estruturados;
- manifesto com identidade canônica igual ao `forge.json` do produtor;
- capability IDs com namespace do produtor e ações declaradas;
- `health` distinguindo `ready`, `unavailable` e `degraded`;
- `execute` somente para capability declarada, com timeout e workspace isolado;
- replay local para sucesso, indisponibilidade e saída nativa malformada;
- teste de instalação em ambiente limpo e teste de não vazamento de secrets.

O estado `DISCOVERED` ou `INSTALLABLE` não pode ser promovido para
`EXECUTION_READY` apenas por existir um manifesto. A promoção exige evidência
de execução registrada.

## Gate de contratos federados

O conjunto de testes deve provar simultaneamente que:

1. todo artifact consumido tem produtor compatível;
2. todo consumidor declara intake/handoff;
3. referências de verifier resolvem para capabilities existentes;
4. versões incompatíveis falham de forma negativa e explicável;
5. receipts preservam `producer`, `protocol`, `trace_id`, `evidence_refs`,
   `uncertainty` e hashes sem permitir evidência fabricada;
6. nenhuma rota é inferida por nome de provider, cloud ou presença de arquivo.

## Gate de UX/CLI

A matriz não executa instalações destrutivas. O primeiro estágio usa apenas
superfícies seguras: `--help`, `--version`, `install --help`, plan/dry-run,
saída JSON e comandos em diretório temporário. Cada linha registra comando,
versão observada, exit code, formato da saída, suporte a TTY e bloqueios.

Falhas de ambiente devem aparecer como `UNAVAILABLE` ou `BLOCKED`, nunca como
sucesso sintético. A matriz serve de contrato para a experiência do usuário
independente de especialização, não como prova de execução do provider.

## Critério para reavaliar o API Sentinel

Só reabrir a decisão de criação quando todos os itens seguintes forem verdes:

- quatro adapters novos promovidos e routáveis;
- negativos produtor/consumidor verdes;
- registry local reparado em ambiente aprovado;
- laboratório real repetido com receipt final;
- PortalApi consumindo esse receipt sem duplicar analyzer ou trace store;
- matriz UX/CLI sem regressões P0/P1.

Até lá, a estratégia correta é fortalecer as fronteiras existentes e manter a
composição do Sentinel como uma especificação de integração testável.
