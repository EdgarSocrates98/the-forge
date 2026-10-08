# Implementation Plan

- [x] 1. Fundação: contratos de manifest, esqueleto dos adapters e ambiente local
- [x] 1.1 Validar a versão declarada pelo provider segundo SemVer 2.0.0 e registrar os códigos novos de manifest
  - Criar o validador puro de SemVer 2.0.0 (núcleo, pré-release e build; sem zeros à esquerda, sem `v`, ASCII) que nunca lança e devolve "malformada" para qualquer entrada inválida
  - Acrescentar `FORGE-MANIFEST-VERSION` e `FORGE-MANIFEST-TAXONOMY` à fonte única de códigos; se `cross-forge-foundation` já estiver em `main`, acrescentá-los no mesmo commit à família `registry` de `CODE_FAMILIES`, à tabela de `docs/errors.md` (lista canônica testada) e ao golden de códigos publicados
  - Registrar no mapa de markers por arquivo, de uma vez, todos os arquivos de teste novos previstos no design (com as categorias definidas lá), para que nenhuma tarefa posterior precise editar esse mapa
  - Testes unitários em `test_manifest_rules.py` com versões válidas (`0.1.0`, `1.2.3-rc.1+build.5`) e inválidas (`1.0`, `v1.2.3`, `01.2.3`, dígitos não ASCII, não string)
  - Pronto quando os testes unitários de versão passam, o guarda de literais `FORGE-*` continua verde (e, com `cross-forge-foundation` em `main`, o teste de taxonomia de erros também) e o mapa de markers já contém todos os arquivos de teste novos do design
  - _Requirements: 4.4_

- [x] 1.2 Declarar aliases e depreciação no contrato de capability
  - Acrescentar aliases, marcador de depreciação e substituta opcionais à capability, com defaults que mantêm válidos os manifests existentes
  - Rejeitar no manifest alias repetido, alias igual a um ID de capability do mesmo manifest e substituta igual à própria capability
  - Oferecer a resolução de um nome que procura primeiro o ID canônico e depois o alias, indicando se veio por alias
  - Regenerar os JSON Schemas publicados e cobrir os campos novos nos testes de contrato e de paridade de schema, preservando os campos opcionais de contexto que `context-intelligence-v2` acrescenta à mesma capability se já estiverem em `main`
  - Pronto quando o schema regenerado está em paridade, os testes de contrato cobrem cada colisão e um manifest do Cycle 1 sem os campos continua válido
  - _Requirements: 5.5, 5.6_

- [x] 1.3 Aplicar as regras mecânicas da taxonomia de capabilities
  - Implementar a função pura que devolve violações por capability (segmentos 2–3, tamanho de segmento e de ID, namespaces reservados, segmentos genéricos proibidos, formato de ação, formato de alias e de `replaced_by`) com o código de taxonomia e o campo apontando a capability
  - Ordem determinística das violações: por capability declarada, depois ID, aliases, ações, `replaced_by`
  - Testes em `test_manifest_rules.py` com um caso válido e um inválido por regra; `demo.echo` e as capabilities das fixtures continuam válidas
  - Pronto quando cada regra da tabela do design tem teste passando e nenhum provider existente do repositório viola a taxonomia
  - _Requirements: 5.1, 5.2_

- [x] 1.4 Criar o esqueleto instalável dos dois adapters e ligá-los ao ambiente de desenvolvimento e à CI
  - Criar as duas distribuições stdlib-only (Python ≥ 3.10, sem dependências declaradas), cada uma com README de instalação e registro, id do provider, versão SemVer própria (`0.1.0`), janela suportada do especialista e entrada executável por módulo que lê o request do stdin e responde, para toda op, um envelope `refused` com exit 0
  - Configurar lint dos adapters com alvo Python 3.10 herdando a configuração da raiz, e incluir os fontes dos adapters na checagem de tipos com imports dos especialistas tolerados como ausentes
  - Instalar os adapters em modo editável junto do pacote nos workflows `ci` e `compat`, atualizar os testes de estrutura de workflow para exigir essa instalação e verificar no teste de empacotamento que o wheel e o sdist de `theforge` não incluem `adapters/` e continuam sem dependências de runtime
  - Pronto quando `pip install -e .[dev] -e ./adapters/sparkforge -e ./adapters/apiforge` funciona em um venv novo, `python -m theforge_sparkforge describe` e `python -m theforge_apiforge describe` devolvem envelope `refused` com exit 0, e ruff, mypy, testes de workflow e de empacotamento passam
  - _Requirements: 3.1_

- [x] 1.5 Preparar o interpretador local do Spark Forge real e os workspaces de exemplo
  - Criar um venv local fora do repositório com `sparkforge-aws` instalado a partir de `E:\projetos\spark-forge-aws` e o adapter do Spark Forge em modo editável, e documentar nas notas de implementação o caminho usado em `THEFORGE_REAL_SPARKFORGE_PYTHON`
  - Registrar que o API Forge não tem interpretador local (Python 3.12 ausente) e que seus testes reais vão pular com motivo
  - Criar os workspaces de exemplo pequenos usados pelas gravações e pela integração: um job PySpark com `requirements` declarando `pyspark` para o Spark Forge; para o API Forge, um contrato OpenAPI com app FastAPI e `requirements` declarando `fastapi`, e um bundle de change-control no formato `af-change-bundle/1` (a composição espelha o workspace `cross` de `cross-forge-foundation`, usado em 6.4)
  - Pronto quando `<venv>/python -c "import sparkforge.adapters.tools, theforge_sparkforge"` sai com código 0 e os dois workspaces de exemplo existem com os arquivos que casam com as entradas declaradas no design
  - _Depends: 1.4_
  - _Requirements: 3.2_

- [x] 2. Core: aplicar as regras novas no registry, routing e CLI
- [x] 2.1 Aplicar versão e taxonomia no registry e expor o motivo de um describe recusado
  - Marcar como inválido, com o código de versão e a versão recebida (truncada), o provider cuja versão não é SemVer
  - Unificar limites de manifest e taxonomia no mesmo ponto de aplicação: capability violadora excluída com aviso; provider inválido quando nada sobra; semântica atual dos limites preservada
  - Incluir no erro do registro de um describe recusado o código e o detalhe do provider, redigidos e truncados em 500 caracteres
  - Testes de integração em `test_registry.py` para versão malformada, capability fora da taxonomia, alias colidente (provider inválido) e describe recusado com detalhe no registro
  - Pronto quando esses quatro cenários produzem registros com estado e mensagem esperados nos testes do registry
  - _Requirements: 1.8, 2.7, 4.4, 5.2, 5.6_

