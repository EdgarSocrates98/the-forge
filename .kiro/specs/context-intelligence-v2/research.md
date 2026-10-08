# Research & Design Decisions — context-intelligence-v2

## Summary
- **Feature**: `context-intelligence-v2` (Wave C do Cycle 2)
- **Discovery Scope**: Extension (descoberta light sobre o core existente) com aprofundamento de segurança na consulta ao git, que é a única integração externa nova.
- **Key Findings**:
  - O broker atual (`context/broker.py`, 57 linhas) é uma função pura de `(task, provider_id, globs, scan)`: o ponto de extensão é limpo. A seleção só considera arquivos casados por glob, e todo arquivo selecionado é lido inteiro para calcular o sha256 (nenhum cache).
  - O orquestrador sobrescreve `ExecutionResult.metrics` com `tokens=unknown` mesmo quando o provider mede tokens, e não há reverificação de contexto após `execute`. Só o echo provider confere o hash, e a divergência que ele reporta não altera o outcome do run.
  - `git status` não é somente leitura por padrão: ele pode reescrever o índice (refresh de stat) e executar comandos configurados pelo repositório (`core.fsmonitor`, filtros `clean`/`process` de `.gitattributes`). A consulta precisa de overrides explícitos e de uma checagem da configuração local antes do `status`.

## Research Log

### Ponto de extensão do Context Broker
- **Context**: requisitos 1, 2, 4 e 7.
- **Sources Consulted**: `src/theforge/context/{broker,scan}.py`, `src/theforge/contracts/context.py`, `src/theforge/forger/orchestrator.py`, `tests/test_broker.py`, `tests/test_protocol_adversarial.py`.
- **Findings**:
  - `scan_workspace` já devolve a lista ordenada de arquivos e exclusões por segurança (`secret`, `outside_root`, `symlinked_dir`, `missing`, `max_files_reached`), com teto de 20.000 arquivos. Ele continua sendo a fonte de candidatos.
  - `build_context_pack` ranqueia por número de globs casados e lê cada arquivo com `fh.read(remaining + 1)`. `BUDGETS` é importado por `tests/test_broker.py`.
  - `tests/test_protocol_adversarial.py` faz monkeypatch de `orchestrator.build_context_pack`. A assinatura usada pelo orquestrador precisa continuar substituível pelo mesmo nome.
  - `validate_context_pack` exige `used_bytes <= budget_bytes`, `used_bytes == soma(files.bytes)` e caminhos léxicos válidos. Isso continua válido se `bytes` de um `excerpt` for o tamanho do intervalo e o tier `metadata` não contar bytes.
- **Implications**: manter `build_context_pack` como fachada com o mesmo nome; mover a relevância e o hashing para módulos próprios; `BUDGETS` passa a ser derivado da tabela de perfis.

### Contratos e compatibilidade
- **Context**: requisito 12.
- **Sources Consulted**: `docs/protocol.md` (campos desconhecidos), `src/theforge/contracts/schema.py`, `src/theforge/runs/store.py`.
- **Findings**:
  - Contratos de provider (`ExecutionResult`, `ForgeManifest`) são lidos de forma tolerante, e artefatos do core são relidos com `strict=True`, aceitando a ausência de campos opcionais (runs antigos).
  - `ContextPack` e `TaskSpec` têm schema aberto porque cruzam o protocolo. `RoutingDecision`, `ExecutionReceipt` e `RiskAssessment` têm schema fechado.
  - `explain` lê todo nome em `runs.store.ARTIFACTS`. Novos artefatos aparecem automaticamente em `explain --json`.
- **Implications**: todos os campos novos são opcionais com default; o novo `RunTelemetry` é exportado com schema fechado (nunca cruza o protocolo); o regenerador de schemas cobre a paridade.

### Git somente leitura
- **Context**: requisito 3; ameaça "repositório analisado malicioso" herdada da Wave A.
- **Sources Consulted**: documentação do git (`git-status`, `git-config`: `core.fsmonitor`, `--no-optional-locks`/`GIT_OPTIONAL_LOCKS`, `safe.directory`, `gitattributes` filtros), CVE-2022-24765 (ownership), conhecimento consolidado do comportamento do git ≥ 2.26.
- **Findings**:
  - `git status` faz refresh do índice e pode gravar `.git/index` e criar `index.lock`. `--no-optional-locks` (equivalente a `GIT_OPTIONAL_LOCKS=0`, git ≥ 2.15) impede essas escritas opcionais.
  - `core.fsmonitor` com valor de comando executa um programa a cada `status`. Pode ser neutralizado com `-c core.fsmonitor=false`.
  - Filtros `filter.<driver>.clean`/`process` (ativados por `.gitattributes`) podem rodar durante o refresh de arquivos com stat "racy". Não há override genérico para desligar todos os filtros. A configuração local (`.git/config`, `config.worktree` e includes) pode ser inspecionada sem executar nada com `git config --list --show-scope --includes` (git ≥ 2.26).
  - `--ignore-submodules=all` evita que o `status` recursione em submódulos (que teriam a própria configuração).
  - git ≥ 2.35.2 recusa repositórios de outro dono ("dubious ownership"). Sobrescrever `safe.directory` enfraqueceria a proteção do usuário.
  - `git status --porcelain=v2 --branch -z` entrega em uma chamada `branch.oid` (ou `(initial)`) e `branch.head` (ou `(detached)`), mais os caminhos alterados relativos ao toplevel.
