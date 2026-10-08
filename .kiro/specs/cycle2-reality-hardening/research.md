# Research & Design Decisions — cycle2-reality-hardening

## Summary
- **Feature**: `cycle2-reality-hardening` (Wave A — Hardening + CI)
- **Discovery Scope**: Extension / Complex Integration (núcleo existente + CI novo + endurecimento de segurança)
- **Key Findings**:
  - Contratos validam tipos e Literals, mas nenhuma invariante relacional (IDs únicos, referências, paths de artifact, formato de hash, consistência receipt↔result). `from_dict` ignora campos desconhecidos.
  - Transporte mata apenas o processo filho direto; `execute` é chamado sem checar `ops`; `producer` só é comparado (id) no resultado de execute; describe/health herdam o cwd do chamador.
  - Cache do registry fica em `.forge/registry` dentro do workspace, auto-hasheado (detecta corrupção, não falsificação); `trusted` e `local` só diferem no desempate de routing; não há CI.

## Research Log

### Estado do core (auditoria 2026-10-02)
- **Context**: base para todas as decisões da Wave A.
- **Sources Consulted**: leitura direta de `src/theforge/**`, `tests/**`, `pyproject.toml`, `docs/**` (tokensave MCP indisponível).
- **Findings**:
  - `contracts/base.py:24` `from_dict` ignora chaves desconhecidas; `ContractError(ValueError)` é o único erro de contrato; `__post_init__` só verifica schema e poucas regras locais.
  - `contracts/result.py` — `Evidence`, `Finding.evidence_ids`, `Artifact{path, sha256}` sem validação; `ExecutionResult.status ∈ {ok, partial}`.
  - `protocol/transport.py:86` `_run`: `Popen` + 3 threads de bombeamento; limites 8 MiB stdout / 64 KiB stderr; timeout via `proc.wait`; `proc.kill()` apenas no filho direto.
  - `forger/orchestrator.py:124` fluxo `_run`: records → scan → route → `_select_healthy` → context → execute → `from_dict(ExecutionResult)` → checagem `producer.id` → persist → `_finish`.
  - `orchestrator._fallback_order:224` pode escolher candidato de **outra capability** (só filtra por ação).
  - `routing/router.py:107` `rank_key=[types, len(deps), len(globs), len(kws)]` sem teto; `MIN_SIGNAL_TYPES=2`; estados `heuristic`/`unresolved` tratados como `supported`.
  - `registry/registry.py:119` cache em `forge_dir/registry/<id>.json`; `_read_cache:140` revalida hash armazenado junto (auto-referente).
  - `security/env.py:6` allowlist: PATH, PATHEXT, SYSTEMROOT, SYSTEMDRIVE, WINDIR, COMSPEC, HOME, USERPROFILE, TEMP, TMP, TMPDIR, LANG, LC_ALL + `PYTHONIOENCODING`, `PYTHONUTF8`.
  - Códigos `FORGE-*` são literais inline em `transport.py`, `health.py`, `orchestrator.py`.
  - `tests/conftest.py:8` já bloqueia `socket.connect/connect_ex` (autouse); só existe marker `slow`; nenhum `.github/`.
- **Implications**: hardening deve ser aditivo (validadores relacionais separados), preservar Protocol v1 e mover constantes de erro para um único lugar.

### GitHub Actions e matriz de Python
- **Sources Consulted**: https://github.com/actions/checkout, https://github.com/actions/setup-python, https://raw.githubusercontent.com/actions/python-versions/main/versions-manifest.json, https://www.python.org/downloads/
- **Findings**: `actions/checkout@v7` e `actions/setup-python@v7` são as versões maiores atuais; Python 3.14 é GA (3.14.8); 3.15 só com `allow-prereleases`. Checkout de repositórios irmãos via `repository:` + `path:`; repositórios privados exigem token de secrets. `persist-credentials: false` evita deixar token em `.git/config`.
- **Implications**: matriz Linux+Windows × 3.11–3.14; 3.15 fora; workflow de providers reais separado (`workflow_dispatch` + `schedule`), `permissions: contents: read`, token só nos steps de checkout.