- [x] 2.2 (P) Resolver aliases e explicar depreciação e sobreposição na decisão de routing
  - No pedido explícito de capability, preferir declarantes do ID canônico e só depois declarantes por alias, mantendo o desempate atual por trust e id; a seleção registra sempre o ID canônico
  - Registrar nas limitações da decisão as notas estáveis de alias resolvido, capability depreciada (com ou sem substituta) e sobreposição entre providers nos caminhos explícito e por sinais, sem alterar ranking nem confiança
  - Fazer a recusa por op não suportada considerar também capabilities pedidas por alias
  - Testes em `test_router.py` e `test_forger.py` cobrindo canônico × alias entre providers, depreciação, sobreposição nos dois caminhos e alias sem `execute`
  - Pronto quando as decisões persistidas desses cenários contêm as notas esperadas e os testes adversariais de routing existentes continuam verdes
  - Independente de 2.1: usa só a resolução de nomes de 1.2 e não toca registry nem seus testes
  - _Boundary: Router, Forger_
  - _Depends: 1.2_
  - _Requirements: 5.4, 5.5_

- [x] 2.3 (P) Mostrar aliases, depreciação e sobreposição na listagem de capabilities
  - Incluir aliases, depreciação, substituta e os providers que declaram o mesmo ID na saída texto e JSON de `capabilities list` e `capabilities search`
  - Emitir aviso em stderr para cada capability depreciada listada; fazer a busca casar também por alias
  - Pronto quando os testes em `test_cli.py` verificam os campos novos no JSON, o aviso em stderr e a busca por alias
  - Independente de 2.1 e 2.2: toca só a CLI de capabilities e seus testes
  - _Boundary: CapabilitiesCLI_
  - _Depends: 1.2_
  - _Requirements: 5.4, 5.5_

- [x] 3. Shell comum dos adapters
- [x] 3.1 (P) Implementar o envelope Forge Protocol v1 e o despacho de ops do shell comum
  - Ler a op do último argumento e as opções do adapter antes dela (replay e versão assumida do especialista), ler o request do stdin e sempre sair com exit 0 e uma resposta com op e `request_id` ecoados e `producer` formado pelo id e pela versão declarados nas constantes do adapter
  - Recusar op desconhecida, protocolo diferente de `forge/v1` fora de describe, capability ou ação não declarada; responder erro estruturado para request inválido e para exceção inesperada (só o tipo, sem traceback)
  - Manter o shell compatível com Python 3.10, sem importar o pacote do core, e copiá-lo de forma idêntica para os dois adapters, ligando o esqueleto de 1.4 a ele
  - Testes em `test_adapter_shell.py` que dirigem por subprocesso um conjunto de handlers de teste (capability e ação declaradas só para o teste) e os dois adapters: recusas de op, capability e ação, request inválido, protocolo incompatível, `op` e `request_id` ecoados e `producer` conferido contra o id e a versão declarados nas constantes de cada adapter (o describe real só chega em 4.1/5.1; as asserções baseadas no manifest ficam para a conformance em 6.1); comparam as duas cópias do shell e fazem `ast.parse` com `feature_version=(3, 10)` dos fontes dos adapters
  - Pronto quando esses testes passam para o conjunto de teste e para os dois adapters
  - Independente das tarefas 2.x: só toca `adapters/` e o novo arquivo de teste do shell
  - _Boundary: AdapterShell_
  - _Depends: 1.4_
  - _Requirements: 1.4, 2.4_

- [x] 3.2 Montar o resultado, copiar para staging só os arquivos do ContextPack e tratar a ausência de entrada
  - Montar o resultado final com schema, `producer` igual ao manifest e `created_at` em UTC, para qualquer resultado do adapter (sem o limite de tamanho, que fica em 3.3)
  - Copiar para `stage/` no cwd só os arquivos do ContextPack contidos no workspace e com sha256 conferido, guardando o sha256 conferido de cada arquivo copiado; arquivo ausente, fora da raiz, symlink para fora ou divergente vira limitação e não é copiado; item com intervalo de linhas (campo de `context-intelligence-v2`) também não é copiado e vira a limitação própria de itens por intervalo, sem ser comparado com o hash do arquivo inteiro
  - Implementar a regra comum de `Evidence.hash`: devolver o hash nativo só quando ele é igual ao sha256 conferido do arquivo copiado em `location.path`; hash nativo ausente, malformado, diferente ou de path não copiado vira `null`
  - Sem a entrada exigida pela ação (os padrões de entrada de cada ação são fornecidos pelo adapter, a partir do seu catálogo ou mapa de verbos), devolver resultado parcial sem findings com a limitação de "sem entrada" e a incógnita correspondente, sem chamar o especialista nem consultar gravações de replay
  - Pronto quando os testes do shell mostram cada motivo de omissão (inclusive item por intervalo) como limitação, a regra de hash devolve o sha256 conferido só para hash nativo igual e `null` em cada um dos outros casos, o resultado sem entrada passa na validação de integridade do core (schema, producer, timestamp UTC) e nada é gravado fora do cwd
  - _Requirements: 1.3, 1.6, 2.3, 2.6_

- [x] 3.3 Limitar o resultado inline e mover a saída grande para artifact
  - Acima de 4 MiB, manter findings em ordem nativa e as evidências que eles referenciam até caber, gravar a saída nativa completa como artifact relativo ao cwd com sha256 e marcar o resultado como parcial com a limitação de truncamento, reaproveitando o montador de resultado de 3.2
  - Pronto quando um resultado acima do limite passa na validação de integridade do core como parcial, com artifact cujo sha256 confere com o arquivo gravado, e um resultado abaixo do limite sai inalterado
  - _Requirements: 1.7, 2.8_