- **Implications**: três chamadas com tempo limite total (rev-parse, config local, status); recusa conservadora de `status` quando a configuração local ou de worktree define chaves que executam programas; nada de `safe.directory`; ambiente mínimo via `security.env.safe_env` + `GIT_OPTIONAL_LOCKS=0`, `GIT_TERMINAL_PROMPT=0`; spawn via `protocol.proctree` (kill de árvore no timeout).

### Cache de fingerprints
- **Context**: requisito 5.
- **Sources Consulted**: ADR 0009 (cache do registry fora do projeto), técnica "racy git" do índice do git (entrada cuja mtime não é anterior ao momento da gravação do índice é tratada como suja).
- **Findings**:
  - Um cache dentro do workspace (`.forge/cache/`) pode ser pré-populado por um repositório malicioso (`git add -f`), pelo mesmo motivo que levou o cache do registry para fora do projeto.
  - `os.stat` expõe `st_size`, `st_mtime_ns`, `st_ctime_ns`, `st_ino` e `st_dev` em Linux, macOS e Windows (no Windows `st_ino` é o file index do NTFS e `st_ctime` é a data de criação até 3.11; ainda assim é evidência adicional, nunca motivo para reutilizar).
  - A granularidade de mtime varia (FAT: 2 s; ext4/NTFS: sub-ms). Uma janela "racy" de 2 s cobre o pior caso comum.
- **Implications**: cache em `<cache do usuário>/context/<digest12 da raiz>.json`, chave por caminho relativo, reutilização só com igualdade total de stat e mtime fora da janela racy; qualquer outra situação recalcula.

### Tokens
- **Context**: requisito 7.
- **Findings**: não existe tokenizador na stdlib e cada modelo tokeniza de um jeito. Qualquer razão fixa bytes→tokens seria uma estimativa sem base declarada.
- **Implications**: o core reporta `tokens` como `unknown`. Ele só preserva `measured`/`estimated` informados pelo provider. Nenhuma estimativa é calculada pelo core nesta wave.

### Baseline de performance
- **Context**: requisito 11; Wave A deixou "budgets saem do baseline medido em context-intelligence-v2".
- **Findings**: `time.perf_counter_ns` e `subprocess` bastam (stdlib). A suíte offline leva ~3–7 min neste host, e rodar sessões de pytest concorrentes quebra o `--basetemp` compartilhado (nota 5.1 da Wave A). Benchmarks não devem entrar na suíte padrão.
- **Implications**: script em `scripts/bench/` fora do pytest padrão; um teste rápido cobre só a lógica de comparação com budgets; o baseline é medido antes da tarefa do cache de fingerprints.

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Notes |
|--------|-------------|-----------|---------------------|-------|
| Pipeline de funções puras no `context/` (escolhido) | `relevance` → `fingerprints` → `broker` (seleção por tiers) → `verify` (pós-execução), orquestrados pelo `forger` | Segue o padrão existente (broker e router são funções puras); testável sem subprocesso | O orquestrador cresce (negociação + verificação) | Extrair o laço de execução para um helper privado |
| Serviço de contexto com estado (classe `ContextBroker` longa) | Objeto que guarda scan, cache e git por run | Menos parâmetros | Estado oculto, mais difícil de testar e de reusar pela Wave D | Rejeitado |
| Índice persistente do workspace (estilo índice do git) | Manter um índice completo do workspace entre runs | Varredura incremental | Muito além do pedido; risco de staleness; seria um mini-banco | Rejeitado (YAGNI) |

## Design Decisions

### Decision: tabela de perfis como fonte única
- **Context**: requisitos 9.1–9.6; hoje `BUDGETS` (context) e `EXECUTE_TIMEOUTS` (forger) são tabelas separadas.
- **Alternatives Considered**:
  1. Manter tabelas espalhadas por módulo.
  2. Um módulo `theforge/profiles.py` com `ContextProfile` congelado por perfil.