### Bloqueio de rede em testes (stdlib)
- **Sources Consulted**: https://github.com/miketheman/pytest-socket, https://pypi.org/project/pytest-socket/
- **Findings**: monkeypatch de `socket.socket.connect`/`connect_ex`, `socket.create_connection`, `socket.getaddrinfo` cobre `urllib`/`http.client`/`ssl`/asyncio; não cobre processos filhos; bloquear loopback quebra `socketpair` no Windows; fixtures de escopo maior rodam antes de autouse de função → aplicar em `pytest_configure`/sessão.
- **Implications**: endurecer `conftest.py` (sessão, permitir loopback, bloquear DNS externo, marker `allow_network`); limitação de filhos documentada; providers de teste recebem `safe_env()` (sem variáveis de proxy).

### Encerramento de árvore de processos (stdlib)
- **Sources Consulted**: https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_basic_limit_information, docs de `subprocess`
- **Findings**: POSIX: `start_new_session=True` + `os.killpg` (TERM → graça → KILL). Windows: Job Object via `ctypes` com `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`; `taskkill /T /F` como fallback (perde órfãos). `Popen.kill()` nunca mata descendentes. Manter handle do job vivo enquanto o processo existir.
- **Implications**: novo módulo `protocol/proctree.py` stdlib-only (`ctypes` é stdlib) isolando a lógica por plataforma.

### Diretório de cache por usuário
- **Sources Consulted**: https://raw.githubusercontent.com/tox-dev/platformdirs/main/src/platformdirs/windows.py, XDG Base Directory spec
- **Findings**: Windows `%LOCALAPPDATA%\<app>\Cache`; macOS `~/Library/Caches/<app>`; Linux `$XDG_CACHE_HOME/<app>` (se absoluto) ou `~/.cache/<app>`.
- **Implications**: `user_cache_dir()` com override `THEFORGE_CACHE_DIR`, espelhando `user_config_dir()` existente.

### Variáveis de ambiente com credenciais
- **Sources Consulted**: https://docs.aws.amazon.com/sdkref/latest/guide/settings-reference.html, https://docs.python.org/3/library/os.path.html
- **Findings**: categorias AWS_*, GH_TOKEN/GITHUB_TOKEN/ACTIONS_*, SSH_AUTH_SOCK, GOOGLE_APPLICATION_CREDENTIALS/CLOUDSDK_*, AZURE_*/ARM_*/TF_TOKEN_*, proxies com userinfo, tokens de registries, KUBECONFIG/DOCKER_CONFIG/NETRC, padrões genéricos `*_TOKEN`, `*_SECRET*`, `*_PASSWORD`, `*_API_KEY`. Python filho precisa de `HOME` (POSIX) / `USERPROFILE` (Windows) para `Path.home()`; `SYSTEMROOT` é obrigatório no Windows (Winsock). Limpar env não protege arquivos de credenciais no home.
- **Implications**: manter allowlist (já não repassa nenhuma dessas variáveis), adicionar filtro de padrões como defesa em profundidade, manter `HOME`/`USERPROFILE` com justificativa documentada e explicitar que o home real permanece legível (cwd ≠ sandbox).