- [x] 3.4 Executar processos nativos com teto de tempo e ambiente controlado
  - Executar sem shell, no cwd dado, com o ambiente recebido do core mais ajustes explícitos do adapter (nunca credenciais), saídas com teto e timeout de 85% do timeout de execute do perfil; estouro vira erro estruturado de timeout
  - Pronto quando os testes do shell provam o timeout estruturado, o ambiente sem variáveis com cara de credencial e o cwd respeitado
  - _Requirements: 1.6, 2.6_

- [x] 3.5 Reduzir o cwd do execute aos artifacts declarados
  - Depois de montar a resposta, em todo desfecho de execute (sucesso, parcial, recusa, erro, timeout), apagar `stage/` e todo arquivo ou diretório do cwd que não seja path de artifact da resposta, mantendo os artifacts declarados (inclusive a saída completa do spill de 3.3); falha de remoção vira limitação, nunca erro
  - Não atuar em describe nem health
  - Pronto quando os testes do shell mostram, para cada desfecho, um cwd que contém só os paths de `artifacts[]`, com o artifact do spill intacto e com sha256 conferindo
  - _Depends: 3.3, 3.4_
  - _Requirements: 1.6, 2.6_

- [x] 4. Adapter do Spark Forge
- [x] 4.1 Derivar o manifest do Spark Forge do snapshot gravado da superfície real, com replay do ambiente
  - Implementar o módulo que regrava, a partir do Spark Forge instalado, o snapshot das tools com anotações, argumentos obrigatórios e versão de origem, de forma determinística; gravar o snapshot inicial com o interpretador de 1.5
  - Implementar a tabela de capabilities do design (capability → ações → tools, sinais sem glob catch-all, bindings de argumentos com globs de entrada próprios e nenhum binding que aceite arquivo qualquer) e declarar só ações de tools read-only, sem open-world e com argumentos preenchíveis; listar nas limitações os grupos não expostos com motivo
  - Recusar describe com motivo acionável quando o Spark Forge não é importável; com `--replay`, substituir essa checagem pelo `environment.json` do diretório de replay
  - Declarar no manifest a estratégia de revalidação de contexto `hash` (campo opcional de `context-intelligence-v2`, ignorado por cores sem ele), já que o staging confere o sha256 do que o especialista lê
  - Estabelecer o layout de replay do Spark Forge segundo o design: cenário saudável `tests/fixtures/native/sparkforge/default/` (usado pela conformance) e um subdiretório completo por desfecho em `scenarios/<nome>/`, com a gravação de erro prevalecendo quando `.json` e `.error.json` coexistem
  - Garantir por teste que nenhum padrão de entrada de ação aceita `*.md` nem arquivo qualquer, para que a conformance de 6.1 continue no caminho "sem entrada"
  - Testes em `test_adapter_sparkforge.py`
  - Pronto quando o describe em replay devolve um manifest em que toda capability passa na taxonomia, nenhuma tool AWS ou de escrita aparece, as exclusões estão nas limitações e o JSON do manifest traz a estratégia de revalidação `hash`, e sem `--replay` no venv de desenvolvimento o describe é recusado com motivo
  - _Depends: 1.5, 3.5_
  - _Requirements: 1.1, 1.5, 1.8, 5.3_

- [x] 4.2 Reportar a saúde do Spark Forge sem rede e sem credenciais
  - Verificar interpretador, importabilidade do dispatcher sem importá-lo, versão do Spark Forge dentro da janela e presença do snapshot, sem chamar o doctor nativo
  - Reportar indisponível com motivo quando interpretador, importação ou snapshot falham, e degradado com versão encontrada e janela esperada fora da janela; a versão assumida por opção substitui a encontrada, inclusive em replay
  - Gravar o `health.json` do cenário `default` e os cenários de saúde indisponível e degradada no layout de 4.1
  - Pronto quando os testes em replay mostram `ok`, `unavailable` com motivo e `degraded` com versão e janela
  - _Requirements: 1.2, 4.5_

- [x] 4.3 Traduzir saídas e erros nativos do Spark Forge a partir de gravações reais
  - Gravar com o interpretador de 1.5, sobre o workspace de exemplo do Spark, a saída nativa de uma ação de `pyspark.static-analysis` (um único arquivo com a saída da tool e a saída do julgamento encadeado) no cenário `default`, e um erro nativo tipado em um cenário próprio, no layout de 4.1, por meio de um pequeno auxiliar de gravação que 4.4 reaproveita
  - Traduzir facts em evidências com o ID nativo, localização relativa ao workspace e hash pela regra comum de 3.2 (o `artifact_sha256` nativo só é aproveitado quando igual ao sha256 conferido do arquivo da localização; senão `null`), e findings em findings com regra nativa, severidade mapeada e referências só a evidências presentes; paginação restante vira limitação de resultado parcial
  - Traduzir tool desconhecida e erros nativos em recusa estruturada com código prefixado do Spark Forge, detalhe e desbloqueio quando houver
  - Testes unitários de tradução sobre essas gravações
  - Pronto quando os resultados traduzidos das gravações passam na integridade do core com IDs de evidência iguais aos IDs nativos, todo hash de evidência é `null` ou igual ao sha256 conferido do arquivo da localização (com um caso de `artifact_sha256` divergente virando `null`) e o erro gravado vira recusa com código `SPARKFORGE-*`
  - _Requirements: 1.3, 1.4, 1.9_

- [x] 4.4 Executar capabilities do Spark Forge com backends real e de replay
  - Chamar a tool da ação com o staging como repositório, argumentos preenchidos pelos bindings e saída reduzida e limitada quando aceita; encadear o julgamento nativo sobre os facts produzidos; aplicar a tradução de 4.3 e o limite inline de 3.3
  - Manter estado, journal e traces nativos dentro do cwd do run e removê-los com a limpeza de 3.5 depois da tradução (sobra só o artifact do spill, quando houver)
  - Em replay, ler a gravação da ação pedida; ação sem gravação devolve `error` `ADAPTER-REPLAY-MISSING` com o arquivo esperado, sem chamar o especialista
  - Gravar com o auxiliar de 4.3 e o interpretador de 1.5 as saídas de replay das ações exercitadas sobre o workspace de exemplo do Spark, e montar um cenário de saída grande derivado de uma gravação real ampliada (marcado como derivado) ou gerado no próprio teste, para não versionar fixture acima de 4 MiB
  - Pronto quando, em replay, toda ação gravada termina `ok`/`partial` e passa na integridade do core, uma ação sem gravação devolve `ADAPTER-REPLAY-MISSING`, o execute sem entrada compatível devolve `partial` "sem entrada" sem consultar gravação, a saída grande vira `partial` com artifact, o repositório e o diretório de estado passados à chamada nativa ficam sob o cwd do run, e ao fim de cada execute o cwd contém só os paths de `artifacts[]` (a verificação com arquivos reais fica em 7.2)
  - _Requirements: 1.3, 1.6, 1.7, 3.1_

