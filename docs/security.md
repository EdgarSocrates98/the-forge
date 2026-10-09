# Segurança — threat model resumido (ciclos 1–3)

Modelo de ameaça: repositório analisado malicioso, provider malicioso ou defeituoso e tentativa de escalar trust. Fora do modelo: usuário local mal-intencionado com escrita no próprio home. Os códigos `FORGE-*` citados aqui estão, com a família de cada um, na lista canônica [errors.md](errors.md).

| Ameaça | Mitigação | Pendente |
|---|---|---|
| Provider malicioso ou desconhecido | trust (`unverified` fora do routing por padrão, `blocked` nunca executa); repositório não pode se autoconceder trust; providers `unverified` não são executados; subprocess isolado; env por allowlist com filtro de credenciais; policy antes de executar | sandbox de SO ([ADR 0012](adr/0012-os-sandbox-research.md)), assinatura |
| Manifest adulterado ou trocado | id do manifest precisa bater com a entrada; `producer` (id e versão) verificado em describe, health e execute; versão SemVer obrigatória (`FORGE-MANIFEST-VERSION`); limites de manifest, regras mecânicas de taxonomia (`FORGE-MANIFEST-TAXONOMY`, [ADR 0017](adr/0017-capability-taxonomy.md)) e rejeição de glob catch-all; alias que colide no mesmo manifest deixa o provider `invalid`; todo candidato é descrito de novo antes da decisão final de routing | assinatura de manifest ([ADR 0013](adr/0013-provider-identity.md)) |
| Cache de registry adulterado | cache fora do projeto, no diretório de cache do usuário ([ADR 0009](adr/0009-registry-cache-location.md)); relido com leitura estrita; invalidado se a entrada ou o fingerprint local mudar; providers `unverified` nunca são cacheados; `init` e `registry refresh` removem o legado `.forge/registry` | — (quem escreve no próprio home está fora do modelo) |
| Resultado malicioso ou inconsistente | [integridade do resultado](protocol.md#integridade-do-resultado): IDs únicos, referências resolvidas, caminho de artifact checado sem ser aberto, hashes em hex minúsculo; resultado inválido não é persistido | — |
| Injeção de shell | `argv` em lista, `shell=False` | — |
| Path traversal / symlink | `resolve_inside` no scan e no echo-forge; `..` e symlinks para fora viram `excluded`; caminhos de ContextPack e de artifact checados lexicamente | — |
| Leitura de secrets do workspace | `.env`, `.env.*`, `*.pem`, `*.key`, `id_rsa*`, `id_ed25519*`, `*.pfx`, `*.p12`, `credentials*`, `.npmrc`, `.netrc`, `.pgpass`, `*.token`, `secrets.*` excluídos do ContextPack | detecção por conteúdo; o provider ainda lê o filesystem diretamente (ver limitações) |
| Vazamento de credencial em artefatos | redaction de padrões e chaves sensíveis antes de persistir; stderr do provider truncado e redigido, nunca persistido bruto; o cache do registry não é gravado quando a redação alteraria a entrada ou o manifest ([ADR 0009](adr/0009-registry-cache-location.md)) | `.forge/runs/<id>/work/` não é redigido ([exceção](#exceção-forgerunsidwork)) |
| Forge especialista real (Spark Forge AWS, API Forge) | adapter fora do core, em processo separado e no interpretador do especialista ([ADR 0014](adr/0014-provider-adapter-location.md)); só capabilities read-only e offline expostas, o resto em `limitations` do manifest; o especialista lê só cópias com sha256 conferido do ContextPack; estado nativo contido no cwd do run e reduzido aos artifacts declarados; health sem rede e sem credenciais | sandbox de SO; drift da superfície nativa é detectado só no workflow agendado |
| Exaustão de recursos | timeout por op (describe e health 10 s; execute 60 s / 180 s / 600 s em economy / balanced / max); stdout limitado a 8 MB; stderr a 64 KB; kill da árvore de processos em timeout, oversize ou interrupção | limite de CPU/memória |
| Prompt injection via workspace | core não usa LLM; conteúdo de arquivo nunca sai do ContextPack para os ops semânticos | providers semânticos que alimentam LLM devem tratar os campos como dado ([dados não-confiáveis](#dados-não-confiáveis-não-instruções)) |
| Prompt injection no planner/resolver/verifier semântico | `plan`, `resolve` e `verify` trocam contratos tipados, não prompts; a resposta é consultiva e só pode escolher dentro do conjunto oferecido — revalidada de forma determinística, e inválida, fora do conjunto ou de `producer` divergente preserva o desfecho determinístico; payload mínimo por construção | — |
| Claim de handoff malicioso | o item é dado para o destinatário: `claim` ≤ 500 chars, redigido, só de nós `inputs`, sem conteúdo de arquivo nem saída integral; o destino deve tratá-lo como dado não-confiável | — |
| Histórico de performance envenenado | `.forge/metrics/provider-performance.json` relido estritamente, malformado ignorado com nota; a história só desempata candidatos já empatados — nunca cria rota nem resolve `ambiguous` sozinha | — |
| Spoofing de capability por provider | o id do manifest precisa bater com a entrada registrada e `producer` é conferido em toda resposta; dois providers declarando o mesmo id geram nota `capability-overlap` com desempate determinístico (trust → história → id), nunca substituição silenciosa; `unverified`/`blocked` não entram no routing | assinatura de manifest |
| Memória cross-run envenenada | `.forge/intel/decisions.json` relido estritamente e ignorado com nota quando malformado; a memória só alimenta `theforge decisions`, que não inicia provider | — |
| Corrida na execução paralela | workdir e transporte por nó (cada nó é um run filho); `plan-state` por escrita atômica; telemetria e spans sob lock; o scheduler só libera o nó quando os `inputs` terminaram | — |
| Cache de inteligência envenenado | `.forge/intel/project.json` relido estritamente com guarda de root e fingerprints por seção — seção divergente é recomputada; sinais de git são lidos ao vivo em todo refresh, nunca do cache | — |
| Supply chain do core | zero dependências de runtime (gate de CI); build reprodutível via hatchling | lockfile do dev, assinatura |
| Mutação inesperada | policy `allow/ask/deny` sobre o `operation_class` declarado; artefato `risk` em todo run que chega a um provider; cwd controlado | enforcement real (sandbox) |
| Repositório afrouxando a policy | `.forge/config/policy.toml` só endurece; tentativas de afrouxar são ignoradas com aviso | — |
| Repositório executando código via `git` | [consulta git somente leitura](#consulta-git-somente-leitura): ambiente sem credenciais e sem transporte, `core.fsmonitor=false`, `status` recusado quando a configuração local define chaves executáveis, `safe.directory` intocado, timeout com kill da árvore ([ADR 0016](adr/0016-git-read-only-signals.md)) | filtros e hooks da configuração global/sistema do usuário (por exemplo `git-lfs`) |
| Cache de fingerprints adulterado | [cache fora do projeto](#cache-de-fingerprints-de-contexto), releitura estrita, reuso só sem nenhuma evidência de mudança, redação antes de gravar ([ADR 0015](adr/0015-context-intelligence.md)) | — (quem escreve no próprio home está fora do modelo) |
| Conteúdo mudando depois do hash (TOCTOU) | `Evidence.hash` com semântica definida, reverificação pelo nível do perfil; divergência nunca vira `confirmed` nem run `ok` ([protocol.md](protocol.md#revalidação-de-contexto-toctou)) | `economy` não reverifica (`context-not-reverified`) |
| Pedido de contexto abusivo | mesmas regras de caminho e segredo da varredura; nunca amplia budget nem limite de arquivos; no máximo 2 rodadas e 64 itens; caminhos recusados gravados redigidos | — |
| Vazamento entre nós de um plano | [handoff](#handoff-e-op-plan) só a partir dos nós declarados em `inputs`, sem conteúdo de arquivo nem saída integral, redigido antes de ser entregue e gravado, limitado a 256 itens e 256 KiB | o provider de destino ainda lê o filesystem diretamente |
| Estimativa (`plan`) afrouxando a policy | a classe estimada só pode endurecer a decisão; `plan` roda com a superfície de `describe`/`health` (cwd temporário, ambiente mínimo, timeout, `producer` conferido) e nunca falha o planejamento | — |
| Repositório injetando relações ou repositórios | `.forge/config/workspace.toml` lido com `tomllib` (até 64 KiB, symlink recusado), só `depends_on` entre repositórios descobertos, entradas inválidas ignoradas com aviso `FORGE-WORKSPACE-CONFIG`; descoberta sem seguir symlinks, até 3 níveis e 64 repositórios; git só pela consulta endurecida, com orçamento total de 20 s | relações são declarações do repositório, não verificadas |
| Vazamento por diagnóstico de erro | sem traceback na CLI; `--debug` mostra um [diagnóstico redigido](#diagnóstico-de-debug) só com quadros `theforge.*`, sem variáveis locais nem caminhos absolutos | — |
| Run adulterado depois de gravado | `explain` e `replay --mode verify` recalculam os hashes registrados no receipt e saem com exit 6 em divergência ([âncora de confiança](#integridade-de-runs-e-âncora-de-confiança)) | adulteração coordenada de receipt e artefatos não é detectável sem âncora externa |
| Plano de instalação executando código | `InstallationPlan` é só de planejamento: texto informativo, nenhum download, instalação ou comando | — |

## Dados não-confiáveis, não instruções
Invariante do ciclo 3: tudo que vem de fora do core — conteúdo do repositório, saída de provider (manifest, resultado, claim de handoff, estimativa), proposta de um backend de raciocínio — é **dado**, nunca instrução. O core não tem LLM e não interpreta texto: cada string externa é validada contra o contrato, redigida antes de persistir e, no máximo, retransmitida como campo de outro payload. Nenhum campo vindo de fora vira comando do core, altera o routing fora das regras determinísticas nem executa algo.

- **Ops semânticas.** `plan`, `resolve` e `verify` carregam dados não-confiáveis nos dois sentidos: o request traz a intent do usuário e sinais declarados por providers; a resposta é consultiva e revalidada campo a campo — escolha fora do conjunto oferecido, veredicto malformado ou `producer` divergente são descartados e a decisão determinística permanece. Um provider semântico que monte prompt para um LLM deve tratar cada campo do request como dado não-confiável ([provider-authoring.md](provider-authoring.md#regras-de-segurança)).
- **Handoff.** `claim`/`location` de cada item é texto produzido por outro provider — dado para o destinatário, redigido e limitado antes do envio ([handoff](#handoff-e-op-plan)).
- **Workspace.** Conteúdo de arquivo chega ao provider só via `ContextFile`/`ContextLines` declarados; para o core são bytes com sha256, nunca instrução.
- **Estado persistido.** Receipts, caches, métricas e inteligência são relidos estritamente e descartados com nota quando malformados — nunca executados.

## Ambiente do provider
O provider recebe só as variáveis abaixo (`ALLOWED_ENV` em `security/env.py`), quando existem no ambiente do pai. Nenhuma outra variável passa.

| Variável | Por que é mantida |
|---|---|
| `PATH` | resolver os executáveis que o provider inicia (python, git, …) |
| `PATHEXT` | Windows: extensões executáveis para resolver comandos no `PATH` |
| `SYSTEMROOT` | Windows: exigida pelo runtime do CPython e pela inicialização do Winsock |
| `SYSTEMDRIVE` | Windows: drive do sistema, usado pelo runtime e na resolução de diretórios temporários |
| `WINDIR` | Windows: diretório do Windows esperado pelas bibliotecas do sistema |
| `COMSPEC` | Windows: interpretador de comandos usado por helpers de subprocess e shell |
| `HOME` | POSIX: `Path.home()` e busca de configuração de ferramentas no processo filho |
| `USERPROFILE` | Windows: `Path.home()` e busca de configuração de ferramentas no processo filho |
| `TEMP` | Windows: diretório temporário para `tempfile` |
| `TMP` | Windows/POSIX: diretório temporário para `tempfile` |
| `TMPDIR` | POSIX: diretório temporário para `tempfile` |
| `LANG` | locale, para decodificação de texto consistente no filho |
| `LC_ALL` | override de locale, para decodificação de texto consistente no filho |
| `PYTHONIOENCODING` | forçada para `utf-8`, para o JSON do protocolo no stdio ser UTF-8 |
| `PYTHONUTF8` | forçada para `1`, para providers Python rodarem em modo UTF-8 |

- `HOME` e `USERPROFILE` continuam porque o Python filho precisa deles (`Path.home()`). Isso não abre acesso novo: o provider já lê o home pelo filesystem (ver limitações).
- Defesa em profundidade: uma segunda passada remove qualquer nome com cara de credencial (`AWS_*`, `TOKEN` como segmento do nome — `GITHUB_TOKEN`, `TF_TOKEN_*` —, `*SECRET*`, `*PASSWORD*`/`*PASSWD*`, `*API_KEY*`/`*APIKEY*`, `*ACCESS_KEY*`/`*ACCESSKEY*`, `*CREDENTIAL*`, `SSH_AUTH_SOCK`, `AZURE_*`, `ARM_*`, `GH_*`, `CLOUDSDK_*`, `ACTIONS_*`, `KUBECONFIG`, `DOCKER_CONFIG`, `NETRC`, `*_PROXY`), mesmo que um dia entre na allowlist por engano, e qualquer valor que contenha uma URL com credenciais (`esquema://usuário@…`). A comparação de nomes ignora maiúsculas.

- Os adapters reais repassam ao especialista o ambiente recebido do core, sem nomes com cara de credencial, e só acrescentam `APIFORGE_CACHE=off` (API Forge) e `PYTHONIOENCODING=utf-8` (processo filho do Spark Forge AWS). As variáveis `THEFORGE_REAL_*` são lidas só pelo harness de teste ([real-providers.md](real-providers.md)).

## Exceção: `.forge/runs/<id>/work/`
A invariante "tudo que o core persiste passa por `security.redact`" vale para os artefatos do run (`task`, `workspace-descriptor`, `routing`, `plan`, `installation`, `risk`, `handoff`, `context`, `context-r1`, `context-r2`, `result`, `plan-state`, `plan-result`, `graph`, `capability-graph`, `semantic-proposal`, `routing-proposal`, `decision`, `economy`, `global-stop`, `verification`, `telemetry`, `diagnostic`, `complexity`, `budget`, `receipt`), para os caches do registry e de fingerprints de contexto, para o histórico de performance (`.forge/metrics/provider-performance.json`) e para a inteligência do projeto (`.forge/intel/project.json`, `.forge/intel/decisions.json` — ambos relidos estritamente e ignorados com nota quando malformados). **`.forge/runs/<id>/work/` fica fora dela**: é o cwd do `execute`, e o que está ali foi escrito pelo provider, não pelo core, e **não é redigido**. O core não conhece o formato desses arquivos e não os reescreve.

- Os adapters reais deixam em `work/` **só os artifacts declarados** em `artifacts[]` (por exemplo a saída nativa completa `native/full-output.json` quando o resultado passa de 4 MiB, e os arquivos de caso do API Forge). Em todo desfecho (`ok`, `partial`, `refused`, `error`, timeout), `cleanup_workdir` apaga `stage/`, o estado nativo (`.sparkforge/`, `traces.db`, `.apiforge/`, caches) e todo o resto. Uma remoção que falha vira a limitação `workdir cleanup incomplete: <path>`.
- Esses artifacts podem conter trechos do código analisado. Trate `work/` com a mesma sensibilidade do workspace e não o publique.
- Um provider de terceiros não tem essa garantia: ele pode deixar em `work/` o que quiser ([provider-authoring.md](provider-authoring.md#regras-de-segurança)).
- Decisão e alternativas em [ADR 0014](adr/0014-provider-adapter-location.md#segurança-e-contenção).

## Consulta git somente leitura
O contexto lê branch, HEAD e arquivos alterados do repositório do workspace (`context/git.py`, [ADR 0016](adr/0016-git-read-only-signals.md)). A consulta só roda depois da policy, nunca escreve no repositório e trata o repositório como não confiável. Toda falha vira limitação `git: …` no ContextPack e no receipt; o run nunca falha por causa do git.

- **Chamadas** (5 processos, sempre como `git -c core.fsmonitor=false …`, `cwd` = raiz do workspace, um orçamento **total** de 5 s com kill da árvore via `protocol.proctree`):
  1. `rev-parse --show-toplevel --absolute-git-dir`;
  2. `symbolic-ref -q --short HEAD` (branch; falha = HEAD destacado);
  3. `rev-parse --verify -q HEAD` (falha = `no_commits`);
  4. `config --list --show-scope --includes -z` (inspeção da configuração);
  5. `status --porcelain=v1 -z --untracked-files=all --ignore-submodules=all --no-renames`, só se a inspeção não recusou.
- **Ambiente**: `safe_env()` (a mesma allowlist do provider, sem credenciais e sem `GIT_*` herdado) mais `GIT_OPTIONAL_LOCKS=0` (sem refresh oportunista do índice, sem `index.lock`), `GIT_TERMINAL_PROMPT=0`, `GIT_PAGER=cat`, `LC_ALL=C` e **nenhum transporte**: `GIT_NO_LAZY_FETCH=1` e `GIT_ALLOW_PROTOCOL=none`. Sem isso, num clone parcial (partial clone) o `status` pode buscar objetos ausentes sob demanda pelo remoto configurado no repositório, executando o transporte que o repositório escolher (`ext::<comando>`, `core.sshCommand`). `GIT_ALLOW_PROTOCOL=none` vale em qualquer versão e sobrepõe `protocol.*.allow` do repositório; `GIT_NO_LAZY_FETCH` exige git ≥ 2.44.
- **Recusa do `status`**: se a configuração de escopo `local` ou `worktree` define `core.fsmonitor` (qualquer valor, inclusive `false`) ou `filter.<driver>.clean|smudge|process`, o `status` não roda (limitação `git: status skipped: repository config defines <chave>`). Também é recusado quando o git não sabe reportar escopos (< 2.26: `git: version too old for safe status`), quando a configuração não pode ser inspecionada ou é grande demais (> 64 KB).
- **Ownership**: `safe.directory` nunca é alterado; um repositório que o git recusa vira `git: repository not trusted by git (safe.directory)`.
- **Saídas limitadas**: 64 KB por chamada, 8 MB para o `status`; a lista de alterados é truncada em 20 000 caminhos, com limitação. Caminhos alterados fora da raiz do workspace são descartados.
- **Estados** (`merge`, `rebase`, `cherry_pick`, `bisect`) vêm da existência léxica de arquivos no git dir, sem executar nada.

Limitações:
- Filtros, hooks e `fsmonitor` definidos na configuração **global** ou de **sistema** do usuário (por exemplo `git-lfs`) não são detectados e podem rodar durante o `status`: são configuração do próprio usuário.
- `GIT_NO_LAZY_FETCH` não existe antes do git 2.44; nessas versões a proteção contra lazy fetch depende só de `GIT_ALLOW_PROTOCOL=none`.
- A consulta confia no executável `git` encontrado no `PATH`.
- Quando o workspace está dentro de um repositório, cada run paga 5 processos `git` (ver [architecture.md](architecture.md#perfis)).

## Cache de fingerprints de contexto
O sha256 de arquivos inteiros pode ser reutilizado entre runs (`context/fingerprints.py`, [ADR 0015](adr/0015-context-intelligence.md)).

- **Local**: `<cache do usuário>/context/<digest12>.json` (mesmo diretório base do [ADR 0009](adr/0009-registry-cache-location.md)), nunca dentro do workspace: o repositório não consegue pré-popular hashes. Se o diretório de cache cair dentro do workspace (por exemplo `THEFORGE_CACHE_DIR` apontando para ele), o cache é desligado no run, com aviso.
- **Reuso conservador**: só quando `size`, `mtime_ns`, `ctime_ns`, `ino`, `dev` e o caminho resolvido batem com o `stat` atual **e** a entrada foi registrada mais de 2 s depois do `mtime` (janela racy). Qualquer outra situação lê e hasheia. Uma entrada só é registrada quando o `stat` antes e depois da leitura é igual. Intervalos de linha nunca usam o cache. Com ou sem cache, os hashes são os mesmos.
- **Releitura estrita**: documento `theforge/FingerprintCache/v1` relido com `strict=True`; ilegível, malformado, de outra versão ou de outra raiz é descartado com aviso.
- **Redação**: antes de gravar, cada entrada cujo caminho relativo ou resolvido tem formato de segredo é descartada, com aviso; se a redação ainda alterar o documento, ele não é gravado e uma cópia anterior é removida. Gravação atômica, uma vez por run; falha de escrita vira aviso, nunca erro.
- **Limitações**: não protege contra quem escreve no próprio home (mesmo modelo do ADR 0009). No Windows, `ctime` é o horário de criação, não de mudança de metadados, então é uma evidência mais fraca do que no POSIX; os demais campos e a janela racy continuam valendo.

## Handoff e op `plan`
Um plano multi-provider ([ADR 0018](adr/0018-multi-provider-execution.md)) não abre canal novo entre providers além do handoff e da estimativa.

- **Handoff.** Montado só a partir dos resultados válidos dos nós listados em `inputs` do nó de destino: um provider nunca recebe dados de um nó que não o alimenta. Os itens trazem ids, `claim` (no máximo 500 caracteres), localização, severidade e hashes; nunca conteúdo de arquivo nem a saída integral do provider. Cada item passa por `security.redact` antes de ser medido e cortado, e o que o provider recebe é o artefato `handoff` relido do disco, com o hash no receipt do nó. Limites: 256 itens e 256 KiB de JSON canônico ([protocol.md](protocol.md#handoff)).
- **Op `plan`.** Mesma superfície de `describe` e `health`: cwd temporário, ambiente mínimo, timeout de 10 s e `producer` conferido; providers `blocked` nunca são chamados e `unverified` só com `--allow-unverified`. A estimativa só endurece a policy (vale a decisão mais restritiva entre a classe declarada e a estimada). Nenhuma falha de `plan` falha o planejamento. `estimate` continua reservada e nunca é chamada.
- **Op `verify` (verificação independente).** Chamada só num provider `ready` que declara a op e uma capability com `can_verify` sobre `<produtor>/<capability>` do run — e só quando a identidade é distinta (outro `id` e outro `argv`; o mesmo programa sob outro id é recusado e nomeado). O payload é o que o run já persistiu redigido (`task`, `result`, `run_id`, `handoff?`), em cwd temporário com ambiente mínimo e `producer` conferido; nenhum arquivo do workspace sai. `refused`/`error`, payload malformado ou transporte falho viram `not_performed` — só `passed`/`failed` de um `VerifyVerdict` bem formado são veredicto, e `failed` demove o run a `partial` ([ADR 0021](adr/0021-independent-verification.md)).
- **Op `resolve` (resolver semântico de routing).** Chamada só quando o routing determinístico termina `ambiguous`, num provider `ready` que declara a op e uma capability `resolves_ambiguity` — `blocked` nunca, `unverified` só com `--allow-unverified`; `economy` nunca chama. A mesma superfície de `describe`/`health`: cwd temporário, ambiente mínimo, timeout de 10 s, `producer` conferido. O payload é mínimo por construção (`task`, os candidatos elegíveis com os sinais que pontuaram, a razão da ambiguidade, nomes de tecnologias) — nenhum arquivo nem conteúdo do workspace sai. A `RoutingProposal` é consultiva: escolha fora do conjunto oferecido, provider desconhecido ou capability/ação não declarada são rejeitados e o `ambiguous` determinístico permanece; a seleção validada ainda passa por health, policy e verificação ([ADR 0025](adr/0025-semantic-routing-fallback.md)).
- **`provider check` (kit de conformidade).** Executa o argv informado sem registry e sem trust gate — é uma ferramenta de authoring sobre um binário que o próprio usuário escolheu. As chamadas usam a mesma superfície endurecida: `SubprocessTransport` com ambiente `safe_env` (allowlist + filtro de credenciais), timeout por chamada, cwd temporário e kill da árvore; as sondas de protocolo malformado usam `subprocess` direto, também com `safe_env`. Nenhum arquivo do workspace sai — os payloads carregam um workspace e workdirs temporários. Nada é persistido.
- **Provider fixado.** Cada nó executa exatamente o provider do plano: se ele não for roteável o nó termina `no_route`, e se estiver indisponível termina `provider_failure` sem tentar fallback, para que um nó nunca troque de especialista em silêncio.
- **Relações de workspace.** `.forge/config/workspace.toml` é configuração do repositório, portanto não confiável: só declara relações `depends_on` entre repositórios já descobertos, nunca concede trust nem altera policy, e entradas inválidas são ignoradas com aviso.

## Diagnóstico de debug
Nenhum erro mostra traceback na CLI, nem em erro interno inesperado (exit 70). Com `--debug`, a CLI imprime em stderr, como linhas `theforge: debug:`, um `Diagnostic` (`theforge/Diagnostic/v1`): estágio, código, família, tipo e mensagem do erro, cadeia de causas e quadros como `módulo:função:linha`.

- Mensagem e causas passam por `security.redact`.
- Só entram quadros de módulos do pacote `theforge`; quadros de outras bibliotecas, de providers ou de adapters são omitidos. Não há caminhos absolutos nem variáveis locais, e o texto bruto do traceback nunca é guardado.
- Num run de `ask` ou `plan` que termina em erro interno, o diagnóstico só é gravado como artefato `diagnostic` do run quando `--debug` é pedido.
- Nas saídas de texto e JSON, um traceback que apareça dentro de um detalhe (por exemplo, o fim do stderr de um provider) é reduzido a `[traceback omitted] <última linha>`.

## Integridade de runs e âncora de confiança
`theforge explain` e `theforge replay --mode verify` recalculam, sem escrever nada e sem iniciar providers, cada hash que o receipt registrou (entradas, rodadas de contexto, resultado, telemetria, verificação, handoff e, em runs de plano, as referências do plano e o receipt de cada nó contra o hash gravado no `plan-result`), mais o sha256 de cada artifact declarado em `work/`. Divergência (`modified`, `missing`, `unreadable`) sai com exit 6.

- **O receipt é a âncora de confiança.** Quem consegue reescrever o run inteiro (receipt e artefatos, de forma coordenada) produz um run sem divergência: isso não é detectável sem uma âncora externa (assinatura ou registro fora do workspace), fora do escopo desta versão.
- Num plano, o receipt de cada nó é ancorado pelo `plan-result`, que é ancorado pelo receipt do plano.
- O artefato `diagnostic` e o próprio receipt não têm hash registrado. Artefatos presentes sem hash registrado (runs gravados antes de o hash existir) aparecem como `unrecorded`, nunca como divergência.
- `replay --mode execute` recusa reexecutar quando as entradas registradas (`task`, `routing`, `handoff`, contexto, receipt) divergem dos hashes, para que uma tarefa editada não rode com outros parâmetros.

## Ameaças da federação (ciclo 3.1)
A federação acrescenta superfícies novas — cada uma com a mitigação existente:

| Ameaça | Mitigação |
|---|---|
| Handoff malicioso de Doctor | O handoff é montado pelo core só de resultados válidos dos nós em `inputs`; `origin` é construída pelo core (provider não a forja); itens são tipados, redigidos e capados (256 itens / 256 KiB); claims são texto de até 500 caracteres — dado, nunca instrução. |
| Receipt aninhado adulterado | `provider_receipt` é só `{ref, sha256}` — um ponteiro, nunca conteúdo. Vive dentro do `result`, então adulterá-lo quebra o hash do resultado: `explain`/`replay --mode verify` reportam a divergência. |
| `native_trace.ref` falso | `ref` é validado por `check_ref`: forma `<scheme>:<id>` (scheme ≥ 2 letras — letra única é drive), sem espaço, `\` ou segmento `..`, e schemes reservados (`file`, `http(s)`, `ftp`, `ssh`, `data`, `javascript`, `theforge`, `forge`) são rejeitados no parse — um ref fora do namespace permitido invalida o resultado inteiro. O core nunca resolve nem abre refs: são rótulos para drill-down manual, não caminhos. |
| Spoof de fingerprint de superfície | `surface_fingerprint`/`capability_fingerprint` são **computados pelo core** sobre o manifest — o provider não os declara. `native_surface_fingerprint` é declarado, mas é informativo e nunca participa da identidade. `registry revalidate` compara `manifest_sha256` vivo com o em uso — mesma versão com superfície diferente resulta `changed`. |
| Injeção de graph-ref | Refs de grafos/traces/recibos são opacos e validados (`check_ref`); o core não mantém um resolver — nenhum ref vira caminho de filesystem nem URL buscada. |
| Falsificação de proveniência cross-provider | `origin` do item é construída pelo core do run real; `Evidence.derived_from` é conferido contra o handoff **entregue** (`handoff-provenance`): item não recebido, `node`/`plan_run` divergentes ou upgrade epistêmico falham a verificação `forge` do run. |
| Escalação de autoridade do planner interno | `SemanticPlanProposal` não carrega campos de orçamento/perfil: budget, teto de providers e limites vêm do perfil do comando; `check_plan` rejeita provider/capability desconhecida, ciclo e excesso de providers — a proposta é consultiva, a validação determinística é soberana. |
| Relaxação de policy por payload | Campos `policy`/`trust` contrabandeados num resultado são descartados pelo parse estrito/não-estrito e nunca chegam ao avaliador — policy lê só as dimensões declaradas do manifest e as regras de configuração; trust vem só do `providers.toml`. |

## Cadeia de suprimento
A identidade de superfície registra, por execução: o fingerprint do executável (`receipt.provider.fingerprint`, sha256 do binário resolvido), a versão do adapter (o `version` do manifest = `producer.version`), a versão observada do especialista (`provider.observed_version`) e os fingerprints de superfície (`surface_fingerprint`, `capability_fingerprint`, `native_surface_fingerprint` declarado). A deriva de qualquer um é detectável: cache do registry valida todos antes de servir, `revalidate` reporta `changed`, e o histórico de performance é escopado por fingerprint.

Hash de wheel não é coletado: após a instalação, o hash do artefato original não está disponível offline de forma confiável, e o fingerprint do executável + fingerprints de superfície + versões já cobrem a detecção de adulteração local. Hash é integridade, nunca confiança — a confiança vem do `providers.toml` e do trust gate, não de um digest.

## Níveis de trust
Trust só é concedido no `providers.toml` do usuário. Detalhes e justificativa em [ADR 0010](adr/0010-policy-model.md).

| Nível | Routing | `local_mutation` | Observação |
|---|---|---|---|
| `builtin` | sim | `allow` | reservado ao core (só o eco embutido) |
| `trusted` | sim | `allow` | |
| `local` | sim | `ask` | roda, mas pede aprovação para mutação local |
| `unverified` | só com `--allow-unverified` | `ask` | padrão; nunca entra no cache |
| `blocked` | nunca | — | filtrado antes da policy; nunca executa |

- Um `providers.toml` de projeto (`.forge/config/providers.toml`) com `trust` acima de `unverified` é rebaixado para `unverified`, com aviso. Sem `--allow-unverified`, o provider aparece como `untrusted` e não é executado (nem `describe`).
- Além da policy, `trusted` e `local` só diferem no desempate quando vários providers declaram a capability pedida com `--capability` (`builtin < trusted < local < unverified`, depois id). A intenção futura é que `trusted` acumule garantias adicionais (por exemplo, identidade forte); se nenhuma se justificar, os dois níveis serão fundidos (ADR 0010).

## Policy e risco
Antes de iniciar o provider, o core decide `allow`, `ask` ou `deny` e grava o artefato `risk` (`RiskAssessment` v1) no run.

- Dimensões: `read_only`, `local_mutation`, `external_read`, `external_mutation` e `destructive` vêm do `operation_class` declarado (só a classe declarada é `yes`); `execution.requires_network = true` força `external_read = yes`. `credentials` e `cross_account` ficam `unknown`.
- Vale a regra mais severa (`allow < ask < deny`) entre as dimensões `yes`. Nenhuma dimensão `yes`, ou regra ausente, resulta em `deny`.
- Regras padrão: `read_only = allow`, `local_mutation.builtin = allow`, `local_mutation.trusted = allow`, `local_mutation.local = ask`, `local_mutation.unverified = ask`, `external_read = ask`, `external_mutation = ask`, `destructive = deny`.
- Configuração: tabela `[rules]` em `policy.toml` no diretório de configuração do usuário (pode afrouxar ou endurecer) e em `.forge/config/policy.toml` (só endurece). A regra aplicada é registrada como `<origem>.<chave>`, com origem `default`, `user` ou `project`.
- `ask` sem aprovação: `refused` com `FORGE-POLICY-APPROVAL-REQUIRED` e `unlock = --approve <capability>`. Com `theforge ask … --approve <capability>`, vira `allow` e o run registra `approved: true`. `deny`: `refused` com `FORGE-POLICY-DENIED`; `--approve` não desbloqueia.
- O `RiskAssessment` sempre registra `source: provider_declaration` e a limitação `operation_class is a provider declaration, not sandbox enforcement`.
- **Hierarquia (ciclo 3.1):** a mais restritiva vence entre quatro camadas — a policy global da Forge, o `operation_class` declarado pela capability, a policy interna do especialista e o boundary dos Doctors. Cada camada só pode endurecer: `.forge/config/policy.toml` só endurece sobre a do usuário, a estimativa de `plan` só endurece sobre a classe declarada, e uma decisão interna do especialista só pode recusar mais cedo — nada abaixo do core relaxa um `deny`. O stop segue a mesma direção: o timeout/kill da árvore do subprocesso do nó é o teto absoluto; políticas internas de stop/recovery do especialista operam dentro dele e nunca o estendem.

## Limitações de isolamento
Não há sandbox. Detalhes e pesquisa por plataforma em [ADR 0012](adr/0012-os-sandbox-research.md).

- **O cwd não é sandbox.** O core escolhe o diretório de trabalho (temporário em describe e health, `.forge/runs/<id>/work` em execute), mas o provider lê e escreve no home e em todo o filesystem com as permissões do usuário, incluindo arquivos de credenciais (`~/.aws`, `~/.ssh`), mesmo sem as variáveis de ambiente.
- **`operation_class` é declaração, não enforcement.** A policy confia no que o provider declara; nada impede um provider de mutar além do declarado.
- **O fingerprint não cobre código importado.** Só o executável e os arquivos do `argv` entram; módulos importados não ([ADR 0013](adr/0013-provider-identity.md)). A revalidação por describe antes do execute compensa em parte. O hash do manifest não prova identidade.
- **O bloqueio de rede dos testes não cobre processos filhos.** Ele atua dentro do processo do pytest; um provider iniciado pelos testes pode acessar a rede.
- **POSIX:** um descendente que sai do grupo de processos (`setsid`, daemonização) escapa do kill da árvore.
- **Windows, modo degradado:** se o Job Object não puder ser criado ou atribuído, o kill usa `taskkill /T /F`, que não alcança um neto órfão cujo pai já terminou. O neto sobrevive, mas a chamada continua limitada (timeout + 2 s de graça + até 5 s de join das pipes).
- **Adapters reais:** a contenção do estado nativo é feita pelo adapter, não pelo core, e o especialista continua com acesso ao filesystem inteiro. No Spark Forge AWS, cada execute roda num processo filho para que o journal nativo (`.sparkforge/traces.db`, gravado também no `atexit`) seja fechado antes da limpeza. Depurar uma falha nativa exige reexecutar, porque o estado nativo é apagado.
- **Routing por sinais genéricos:** uma dependência ou keywords genéricas declaradas por **um único** provider confiável ainda podem vencer um provider mais específico, porque distinguir sinal genérico de específico exigiria conhecimento de domínio no core. A mitigação é o trust: só providers configurados pelo usuário roteiam.

## Ameaças do registry e da federação de metadados (ciclo 4)

Fontes externas (`http`, `a2a`, `mcp`) entregam **metadados não confiáveis**. Nenhuma delas pode criar trust, identidade ou roteabilidade local — trust continua vindo só do `providers.toml` do usuário, e um candidato remoto nunca entra no routing sem instalação explícita e aprovada ([remote-discovery](remote-discovery.md), [provider-distribution](provider-distribution.md)).

| Ameaça | Mitigação | Limite |
|---|---|---|
| Registry malicioso / poisoning | fonte opt-in e desabilitável; documento decodificado de forma tolerante mas validado por contrato (`RegistryDocument` v1); entradas malformadas viram dados inválidos, nunca exceção | o core não pode distinguir um registry comprometido que sirva entradas *válidas* — por isso nada disso concede trust |
| Impersonação de publisher | `PublisherIdentity` é declaração, não prova; candidatos remotos são sempre `unverified` por construção; popularidade do registry não é sinal de trust | identidade forte exige assinatura verificada (futuro — ver §Assinaturas) |
| Dependency confusion / package substitution / typosquatting | `DistributionRef` declara tipo + coordenadas + `sha256`; o `InstallationPlan` v2 pinna versão e carrega `expected_hashes`; aprovação explícita (`--approve`) obrigatória; plano é *plan-only*, nunca executa | hash prova **identidade de conteúdo**, não segurança — um artefato com hash correto pode continuar malicioso |
| Spoofing de assinatura | `SignatureRef` é metadado carregado para o stage `verify` do plano; nenhuma verificação local é fingida — sem verificação, a assinatura não conta como garantia | verificação real pesquisada em §Assinaturas |
| Publisher comprometido / versão stale vulnerável | reads carregam provenance + freshness (`retrieved_at`, `from_cache`, `stale`); metadado expirado é servido como `stale`, nunca como fresco; o plano registra versão e hash fixos | o core não conhece CVEs — stale é informado, a decisão é do usuário |
| Mismatch manifest/distribuição | `manifest_sha256` em `entry.hashes` + `distribution.sha256` entram em `expected_hashes`; divergência quebra o plano antes de qualquer execução | — |
| Injeção via descrição/nome de metadado | nomes e descrições de fontes remotas são **dados**: tamanho limitado, redigidos por `security.redact`, slugificados quando precisam virar id; nunca chegam a um prompt ou shell | o core não executa instruções contidas em metadados — eles não entram em `argv` nem em prompts do core |
| Cache de registry adulterado (ciclo 4) | envelope de cache com `body_sha256` verificado na leitura; cache fora do workspace; `THEFORGE_NO_NETWORK=1` desliga qualquer leitura remota | quem escreve no próprio home está fora do modelo |
| Agent Card A2A malicioso | card é documento: decodificado com limites (`_MAX_SKILLS`, `_MAX_PARTS`, tamanho de strings), `entry_from_card` produz no máximo um candidato `unverified`; descrições passam por redação; auth é HTTP-layer, nunca vira trust Forge | agentes A2A nunca executam — são metadados para discovery |
| Identidade A2A/MCP forjada | `RemoteProviderCandidate.trust` é fixo em `unverified`; MCP servers ficam num tipo separado (`McpServerEntry`) que não entra no grafo de providers | — |
| Histórico de performance/enconomia envenenado | `provider-performance.json` e `observations.jsonl` falham fechado: malformado → warning + ignorado; contagens impossíveis (`ok > runs`) violam o contrato; observações conflitantes do mesmo `(run_id, provider, capability)` viram `conflict` explícito, nunca média silenciosa | conteúdo *válido* fabricado é dado local confiável — o arquivo de métricas está no workspace do usuário |
| Recomendação com história rasa/fabricada | challenger frio ou sem runs verificados nunca é recomendado; `ShadowRecommendation.advisory` é `True` por contrato — nenhum caminho a promove | — |
| Superfície mudada com história antiga | história é escopada por `surface_fingerprint`; fingerprint novo → `stale`, e o score antigo não responde pela superfície nova | — |
| Manifest malicioso | todo manifest passa pela validação de contrato (ops obrigatórias, ids únicos, padrões de id); campos extras de resultado/payload são descartados antes de qualquer decisão | — |

### Assinaturas (pesquisa, §82)

Não inventamos criptografia. A pesquisa cobriu os três ecossistemas propostos:

- **Sigstore** (cosign/signing a blob com identidade OIDC + Rekor): é o caminho escolhido como *alvo* — verificação offline-deferred, identidade baseada em OIDC, transparência via log público. No core stdlib-only, a verificação real exige dependências — então hoje `SignatureRef` carrega `algorithm`/`key_id`/`signature`/`signed` como metadado declarativo, e o `InstallationPlan` v2 reserva o stage `verify` para um verificador externo opcional.
- **Package index signatures** (PEP 691/PEP 740-style, por índice): boa para distribuições `pip-package`; mesma política — metadado carregado, verificação delegada.
- **GitHub artifact attestations**: útil quando a distribuição já sai de GitHub Actions; mesmo slot `SignatureRef`.

Decisão: **carregar metadado de assinatura hoje, verificar por verificador externo opcional depois** — nunca fingir verificação local com crypto caseira. Detalhes no [ADR 0043](adr/0043-security-hardening.md).

### Registries de organização

Catálogos privados e ambientes air-gapped são suportados pelo mesmo mecanismo de fontes: `kind: "local-file"` para catálogo versionado no repositório da organização (sem rede), ou `http` apontando para o registry interno — ambos read-only, explícitos e desabilitáveis. Nenhum catálogo corporativo precisa de tratamento especial: a fronteira de trust é a mesma.


## Ameaças do controle adaptativo (Cycle 4.1)

| Ameaça | Mitigação |
|---|---|
| Provider tenta decidir o stop global | Provider output é dado; somente o core produz `GlobalStopDecision/v1`. O receipt do plano ancora o hash do artefato. |
| Provider declara artificialmente “sem ganho” | Information gain é calculado pelo core a partir de unknowns, capability/verification e policy; texto do provider não é instrução de controle. |
| Poisoning de ROI | Context ROI é escopado por provider + capability + surface fingerprint + task family; métricas ausentes permanecem unknown/limitation e história fria não recomenda redução. |
| História antiga após mudança de provider | Mudança de `surface_fingerprint` separa a série histórica e marca experimentos incompatíveis como `stale`. |
| Auto-promoção de challenger | `StrategyExperiment/v1` nunca promove automaticamente; estado `promoted` exige `approval_sha256` e estados governados exigem rationale. |
| Native trace como caminho/URL | `NativeTrace.ref` é opaco; schemes dereferenceáveis/reservados e traversal são rejeitados e o core nunca abre/faz fetch do ref. |


| Ameaça | Mitigação |
|---|---|
| Retry amplification | `max_attempts` é limitado a 1..5; o pior caso é reservado em `RunBudget.provider_calls`, cada execute real entra na telemetria e a ampliação fica explícita em `adjustments`. |
| Promotion by assertion | `promoted` exige hash de aprovação governada; texto do provider/registry nunca é aprovação. |