### Sandbox de SO (pesquisa, não implementação)
- **Findings**: Linux — bubblewrap (binário externo, namespaces), `os.unshare` (3.12+, requer user namespaces), Landlock (5.13+, via ctypes), seccomp (complexo). macOS — `sandbox-exec` marcado deprecated, ainda funcional. Windows — Job Objects (limites e kill-tree, sem isolamento de FS/rede), AppContainer (forte, complexo), restricted tokens (moderado).
- **Implications**: ADR de pesquisa; nada obrigatório no ciclo; Job Object usado apenas para kill-tree.

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Notes |
|--------|-------------|-----------|---------------------|-------|
| Invariantes dentro de `__post_init__` | Toda validação relacional nos dataclasses | Impossível construir objeto inválido | `from_dict` reembrulha em `ContractError` genérico → perde código específico exigido (1.1–1.4) | Usado só para regras locais/estruturais (formato de hash) |
| Validador relacional separado (`contracts/integrity.py`) | Funções puras que retornam/lançam erro com código | Códigos específicos, reutilizável por receipts/runs/futuros adapters | Exige chamada explícita nos pontos de entrada | **Selecionado** |
| Policy embutida no router | Decisão de risco junto com routing | Menos arquivos | Mistura WHO com governança; dificulta reuso por ExecutionPlan (Wave D) | Rejeitado |
| Pacote `policy/` dedicado | `evaluate()` puro + construção de `RiskAssessment` | Testável isoladamente, consumível por Waves B/D | Novo pacote | **Selecionado** |

## Design Decisions

### Decision: Validação relacional separada com códigos próprios
- **Context**: 1.1–1.8 exigem códigos de erro específicos; `from_dict` perde a origem.
- **Alternatives Considered**: 1) tudo em `__post_init__`; 2) módulo `integrity` chamado nos pontos de entrada.
- **Selected Approach**: formato de hash validado em `__post_init__` (estrutural, gera `FORGE-PROTO-SCHEMA`); invariantes relacionais em `contracts/integrity.py` levantando `IntegrityError(ContractError)` com `code`.
- **Rationale**: preserva o parser genérico e dá códigos estáveis.
- **Trade-offs**: dois lugares de validação; mitigado por documentação e testes por invariante.

### Decision: Política de campos desconhecidos
- **Context**: 1.10.
- **Selected Approach**: `from_dict(..., strict=True)` para contratos lidos pelo core a partir de artefatos que ele mesmo produziu (runs, cache do registry); providers continuam tolerantes (forward compatibility do Protocol v1). Schemas publicados de contratos produzidos só pelo core (`TaskSpec`, `RoutingDecision`, `ContextPack`, `ExecutionReceipt`, `RiskAssessment`) passam a declarar `additionalProperties: false`.
- **Rationale**: endurece o que o core controla sem quebrar providers existentes.

### Decision: Revalidação dos candidatos antes da decisão final de routing (revisada)
- **Context**: 4.3 exige detectar cache adulterado e redescobrir **antes de rotear**. A versão inicial revalidava só o provider selecionado, depois do routing. A revisão independente mostrou que uma entrada adulterada de um provider não selecionado podia forçar empate ou mudar a ordem de fallback.
- **Alternatives Considered**: 1) HMAC com chave local (quem tem escrita no home também lê a chave); 2) TTL; 3) re-describe só do selecionado; 4) re-describe de todos os candidatos que pontuaram.
- **Selected Approach**:
  - O cache vai para o diretório de cache do usuário, fora do alcance do conteúdo do projeto.
  - Depois do primeiro `route()` com status `routed` ou `ambiguous`, todos os candidatos que pontuaram passam por describe.
  - Uma divergência invalida as entradas e refaz `records`/`route` uma única vez.
  - O artefato `routing` só é gravado depois da decisão final.
  - A escrita do cache usa `mkstemp` + `os.replace`, e uma falha nela vira aviso.
- **Trade-offs**: uma chamada describe por candidato pontuado, em geral 1 ou 2, com timeout de 10 s.

### Decision: Isolamento do cache nos testes
- **Context**: o cache global faria os testes escreverem no `~/.cache` real, e a ordem dos testes passaria a importar (finding 2 da revisão).
- **Selected Approach**: uma fixture autouse define `THEFORGE_CACHE_DIR` por teste. A checagem de producer fica nos chamadores, e `ProviderTransport.call` mantém a assinatura, o que preserva os fakes existentes.

### Decision: Diferença concreta entre `trusted` e `local`
- **Context**: 4.2 — hoje só desempate.
- **Selected Approach**: a diferença passa a ser de policy: `local_mutation` → `allow` para `builtin`/`trusted`, `ask` para `local`. Ranking de desempate mantido.
- **Rationale**: conecta trust a governança observável sem novo conceito.