- [x] 5. Adapter do API Forge
- [x] 5.1 (P) Derivar o manifest do API Forge da matriz pública gravada, com replay do ambiente
  - Implementar o módulo que regrava o snapshot da matriz pública a partir do API Forge instalado e gravar o snapshot inicial a partir do arquivo da matriz do repositório irmão (provisório, marcado como montado à mão)
  - Implementar o mapa de verbos offline do design e expor só registros `supported`/`heuristic`, `read_only` e mapeados, preservando ID e estado nativos; demais registros nas limitações com motivo
  - Recusar describe com motivo explícito quando o interpretador não é 3.12 ou o API Forge não é importável; com `--replay`, substituir essas checagens pelo `environment.json` do diretório de replay
  - Declarar no manifest a estratégia de revalidação de contexto `hash`, como no adapter do Spark Forge
  - Estabelecer o layout de replay do API Forge segundo o design: cenário saudável `tests/fixtures/native/apiforge/default/` e um subdiretório completo por desfecho em `scenarios/<nome>/`, com a gravação de erro prevalecendo quando `.json` e `.error.json` coexistem; garantir por teste que nenhum padrão de entrada aceita `*.md` nem arquivo qualquer
  - Testes em `test_adapter_apiforge.py`
  - Pronto quando o describe em replay expõe `api.analyze` e `api.change-control`, lista os demais registros com motivo, toda capability passa na taxonomia e o JSON do manifest traz a estratégia de revalidação `hash`, e sem `--replay` neste ambiente o describe é recusado citando Python 3.12
  - Independente das tarefas 4.x: só toca `adapters/apiforge`, `tests/fixtures/native/apiforge` e o próprio arquivo de teste
  - _Boundary: ApiForgeAdapter_
  - _Depends: 1.3, 3.5_
  - _Requirements: 2.1, 2.5, 2.7, 5.3_

- [x] 5.2 Reportar a saúde do API Forge sem rede e sem credenciais
  - Verificar Python 3.12, importabilidade, versão dentro da janela e o doctor nativo executado em diretório temporário, mapeando seus estados para `ok`, `degraded` e `unavailable`
  - Reportar indisponível com o motivo do interpretador ou da importação e degradado com versão e janela fora da janela, aceitando a versão assumida por opção; gravar o `health.json` do cenário `default` e um cenário por estado do doctor (`ready`, `degraded`, `unresolved`, `blocked`) no layout de 5.1
  - Pronto quando os testes em replay mostram cada mapeamento de estado e os motivos esperados
  - Sequencial a 5.1: usa o mesmo backend de replay e o mesmo arquivo de teste
  - _Requirements: 2.2, 2.7, 4.5_

- [x] 5.3 Traduzir casos e erros nativos do API Forge a partir de entradas montadas
  - Montar, a partir do formato de caso e das fixtures do repositório irmão, um caso de sucesso de `api.analyze` no cenário `default` e linhas `AF-*` de recusa (exit 2) e erro (exit 3) em cenários próprios, no layout de 5.1 e marcados como provisórios
  - Traduzir os findings e facts do caso em findings e evidências que referenciam os IDs nativos, com hash pela regra comum de 3.2 (`source.sha256` só quando igual ao sha256 conferido do arquivo da localização; senão `null`), omitindo `not_applicable` com contagem nas limitações, e anexar os arquivos do caso como artifacts com sha256
  - Traduzir a linha `AF-*` do stderr em recusa (exit 2) ou erro (exit 3 ou interno) preservando código, campo e desbloqueio; saída sem linha reconhecível vira erro estruturado com o fim do stderr
  - Testes unitários de tradução sobre essas entradas
  - Pronto quando os resultados traduzidos passam na integridade do core com IDs nativos, todo hash de evidência é `null` ou igual ao sha256 conferido do arquivo da localização (com um caso de `source.sha256` divergente virando `null`) e as recusas mantêm o código `AF-*` intacto
  - Sequencial a 5.1: depende do mapa de verbos e compartilha o arquivo de teste
  - _Requirements: 2.3, 2.4, 2.9_

- [x] 5.4 Executar capabilities do API Forge pela CLI pública com backends real e de replay
  - Rodar o verbo mapeado no mesmo interpretador, com cwd do adapter, cache nativo desligado, entradas tiradas do staging e saída sob o cwd, sem usar limiar de falha; aplicar a tradução de 5.3 e o limite inline de 3.3; depois da tradução, a limpeza de 3.5 remove `.apiforge/` e as saídas do caso que não viraram artifact
  - Em replay, ler a gravação da ação pedida; ação sem gravação devolve `error` `ADAPTER-REPLAY-MISSING` com o arquivo esperado, sem chamar o especialista
  - Completar as gravações provisórias de replay no layout de 5.1: um caso de `api.change-control` no cenário `default`, um cenário de erro interno sem linha `AF-*` e um cenário de saída grande (derivado ou gerado no teste)
  - Verificar offline, no executor de processo nativo, que o verbo recebe cwd sob o cwd do run, `APIFORGE_CACHE=off` e diretório de saída sob o cwd
  - Pronto quando, em replay, as ações gravadas das duas capabilities terminam `ok`/`partial`/`refused`/`error` conforme a gravação e os resultados passam na integridade do core, uma ação sem gravação devolve `ADAPTER-REPLAY-MISSING`, o execute sem contrato ou bundle compatível devolve `partial` "sem entrada", a saída grande vira `partial` com artifact, o argv, o cwd e o ambiente passados ao processo nativo mantêm todas as saídas sob o cwd do run, e ao fim de cada execute o cwd contém só os paths de `artifacts[]` (a verificação com arquivos reais fica em 7.2)
  - _Requirements: 2.3, 2.6, 2.8, 3.1_