- **Selected Approach**: opção 2. `context` e `forger` leem a mesma tabela; `BUDGETS` vira alias derivado por compatibilidade.
- **Rationale**: a diferença entre perfis precisa ser provada por teste e registrada no run; uma única tabela torna isso verificável.
- **Trade-offs**: `economy` passa a não fazer fallback de health (mudança de comportamento documentada).
- **Follow-up**: `cross-forge-foundation` consome `max_providers`.

### Decision: tiers por referência, sem conteúdo
- **Context**: requisitos 1.1–1.7; ADR 0007.
- **Alternatives Considered**: incluir trechos de conteúdo no ContextPack; manter só arquivo inteiro.
- **Selected Approach**: `excerpt` é um intervalo de linhas `[start, end]` com hash e tamanho do intervalo; o provider lê o intervalo do arquivo.
- **Rationale**: preserva ADR 0007 (nada de conteúdo persistido) e a verificabilidade por hash.
- **Trade-offs**: o provider precisa saber ler intervalos (documentado; campo opcional ignorável por providers v1, que leem o arquivo inteiro e verão hash divergente do arquivo inteiro → tratado como divergência conservadora). Para evitar falsos positivos, só providers que declaram suporte a `excerpt` recebem esse tier (ver decisão seguinte).

### Decision: tiers avançados exigem declaração do provider
- **Context**: providers v1 existentes não conhecem `excerpt` nem pedido de contexto.
- **Selected Approach**: `Capability.context` (opcional) declara `excerpts: bool` e `requests: bool`; o manifest declara `context_revalidation`. Sem declaração, o broker usa só `metadata` + `reference` e nunca aceita pedido de contexto.
- **Rationale**: mudança estritamente aditiva; nenhum provider existente recebe um tier que não entende.
- **Trade-offs**: o perfil define o máximo permitido; o efetivo é a interseção perfil × declaração do provider (registrado na telemetria).

### Decision: cache de fingerprints no diretório de cache do usuário
- **Context**: requisito 5.4.
- **Alternatives Considered**: `.forge/cache/` (já criado), memória por processo.
- **Selected Approach**: `<user_cache_dir()>/context/<digest12(raiz resolvida)>.json`, escrita atômica, releitura estrita, redação antes de gravar com recusa se a redação alterar algo.
- **Rationale**: mesmo modelo de ameaça do ADR 0009; `.forge/cache/` continua reservado e efêmero, sem uso.
- **Trade-offs**: o cache não é compartilhado entre usuários; arquivos de raízes antigas não são podados (custo só de disco, como no ADR 0009).

### Decision: divergência (TOCTOU) rebaixa evidência e o run vira `partial`
- **Context**: requisitos 6.1–6.7.
- **Alternatives Considered**: falhar o run (`provider_failure`); só anotar limitação.
- **Selected Approach**: o run termina `partial`; evidências `confirmed`/`observed` sobre itens divergentes são persistidas como `unresolved` com limitação `context-drift: <status original>`; limitações `context-drift: <path>` no resultado e no receipt.
- **Rationale**: o resultado restante pode ser útil, mas nada derivado de conteúdo divergente fica "confirmado".
- **Trade-offs**: o core altera o status epistêmico informado pelo provider; a alteração é sempre explícita.
- **Revisão cruzada (com `real-provider-integration`)**: a regra de drift reportado só é válida com uma semântica fixa de `Evidence.hash`. Definição adotada: sha256 de exatamente o conteúdo entregue em `location.path` — arquivo inteiro para `reference`, intervalo `lines` do item para `excerpt`/`requested` com linhas — e nulo em qualquer outro caso. A comparação é contra `ContextFile.sha256` (que já é o hash do intervalo quando há linhas), nunca contra o hash do arquivo inteiro para um item com intervalo. `Location` v1 só tem `line` pontual, que não altera o escopo. Os adapters da Wave B declaram `context_revalidation` (`hash`); é só um seam, sem mudança aqui.

### Decision: pedido de contexto via `ExecutionResult.context_request`
- **Context**: requisito 8; ops `plan`/`verify`/`estimate` são reservadas e pertencem à Wave D.
- **Alternatives Considered**: nova op `context`; reaproveitar `plan`.
- **Selected Approach**: campo opcional `context_request` no `ExecutionResult` de `execute`. Se presente, a resposta é uma rodada de negociação e nunca é persistida como resultado. O core reexecuta `execute` com o ContextPack estendido, até o limite de rodadas do perfil (máx. 2).
- **Rationale**: não exige op nova nem mudança de major; um provider v1 que não declara suporte nunca envia o campo.
- **Trade-offs**: cada rodada é um novo processo `execute` (custo medido na telemetria).