### Decision: Decisão por presença de tipos de sinal (revisada)
- **Context**: 3.2, 3.5, 3.11. A versão inicial limitava cada tipo de sinal a 3 ocorrências e descartava globs que casavam com uma fração alta dos arquivos. A revisão independente mostrou três problemas:
  - um provider de spam ainda vencia no case_a (`[3,1,3,3]` contra `[3,1,1,2]`);
  - abaixo de 20 arquivos a regra de fração nunca disparava;
  - um repositório Glue legítimo perdia o glob e o routing virava `ambiguous`.
- **Selected Approach**:
  - A decisão usa só `types_matched`, um bit de presença por tipo. As contagens servem apenas para explicação, e empate em tipos dá `ambiguous`.
  - Um sinal comum a todos os candidatos que pontuaram é não discriminante. A regra é entre providers e não depende do tamanho do workspace.
  - Globs catch-all são rejeitados estaticamente no manifest.
  - O manifest tem limites de declaração.
  - Capabilities sem `execute` em `ops` não são roteáveis.
- **Rationale**: declarar mais sinais nunca aumenta o score. A regra é determinística, agnóstica de domínio e não depende do tamanho do repositório.
- **Trade-offs**: mais casos `ambiguous` quando dois providers casam os mesmos tipos. Isso é aceitável, porque ambiguidade não pode virar chute.

### Decision: Policy pela regra mais severa entre as dimensões
- **Context**: um `read_only` com `requires_network` era liberado com `allow` enquanto o RiskAssessment registrava `external_read=yes` (finding 4).
- **Selected Approach**: `evaluate` recebe `RiskDimensions` e aplica a regra mais severa entre as dimensões marcadas `yes`.

### Decision: Constantes de erro em `contracts/codes.py`
- **Context**: o plano anterior criava um ciclo de import entre `errors` e `integrity` (finding 7).
- **Selected Approach**: `contracts/codes.py` fica no ponto mais à esquerda da cadeia de dependências, e `errors.py` só o reexporta.

### Decision: Schemas fechados só para artefatos que não cruzam o protocolo
- **Context**: `TaskSpec` e `ContextPack` vão até os providers dentro do `ExecuteRequest` e vão evoluir na Wave C (finding 8a).
- **Selected Approach**: `additionalProperties: false` só em `RoutingDecision`, `ExecutionReceipt` e `RiskAssessment`. Os demais ficam rígidos via `from_dict(strict=True)` quando o core os relê.

### Decision: Confiança permanece `high`/`low`
- **Context**: 3.7 é opcional e exige semântica objetiva.
- **Selected Approach**: não introduzir `medium`. Capabilities `heuristic`/`unresolved` rebaixam a confiança para `low` e aparecem em `Confidence.unresolved`; `Candidate` ganha `state`.
- **Rationale**: evita classificação cosmética (diretriz do prompt §19).

### Decision: Kill de árvore de processos
- **Selected Approach**: `protocol/proctree.py` — POSIX: nova sessão + `killpg`; Windows: Job Object (`ctypes`, `KILL_ON_JOB_CLOSE`) com fallback `taskkill /T /F`.
- **Trade-offs**: código específico de plataforma; isolado e coberto por teste com neto que dorme.

### Decision: CI
- **Selected Approach**: `ci.yml` (PR/push: Linux+Windows × 3.11–3.14, ruff, mypy, pytest offline, paridade de schemas, packaging/fresh install, zero-deps); `compat.yml` (semanal + manual: macOS × 3.11/3.14); `real-providers.yml` (manual + semanal, não bloqueante, checkout de `spark-forge-aws` e `api-forge`). 3.14 entra no gate por ser GA; 3.15 fica fora até GA.