- [x] 6. Conformance offline dos adapters
- [x] 6.1 Certificar os dois adapters em replay na suíte de conformance existente
  - Incluir os dois adapters em modo replay, apontando para o cenário `default` de cada um, na lista de providers certificados da conformance
  - A conformance executa toda capability com contexto vazio ou com arquivo que não casa com nenhuma entrada, portanto exercita o caminho "sem entrada" e não depende de gravações de execute
  - Pronto quando toda a suíte de conformance (describe, health, execute de toda capability, recusas, op ecoado, producer, integridade) passa para os dois adapters sem rede e sem os repositórios irmãos
  - _Depends: 4.4, 5.4_
  - _Requirements: 3.1_

- [x] 6.2 Verificar os adapters em replay pelo caminho do core
  - Em `test_adapters_core.py`, com os adapters registrados no `providers.toml` isolado apontando, conforme o caso, para o cenário `default` ou para os cenários de erro, saída grande e saúde gravados em 4.x/5.x: estado no registry, run do Forger com erro nativo gravado preservado até o receipt, resultado parcial com artifact persistido a partir da gravação de saída grande, versão fora da janela como degradado, e especialista ausente (adapter sem `--replay` no venv de desenvolvimento) como `invalid` com motivo; em cada run, o `work/` do run contém só os paths de `artifacts[]`
  - Pronto quando esses cenários passam na suíte offline padrão e o receipt de cada run registra o status e o código esperados
  - _Depends: 2.1, 4.4, 5.4_
  - _Requirements: 1.4, 1.6, 1.7, 1.8, 2.4, 2.6, 2.7, 2.8, 3.1, 4.5_

- [x] 6.3 Provar que os adapters não geram drift de contexto nos workspaces de exemplo
  - Em `test_adapters_core.py`, executar pelo Forger, em replay, cada capability com gravação sobre os workspaces de exemplo de 1.5 e verificar que toda evidência com hash não nulo tem item do ContextPack com o mesmo caminho e hash igual ao sha256 desse item
  - Quando `context-intelligence-v2` estiver em `main`, exigir também nenhum drift reportado pelo provider, nenhuma limitação de drift e a estratégia de revalidação registrada como `hash` (não `undeclared`)
  - Pronto quando o teste passa na suíte offline padrão para os dois adapters e falha se uma gravação tiver hash nativo divergente copiado para a evidência
  - Sequencial a 6.2: compartilha `test_adapters_core.py`
  - _Depends: 6.2_
  - _Requirements: 1.3, 2.3, 3.1_

- [x] 6.4 Checar o lado B da seam da tarefa de prova de `cross-forge-foundation`
  - Em `test_adapters_core.py`, rotear sem capability pedida a tarefa "Projete um pipeline Spark que produza dados para uma API" sobre os manifests dos dois adapters em replay (cenário `default`), com arquivos e dependências do workspace `tests/fixtures/workspaces/cross/` (fixture de `cross-forge-foundation`, obrigatória quando existir em `main`) ou, antes dela, da combinação dos workspaces de exemplo de 1.5
  - Agrupando os candidatos por provider, verificar que cada provider tem exatamente uma melhor capability com o mínimo de tipos de sinal do router: `spark-forge` → `pyspark.static-analysis` e `api-forge` → `api.analyze`; um empate ou outra capability se corrige nos sinais do catálogo dos adapters, nunca no core
  - Pronto quando o teste passa na suíte offline padrão; é a checagem do lado B da seam e precisa ser reexecutado em cada gatilho de revalidação dela listado no design
  - Sequencial a 6.3: compartilha `test_adapters_core.py`
  - _Depends: 6.3_
  - _Requirements: 3.1, 5.3_

- [x] 7. Conformance de integração contra os Forges reais
- [x] 7.1 Implementar o contrato de ambiente dos Forges reais
  - Ler as variáveis do interpretador de cada Forge e a variável de obrigatoriedade; verificar na ordem variável definida, arquivo existente e importação do adapter e do especialista, pulando com motivo explícito ou falhando quando obrigatório
  - Montar o registro do provider real no `providers.toml` do usuário isolado do teste sem repassar nenhuma variável ao provider
  - Testes unitários em `test_real_providers_env.py` com o ambiente simulado: variável ausente, arquivo inexistente, falha de importação e obrigatoriedade ligada
  - Pronto quando esses testes passam na suíte offline padrão e mostram os motivos de skip e a falha em modo obrigatório
  - _Requirements: 3.3, 3.4, 3.5_

- [x] 7.2 Cobrir describe, health, execute, ausência, version skew e drift contra os Forges reais
  - Para cada Forge, via core: provider pronto com versão SemVer e capabilities na taxonomia, sem capability de rede; saúde sem credenciais; execute de uma capability exposta sobre o workspace de exemplo de 1.5 com resultado íntegro, IDs nativos, nenhum diretório nativo fora do run, `work/` do run reduzido aos artifacts declarados e todo hash de evidência não nulo igual ao sha256 do item do ContextPack de mesmo caminho; interpretador inexistente e especialista ausente com motivo; versão assumida fora da janela como degradado
  - Drift: snapshot igual à superfície viva, e saída nativa viva da ação exercitada com as mesmas chaves de topo e formato de IDs que a gravação de replay da mesma ação
  - Pronto quando `pytest -m real_provider` passa contra o Spark Forge local de 1.5 e pula o API Forge com motivo explícito nesta máquina
  - _Depends: 1.5, 4.4, 5.4_
  - _Requirements: 1.1, 1.2, 1.3, 1.6, 1.8, 2.1, 2.2, 2.3, 2.6, 2.7, 3.2, 3.6, 4.5, 5.3_

- [x] 7.3 Rodar a integração real no workflow agendado com os dois interpretadores
  - Preparar no workflow de providers reais um ambiente 3.11 para o Spark Forge e um 3.12 para o API Forge, instalando cada especialista do checkout irmão e o adapter correspondente, e exportar o contrato de ambiente com obrigatoriedade ligada
  - Propagar o exit code dos testes reais sem tolerar seleção vazia e remover a tolerância a falha do job, mantendo gatilhos só agendado e manual, permissões mínimas e o segredo restrito aos checkouts
  - Atualizar os testes de estrutura do workflow para as novas propriedades
  - Pronto quando os testes de estrutura de workflow passam e o YAML exporta as três variáveis do contrato sem expor segredo fora dos checkouts
  - _Requirements: 3.7_