### Decision: telemetria como artefato próprio vinculado ao receipt
- **Context**: requisitos 10.1–10.5 e 9.4.
- **Alternatives Considered**: estender `ExecutionResult.metrics` (só existe em sucesso); campos no receipt.
- **Selected Approach**: contrato `theforge/RunTelemetry/v1` (core-only, schema fechado), artefato `telemetry` gravado em todo `_finish` antes do receipt; `ExecutionReceipt.telemetry_sha256` opcional.
- **Rationale**: runs recusados ou com falha também têm telemetria; o receipt continua a âncora de integridade.
- **Revisão cruzada (com `cross-forge-foundation`)**: decidido que a Wave D grava `telemetry` também para runs de plano (varredura, routing, `providers_executed` = nós executados, `ProfileSnapshot`) e acrescenta `telemetry_sha256` ao receipt do plano. Para isso, todas as métricas de `RunTelemetry` têm default `unknown`, o contrato não limita `providers_executed` (o ≤ 1 do `ask` é provado por teste de fluxo) e os campos por provider/ContextPack ficam no default em runs de plano. 10.1 e 9.4 não foram estreitados. A Wave D também reescreve o `explain` em texto via `ExplainReport` e deve preservar as seções de contexto e telemetria desta spec e seus testes.

## Synthesis Outcomes
- **Generalização**: "relevância" é um único mecanismo de sinais com prioridade fixa (glob, dependência, alvo, caminho citado, git) em vez de casos especiais; o pedido de contexto do provider reaproveita a mesma seleção/validação (`requested` passa pelo mesmo filtro de caminho, segredo, budget e limite de arquivos). A reverificação pós-execução e a detecção pelo provider convergem para o mesmo `DriftReport`.
- **Build vs. adopt**: git é consultado como ferramenta externa opcional (não há parser de índice na stdlib; escrever um seria desproporcional). Tokenização não é adotada (sem tokenizador universal; `unknown` honesto). Benchmark com `time.perf_counter_ns` (sem `pytest-benchmark`, para manter zero deps e fora da suíte padrão).
- **Simplificação**: sem índice persistente do workspace; cache só de fingerprints de arquivo inteiro (excerpts são sempre recalculados); sem estimador de tokens; sem novo comando de CLI (`explain` ganha a seção de contexto); nenhum `WorkspaceDescriptor` (o resumo `metadata` é local ao ContextPack).

## Risks & Mitigations
- Filtros ou fsmonitor definidos no repositório executam código durante `git status` — checagem prévia da configuração local/worktree e recusa conservadora (limitação registrada), mais `-c core.fsmonitor=false`.
- Cache de fingerprints reutilizado indevidamente (mtime grosseiro, relógio ajustado) — janela racy de 2 s, igualdade de `size`, `mtime_ns`, `ctime_ns`, `ino`, `dev` e caminho resolvido; propriedade testada: cache ligado ou desligado produz os mesmos hashes.
- `economy` sem fallback reduz resiliência — documentado; o usuário escolhe `balanced` para fallback.
- Conflito de numeração de ADR entre waves — resolvido na revisão cruzada com numeração congelada: 0014 e 0017 (Wave B), 0015 e 0016 (esta spec), 0018 e 0019 (Wave D), 0020 (Wave E); sem fallback para o próximo número livre.
- Alteração de `theforge.__version__` sem a linha da matriz de compatibilidade quebraria `test_compat_matrix.py` (Wave B) — esta wave não prevê alterar a versão; se alterar, a linha de `docs/versioning.md` entra na mesma mudança.
- `RecursionError` em `redact`/`canonical_json` para payloads profundos (nota 4.2 da Wave A) — o `context_request` tem profundidade fixa e limite de itens; nenhum `Any` novo é aceito do provider.
- Benchmarks instáveis em CI compartilhado — budgets com tolerância documentada; verificação de budgets fora do gate de PR.

## References
- `docs/adr/0007-context-pack-by-reference.md` — ContextPack por referência.
- `docs/adr/0009-registry-cache-location.md` — cache fora do projeto.
- `docs/adr/0013-provider-identity.md` — identidade observada.
- Documentação do git: `git-status(1)` (`--porcelain=v2`, `--no-optional-locks`), `git-config(1)` (`core.fsmonitor`, `--show-scope`, `--includes`, `safe.directory`), `gitattributes(5)` (filtros).
- `.kiro/specs/cycle2-reality-hardening/{design.md,tasks.md}` — invariantes de integridade e notas de implementação (4.2, 5.1).