## Synthesis Outcomes
- **Generalização**: os pontos de entrada de dados de provider (describe, health, execute) passam todos por uma mesma sequência "envelope → contrato → integridade → producer"; implementada uma vez em `forger`/`registry` usando `integrity`.
- **Build vs. adopt**: kill-tree, cache dir, bloqueio de rede e checagem de deps implementados com stdlib (runtime precisa ficar sem deps); `build` (PyPA) e `hypothesis` adotados apenas como dev-deps; `pytest-socket` rejeitado (conftest stdlib já existe e cobre o necessário).
- **Simplificação**: sem nível `medium`; sem HMAC; sem TTL; sem sandbox; `RiskAssessment` deriva só da declaração do provider; policy configurável só por arquivo de usuário (projeto só pode endurecer).

## Risks & Mitigations
- O describe extra por `ask` aumenta a latência. Mitigação: só os candidatos que pontuaram (normalmente 1 ou 2), com timeout curto, e o custo é medido no baseline (Wave C).
- Launchers de console scripts no Windows (distlib, redirectores de venv) podem escapar do Job Object. Mitigação: `CREATE_SUSPENDED`, atribuição ao job e só então resume.
- Em POSIX, a nova sessão desliga o Ctrl-C dos filhos. Mitigação: `kill_tree` em todo `finally`.

## Design Review Log
- 2026-10-02, revisão adversarial independente com o código como referência: NO-GO condicional e 8 findings.
  - Os três críticos: routing ainda vulnerável a volume, cache global quebrando o isolamento dos testes, e revalidação feita depois do routing.
  - Os outros cinco eram ajustes curtos de design.
  - O usuário aprovou aplicar todas as correções, e elas estão nas decisões revisadas acima e no `design.md`.
- Job Object via `ctypes` pode falhar em ambientes com job pai restritivo — fallback `taskkill /T /F` e teste que tolera degradação registrando limitação.
- Endurecer validação pode rejeitar resultados de providers existentes — echo/fixtures atualizados no mesmo PR; política tolerante para campos desconhecidos de provider mantida.
- Matriz 3.14 pode expor incompatibilidade de dev-deps — job marcado como gate, falha investigada com `kiro-debug`.
- Bloqueio de rede não cobre filhos — documentado; providers de teste rodam com `safe_env()` sem proxies e não fazem I/O de rede.

## References
- `docs/adr/0006-local-registry-and-trust.md`, `docs/adr/0007-context-pack-by-reference.md`, `docs/security.md`, `docs/protocol.md`
- https://github.com/actions/checkout — checkout multi-repo, `persist-credentials`
- https://github.com/actions/setup-python — matriz de versões
- https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_basic_limit_information — Job Objects
- https://docs.aws.amazon.com/sdkref/latest/guide/settings-reference.html — variáveis AWS
- https://docs.python.org/3/library/os.path.html — dependência de HOME/USERPROFILE

## Implementation Log (Wave A)
- **2.8 routing — decisões além do design (aceitas na revisão)**:
  - O vencedor precisa ser também o topo único por presença bruta, com os sinais compartilhados incluídos. Caso contrário o resultado é `ambiguous`. Sem essa regra, um provider que copia os sinais de outro e acrescenta extras venceria ao "esvaziar" o original.
  - Custo: um provider legítimo cujos acertos formam um superconjunto estrito dos de um rival genérico também cai em `ambiguous`.
  - A regra de sinal não discriminante compara providers (qualquer capability do provider) e só vale com pelo menos 2 providers distintos.
- **Lacuna escalada**:
  - (a) A detecção de catch-all só reconhece as formas literais. Fica decidido ampliá-la para "glob sem nenhum caractere alfanumérico literal é catch-all" (`?*`, `**/?*`), no escopo da tarefa 4.1.
  - (b) Uma dependência ou keywords genéricas declaradas por um único provider *configurado pelo usuário* ainda podem vencer um provider específico que casa 2 tipos. Isso não tem solução determinística sem conhecimento de domínio, que o core não pode ter. Fica como limitação documentada, mitigada pelo trust: providers de projeto são `unverified` e não roteiam por padrão.