- [x] 8. Documentar as regras de versão e testar a matriz de compatibilidade
  - Escrever as regras separadas de versão de pacote, protocolo, schema de contrato, provider e evolução de capability, com a janela de suporte
  - Publicar a matriz (The Forge, Forge Protocol, adapters, especialistas suportados, suporte até) como fonte única
  - Escrever a regra de manutenção: toda wave ou release que altera `theforge.__version__` acrescenta a linha dessa versão na matriz no mesmo commit (gatilho de revalidação para as waves seguintes, registrado no design)
  - Testar que a matriz cobre a versão atual de The Forge e dos adapters, que a janela de cada adapter é igual à da matriz e que o major de protocolo é suportado; a falha nomeia a versão sem linha e cita a regra
  - Pronto quando o teste da matriz passa e falha ao alterar a versão de um adapter ou de The Forge sem atualizar a matriz
  - _Requirements: 4.1, 4.2, 4.3_

- [x] 9. ADRs e documentação de integração
- [x] 9.1 (P) Registrar a decisão de local dos adapters e o guia de providers reais
  - Escrever o ADR 0014 de local dos adapters avaliando acoplamento, independência de release, compatibilidade retroativa, ownership, instalação, segurança, testes e version skew, com a decisão e o gatilho de migração para entrada nativa; na parte de segurança, registrar que `.forge/runs/<id>/work/` guarda dados escritos pelo provider, não redigidos, fora da invariante de redação do core, e que o adapter reduz o que sobra aos artifacts declarados
  - Escrever o guia de providers reais: instalação de cada adapter no interpretador do especialista, registro, contrato de ambiente, regravação de snapshots e troubleshooting
  - Pronto quando o ADR e o guia existem e o guia descreve as três variáveis do contrato
  - Independente de 8 e 9.2: toca só o ADR 0014 e o guia de providers reais
  - _Boundary: ADR 0014, docs/real-providers.md_
  - _Requirements: 3.3, 4.6_

- [x] 9.2 (P) Registrar a taxonomia de capabilities e o catálogo inicial
  - Escrever o ADR de taxonomia com o número congelado 0017 (0014 desta spec; 0015 e 0016 de `context-intelligence-v2`; 0018 e 0019 de `cross-forge-foundation`; 0020 de `agentic-maintainability`; nenhum outro número em caso de conflito) e o documento de capabilities com regras de namespace, subject, granularidade, ações, sobreposição, versionamento, depreciação e aliases, mais a tabela de regras mecânicas
  - Publicar o catálogo inicial dos dois Forges com a origem nativa de cada capability e o motivo de cada exclusão
  - Teste em `test_capability_catalog_doc.py` que lê a tabela do catálogo e a compara com o describe em replay dos dois adapters
  - Pronto quando esse teste passa e falha se uma capability for exposta sem constar no catálogo
  - Independente de 9.1: toca só o ADR 0017, o documento de capabilities e o próprio teste
  - _Boundary: ADR 0017, docs/capabilities.md_
  - _Depends: 4.1, 5.1_
  - _Requirements: 5.1, 5.3, 5.7_

- [x] 9.3 Atualizar protocolo, guia de autoria, arquitetura, segurança e README
  - Documentar os códigos novos, a regra SemVer, aliases e depreciação, a raiz dos paths de artifact, os adapters reais (inclusive na arquitetura, com links para os ADRs 0014 e 0017), a contenção de estado nativo no cwd do run e as capabilities não expostas, com nota de migração para autores de provider
  - Em `docs/protocol.md`, manter no máximo uma tabela curta dos códigos de manifest com link para `docs/errors.md` (de `cross-forge-foundation`), declarado como lista canônica e testada de códigos `FORGE-*`
  - Em `docs/security.md`, registrar que `.forge/runs/<id>/work/` fica fora da invariante "tudo que o core persiste passa por redact" (dados escritos pelo provider, não redigidos) e que os adapters deixam ali só os artifacts declarados
  - Em `docs/provider-authoring.md`, registrar a regra de `Evidence.hash` (sha256 exatamente do conteúdo coberto pelo item do ContextPack em `location.path`, senão `null`) e a declaração de `context_revalidation` dos adapters
  - Pronto quando cada documento listado cita os códigos novos (`FORGE-MANIFEST-VERSION`, `FORGE-MANIFEST-TAXONOMY`) e os ADRs 0014 e 0017 onde aplicável, `docs/protocol.md` linka `docs/errors.md`, `docs/security.md` descreve a exceção de `work/`, e a suíte offline (incluindo o guarda de literais `FORGE-*` e os testes de workflow) continua verde
  - _Requirements: 1.3, 1.5, 1.6, 2.3, 2.5, 2.6, 3.3, 4.4, 5.1_

- [x] 10. Validação final: rodar os gates completos e a integração real disponível
  - Rodar lint, tipos, paridade de schemas, suíte offline padrão e a seleção `real_provider` com o Spark Forge local
  - Confirmar que nenhum teste novo ficou sem categoria e que o pacote `theforge` continua sem dependências de runtime
  - Pronto quando todos os gates passam localmente e o resultado da integração real (Spark executado, API pulado com motivo) está registrado nas notas de implementação
  - _Requirements: 1.1, 1.2, 1.3, 2.1, 3.1, 3.2, 3.4, 3.6_

## Implementation Notes
- Cross-spec review (minor, open): (a) link protocol.md -> docs/errors.md only when errors.md exists (D creates it after its gate 5.3); (b) document the replay recording JSON shape (case files findings/facts/artifact manifest, exit code, how replay recreates artifacts[]) in OfflineConformance — D hand-builds API scenarios/cross from it; (c) 6.4 must also assert non-empty matched.keywords and spark-before-api keyword positions (D intent-order needs them); (d) the context_revalidation="hash" test must inspect the RAW describe payload (parsed ForgeManifest lacks the field if B merges before C).
- (controller, 2026-10-03) Python 3.12.13 now installed via uv (C:\Users\edgar\AppData\Roaming\uv\python\cpython-3.12.13-windows-x86_64-none\python.exe): task 1.5 creates the API Forge venv as well (instead of recording it absent); real API Forge tests (7.2) can run locally.
- 1.1: FORGE-MANIFEST-VERSION/-TAXONOMY only in codes.py (D not in main): whoever merges last adds them to CODE_FAMILIES registry family, docs/errors.md and the golden. All 9 B test files pre-registered in FILE_MARKERS.
- 1.2: new Capability defaults change manifest_sha256 of every provider -> each existing registry cache is discarded once with a warning after upgrade (safe). Mention in 9.3 docs/changelog. replaced_by==id check lives in Capability.__post_init__ (same ContractError effect).
- 1.5: `THEFORGE_REAL_SPARKFORGE_PYTHON=E:\projetos\.venvs\theforge-sparkforge\Scripts\python.exe` (Python 3.11.15, base = uv cpython-3.11.15; `sparkforge-aws` 0.5.0 non-editable from `E:\projetos\spark-forge-aws` + PyYAML 6.0.3, jsonschema 4.26.0; `theforge-sparkforge-adapter` 0.1.0 editable). `import sparkforge.adapters.tools, theforge_sparkforge` exits 0. API Forge: the original plan recorded "no local interpreter (Python 3.12 absent) -> real API tests skip with reason"; per the controller note above, 3.12.13 is now present, so `THEFORGE_REAL_APIFORGE_PYTHON=E:\projetos\.venvs\theforge-apiforge\Scripts\python.exe` was also created (Python 3.12.13; `apiforge` 0.1.0 non-editable from `E:\projetos\api-forge`; `theforge-apiforge-adapter` 0.1.0 editable; `import apiforge, theforge_apiforge` exits 0). On a machine without 3.12 the API real tests still skip with the reason from the env contract. Example workspaces: `tests/fixtures/workspaces/spark/` (`requirements.txt` pyspark, `jobs/orders_job.py`: 17 facts from `sparkforge_analyze_pyspark` incl. udf/driver_collect/join/partitioning) and `tests/fixtures/workspaces/api/` (`openapi.yaml`, `app/main.py` FastAPI with one undocumented DELETE route -> `AF-CODE-002`, `requirements.txt` fastapi, `change-bundle.json` af-change-bundle/1 with workspace-relative `contract: openapi.yaml`, `project: app`). Smoke (outside repo): `apiforge analyze --contract openapi.yaml --project app --out-dir out/case` and `change-control run --bundle change-bundle.json --out-dir out/cc` exit 0 from the workspace root; api-forge requires `--out-dir` under cwd (`AF-CASE-PATH-TRAVERSAL` otherwise) and not overlapping `--project` (`AF-CASE-INPUT-OUTPUT-OVERLAP`); a contract-clean app makes change-control refuse with `AF-ROUTING-NO-FINDINGS`. The bundle's `contract`/`project` are resolved against the native process cwd, so 5.4 must run the verb from (or rewrite paths to) the staged workspace.
- 2.2 follow-up (2026-10-03, user decision): an explicit request by alias whose alias declarers resolve to DIFFERENT canonical ids returns `ambiguous` (low confidence, candidates listed, `unresolved = ["capability-alias: '<alias>' resolves to different capabilities: <ids>"]`, alias notes kept). Same-canonical alias groups keep the trust-then-id tie-break. Rationale: CLAUDE.md invariant "ambiguity → ambiguous, never a guess" and req 5.5 ("a capability canônica"). Design §Router should be read with this refinement.
- 3.3 (2026-10-03): new code `ADAPTER-OUTPUT-TOO-LARGE` (not in design error table) → `error` when the result exceeds 4 MiB even with zero findings (e.g. huge limitations); nothing is written in that path, native output not saved. `ResultDraft.native_output` added (bytes raw, else JSON, None → full untruncated result) so the spill holds native output. Spill path fixed at `native/full-output.json`; adapters must not declare their own artifact at that path (duplicate/overwrite). Evidence not referenced by kept findings is dropped inline (kept in spill). Docs task 9.3 must add ADAPTER-OUTPUT-TOO-LARGE to the error table. Binary search re-serializes ~log2(n)×size; revisit if 3.4 native caps make it hot.
- 3.4 (2026-10-03): adapter timeout comes only from `task.budget_profile` (core `execute_timeout` override is not in the request; if smaller, core kills the adapter first and reports FORGE-PROTO-TIMEOUT; on Windows the native job is nested in the core's job). Credential rules and EXECUTE_TIMEOUTS are copies pinned by parity tests against the core. POSIX: SIGTERM guard kills the native tree; known residual window of microseconds between Popen fork and registration in `active` (fix: pthread_sigmask around spawn) — the POSIX SIGTERM test only runs on ubuntu CI. Output caps truncate with flags (64 MiB stdout / 1 MiB stderr). Missing native executable falls to ADAPTER-INTERNAL; per-adapter tasks (4.x/5.x) map it.
- 3.5 (2026-10-03): `cleanup_workdir(cwd, keep, *, preserve=())` — deviation from design signature/text: top-level entries that existed in cwd before execute are never touched (safety for manual runs in real dirs; the core's RunStore always gives a fresh empty `work/`, so no effect there). Gap accepted: a pre-existing top-level dir is kept whole (incl. children added during execute) and pre-existing files modified by the native process are kept. Links are always removed, never followed; a declared artifact that does not survive as a regular non-link file yields a limitation (see fix). Long paths >260 chars without LongPathsEnabled and extremely deep trees end in `workdir cleanup incomplete: <path>` (no `\?\` prefix; same limit as staging). Note: core integrity (`contracts/integrity.py`) checks artifact paths lexically only, not on disk.
- 3.5 follow-up candidate: a declared artifact that never existed gets no note (handler bug, not cleanup); since core integrity checks artifact paths only lexically, consider an `lexists` check per declared artifact → limitation + ok→partial (adapter tasks 4.4/5.4 or conformance 6.1). Directory artifacts get a misleading "removed artifact" note (harmless: sha256 artifacts are files). `normcase` covers Windows only (not case-insensitive macOS).
- 4.1/5.1 (2026-10-03): error codes not in design table, to document in 9.3: `ADAPTER-REPLAY-INVALID` (malformed replay environment.json), `SPARKFORGE-ADAPTER-SNAPSHOT-INVALID`, `APIFORGE-ADAPTER-SNAPSHOT-INVALID` (unreadable packaged snapshot); plus `ADAPTER-OUTPUT-TOO-LARGE` from 3.3. Convention: adapter-originated failures `<FORGE>-ADAPTER-<X>`; bare `<FORGE>-<X>` reserved for mapped native errors. `.gitattributes` pins LF for `adapters/**/native_*.json` and `tests/fixtures/native/**`. Spark: 15 capabilities / 26 actions exposed (only tools with native file-name conventions get bindings; others excluded with reasons — design's eligibility rule). API: `api.analyze` (`--project` must receive the `stage/` dir in 5.3, not a file) and `api.change-control`. Routing note for 6.4: `orchestration.analysis` `*dags/*.py` can co-score with `pyspark.static-analysis`; core fixture `fixture-spark` could tie if registered next to the real adapter.
- 4.2 (2026-10-03): Spark `health.json` shape `{dispatcher, specialist_version[, provenance]}` (not in design); replay dispatcher = health.json.dispatcher AND environment.json specialist_version non-null. Derived scenarios (specialist-missing, version-skew) carry provenance. For 6.x/7.2: core `registry/health.py` `check_health` returns `degraded` without forwarding the adapter check detail ("found <v>, supported <window>"); the real-provider test "health degraded com versão e janela" must read the checks or the core must forward details. Shell test `test_adapter_ops_refuse_without_specialist` now expects health ok + HealthReport unavailable.
- 5.2 decision (2026-10-04, controller under user goal "finish autonomously"): API Forge health ignores native doctor gaps for capabilities the adapter never uses (`network` — adapter is offline; `mcp-stdio` — adapter uses the CLI); they appear as informational detail only. Without this, real API Forge health would always be `degraded`. Other gaps keep the design mapping (ready→ok, degraded/unresolved→degraded, blocked→unavailable).
- 4.3 (2026-10-04): DESIGN ERRATA — Spark `pyspark.static-analysis` uses `detail_level="normal"`, not "summary" (real `sparkforge_judge` rejects summary facts: missing `subject`); 4.4 inherits `normal`. Native errors: typed or exit_code 2 → `refused`, else `error` (reconciles design §Spark text vs error table). New codes for 9.3: `SPARKFORGE-ADAPTER-NATIVE-INVALID` (non-page native output); `SPARKFORGE-TOOL-UNKNOWN` is the design's mapped native KeyError. For 4.4: native writes `.sparkforge/traces.db` into cwd DURING the call and at atexit; keep it inside the execute cwd; SQLite must be closed (gc.collect) before cleanup_workdir or Windows removal fails; optionally rewrite `stage/` prefix in native error detail to workspace-relative. Recorder `record_execute` validates --workspace (Snyk python/PT hardening).
- 5.3 notes for 5.4: `APIFORGE_CACHE=off` does not disable `analyze` case cache at `<cwd>/.apiforge/cache` (contained by cleanup); bad `--out-dir` errors exit 2; native case.json uses backslashes on Windows (normalize); case files serialized json.dumps(indent=2, sort_keys=True)+"\n" in replay so hashes match. New code for 9.3: `APIFORGE-ADAPTER-NATIVE-INVALID`.
- 4.4 (2026-10-04): DESIGN ERRATA — Spark live backend runs `call_tool` in a child process (`python -m theforge_sparkforge.native_call` via shell `run_native`, cwd = execute cwd, same specialist interpreter), not in-process as design.md:140/:516 say; live backend lives in `execute.py`/`native_call.py`, not `backend.py`. Reasons: shell cleanup runs inside respond before process exit and the native atexit ledger would recreate `.sparkforge/traces.db` after cleanup; child gives ADAPTER-NATIVE-TIMEOUT + tree kill (design.md:459) and releases SQLite before cleanup. Cost 3–5 s per live execute vs 51 s minimum budget. New code for 9.3: `SPARKFORGE-ADAPTER-NATIVE-FAILED` (child nonzero exit / truncated stdout). native_call validates --file paths before importing sparkforge.
- 5.4 (2026-10-04): change-control runs with native cwd = staged workspace root (API Forge resolves bundle paths against its cwd), `--bundle <b>`, absolute resolved `--out-dir <cwd>/change-control`; analyze keeps adapter cwd + `--contract stage/<c> --project stage --out-dir case`. `relativize_outputs` rewrites absolute run-dir paths in output files to relative POSIX before hashing (files hashed by a native manifest are left unchanged with a limitation). New codes for 9.3: `APIFORGE-ADAPTER-INPUT-OUTSIDE` (bundle path outside workspace). Replay recording shape `{argv, assembled_from, case_dir, case_files{relpath: doc|text}, exit_code, provenance, stdout[, native_cwd]}` with all keys validated before any write.
- 9.1/9.2 (2026-10-04): for 9.3 — adapter READMEs (adapters/*/README.md) are stale (say health/execute refuse); `docs/real-providers.md` describes `tests/real_providers.py` and the two-interpreter `real-providers.yml` per design — recheck it after 7.x lands. No ADR index exists in docs/adr/. `docs/capabilities.md` copies adapter limitation texts verbatim: any wording change requires updating the catalog (test_capability_catalog_doc enforces).
- 7.2 follow-up (2026-10-04): DESIGN ERRATA — API Forge health no longer runs `apiforge doctor` (design.md ~567/642, task 5.2): checks python/import/version/cli (`find_spec("apiforge.cli")`, no import); health.json shape `{provenance, cli}`; `doctor-*` scenarios replaced by `cli-missing`; note 5.2 superseded. Root cause: `import apiforge.cli` costs 3–17 s under load (pydantic models), not the doctor checks; design's "~3 s cold" was wrong. Same import cost hits every API execute (timeout budget). Trade-off: broken CLI deps surface in execute, not health. Real run 2026-10-04: Spark (sparkforge 0.5.0, 136 tools) and API (apiforge 0.1.0, 21 caps) both pass `-m real_provider` (16 passed), no drift. 9.3: document these.
- 10 (2026-10-04): gates green on 6746334 — ruff, mypy (80 files), schema parity, full offline suite in 3 sequential file chunks (single run reaped under memory pressure), all exit 0; `-m real_provider` 16 passed (Spark sparkforge 0.5.0 + API apiforge 0.1.0 both executed locally, no skips, 31.9 s); runtime dependencies = []; every test file categorized (harness test green).
