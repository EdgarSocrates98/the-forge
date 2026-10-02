# The Forge — Ciclo 1: Discovery, Forge Protocol v1 e Core Local

- Data: 2026-10-02
- Status: aprovado em brainstorming, aguardando revisão do spec
- Escopo: Fases 0, 1 e 2 do `prompt_evo_inicial.md` (§65–§67)
- Fora de escopo: adapters reais Spark/API (ciclo 2), LLM, multi-provider, economy avançada, installer, workspace graph, forge-doctor

## 1. Problema

Spark Forge (`sparkforge-aws`) e API Forge (`apiforge`) são especialistas maduros e independentes. Falta uma entrada única que descubra especialistas, escolha o certo de forma explicável e registre evidência verificável — sem duplicar conhecimento de domínio e sem acoplar por import.

## 2. Goals / Non-goals

Goals:
- Forge Protocol v1 versionado, agnóstico de linguagem, provado por um provider nativo (echo-forge).
- Core local determinístico: registry, capabilities, routing explicável, ContextPack, run store, receipts.
- Falhas de provider degradam explicitamente; nunca falso sucesso.
- Funciona offline, stdlib-only em runtime.

Non-goals:
- Routing de domínio (cada Forge mantém seu `next-step`).
- `forge-kernel` compartilhado.
- LLM em qualquer etapa.
- Mudanças nos repos Spark Forge / API Forge.

## 3. Fase 0 — Achados da auditoria (main de ambos, 2026-10-02)

Legenda: C = confirmed (código lido), O = observed (docs), I = inferred.

### 3.1 Spark Forge (`sparkforge-aws` 0.5.0)
- Python >=3.10; deps core: PyYAML, jsonschema. CLI `sparkforge` (argparse, 53 verbos). (C)
- Todo comando imprime JSON em stdout; erros texto PT em stderr; exit 0/1 (gate)/2 (uso). (C)
- `--version` texto puro; nenhum verbo emite manifest de capabilities. (C)
- `parity.yaml`: 82 capabilities sem id estável; `manifest.json`: 52 skills, ~120 MCP tools. (C)
- Primitivas maduras: `next-step` + `routing.yaml`, context gateway (perfis economy/balanced/deep, `ctx://v1`), receipts sha256, journal hash-chained, policy allow/ask/deny, codeintel SQLite. (C)
- Riscos: monólitos `_core.py`/`tools.py`; segunda CLI não exposta (`sparkforge/cli/forge.py`) com `doctor` divergente; dois modelos de capability; estado em `.sparkforge/`. (C)

### 3.2 API Forge (`apiforge` 0.1.0)
- Python `>=3.12,<3.13`; deps pesadas obrigatórias (pydantic, typer, tree-sitter, cryptography). CLI `apiforge` (~235 handlers). (C)
- JSON default em stdout (`--output json|compact`); erros `AF-CODE: detail (field=…; unlock=…)` texto em stderr; exits 0/2/3/4. (C)
- `capabilities list` → `CapabilityRecord/v1`, 21 ids com state supported/heuristic/unresolved/unsupported. (C)
- Contratos `VersionedContract` (frozen, extra=forbid): TaskSpec, RoutingPlan, ContextCapsule, BudgetEnvelope, Receipt `af-receipt/1`, Policy com AutonomyClass. (C)
- Três convenções de versão coexistem (`version` int, `apiforge/*/v1`, `af-*/1`). (C)
- Efeito colateral: todo emit JSON grava `<cwd>/.apiforge/economy.jsonl`. (C)
- Risco: loader de `knowledge/` provavelmente quebra em instalação via wheel. (C código / I efeito)

### 3.3 Matriz de capacidades

| Capability | Spark Forge | API Forge | Classificação |
|---|---|---|---|
| JSON stdout | todos verbos | default | protocol concern |
| Erro estruturado | ⊥ (texto PT) | texto `AF-CODE` | protocol gap → adapter parseia |
| Version | texto | texto | protocol gap |
| Capability listing | sem ids | 21 ids + state | protocol concern |
| Health | `doctor` | `doctor`/`inspect` | cross-domain |
| Routing interno | `next-step` | `next-step` + RoutingPlan | domain-specific — não duplicar |
| Context/budget | gateway + perfis | ContextCapsule/BudgetEnvelope | potential kernel concern |
| Receipts/evidence | sha256 + journal | af-receipt + Ed25519 | potential kernel concern |
| Policy | allow/ask/deny | allow/gate/deny + autonomy | potential protocol concern |
| Graph/impact | codeintel | graph build/impact | domain-specific (por ora) |
| Workspace multi-repo | manifest v1 | WorkspaceManifest/v1 | potential kernel concern |
| Python | >=3.10 | ==3.12 | isolamento obrigatório |
| Side effects cwd | `.sparkforge/` | `.apiforge/` | adapter controla cwd |

Conclusões:
1. Conceitos convergem, schemas divergem → protocolo primeiro, sem kernel (§11).
2. The Forge seleciona provider; não roteia domínio.
3. Vocabulário do API Forge (CapabilityRecord state, tríade code/field/unlock) é semente do protocolo — como vocabulário, não como código.

## 4. Decisões

| Decisão | Escolha | Alternativas rejeitadas |
|---|---|---|
| Transporte | exec-protocol: subprocess + JSON stdin/stdout | MCP (dep, async, acoplado a host); entry points in-process (import coupling, conflito 3.10 vs 3.12) |
| Integração legada | adapters externos dentro do The Forge (ciclo 2) | protocolo nativo nos especialistas; manifest estático commitado |
| Linguagem/deps | Python >=3.11, zero deps runtime (argparse, dataclasses, tomllib) | pydantic; typer |
| Nome | pacote `theforge`; console scripts `theforge` + alias `forge` | só `forge` (colide com Foundry e Laravel Forge) |
| Routing | determinístico; ambiguidade → `ambiguous`, sem chute | LLM fallback (adiado) |

## 5. Forge Protocol v1

### 5.1 Invocação
`<argv do provider> <op>`; request JSON em stdin; response JSON em stdout (um documento cada).
- Exit 0 sempre que houver response de protocolo válida (inclusive `refused`).
- Exit ≠0, stdout não-JSON, stdout > 8 MB ou timeout → falha de transporte → `provider_failure`.

### 5.2 Ops
- `describe` (obrigatória) → `ForgeManifest`.
- `health` (obrigatória) → `{status: ok|degraded|unavailable, checks[]}`.
- `execute` → `ExecutionResult` para capability + action + ContextPack.
- Reservadas, declaráveis, não implementadas no core neste ciclo: `plan`, `verify`, `estimate`.
- Provider declara ops suportadas em `describe.ops` (capability negotiation mínima).

### 5.3 Envelopes
```json
{"protocol":"forge/v1","kind":"Request","op":"execute","request_id":"r_…","payload":{}}
```
```json
{"protocol":"forge/v1","kind":"Response","request_id":"r_…",
 "producer":{"id":"echo-forge","version":"0.1.0"},
 "status":"ok|partial|refused|error",
 "payload":{},
 "error":{"code":"…","detail":"…","field":null,"unlock":null},
 "limitations":[],"unknowns":[]}
```
- `request_id` da response ≠ request → `provider_failure` (`FORGE-PROTO-MISMATCH`).
- `error` obrigatório quando status ∈ {refused, error}.

### 5.4 Versionamento
- `describe.protocols` lista majors suportados; core escolhe maior major comum.
- Sem major comum → provider `incompatible`, excluído do routing.
- Campos desconhecidos ignorados na leitura (forward-compat intra-major).
- Breaking change → novo major.

### 5.5 Segurança do transporte
- `argv` como lista; nunca `shell=True`.
- Timeouts: `describe`/`health` 10 s; `execute` conforme perfil (economy 60 s, balanced 180 s, max 600 s).
- Env por allowlist (`PATH`, `HOME`/`USERPROFILE`, `SYSTEMROOT`, `TEMP`/`TMP`, `LANG`, `PYTHONIOENCODING`); credenciais não repassadas.
- cwd = `.forge/runs/<run_id>/work`.
- `execute` recebe `workspace_root` e lista de paths permitidos via ContextPack.

## 6. Contratos v1

Cabeçalho comum de contrato persistido: `schema` (`theforge/<Name>/v1`), `producer{id,version}`, `created_at` (UTC ISO-8601), `status`, `limitations[]`, `unknowns[]`. Hash = sha256 sobre JSON canônico (`sort_keys=True`, `separators=(",",":")`, `ensure_ascii=False`, UTF-8).

| Contrato | Campos |
|---|---|
| ForgeManifest | id, version, protocols[], ops[], domains[], capabilities[], execution{local, offline, requires_network}. `trust` atribuído pelo registry, nunca lido do manifest. |
| Capability | id (`^[a-z][a-z0-9-]*(\.[a-z][a-z0-9-]*)+$`), actions[] (≥1), default_action (∈ actions), state (supported\|heuristic\|unresolved\|unsupported), operation_class (read_only\|local_mutation\|external_read\|external_mutation\|destructive), signals, description |
| Signals | keywords[], file_globs[], dependencies[] — declarados pelo provider |
| TaskSpec | id, intent, requested_capability?, requested_action?, workspace_root, targets[], budget_profile (economy\|balanced\|max), constraints{} |
| RoutingDecision | task_id, candidates[{provider, capability, matched{dependencies[], file_globs[], keywords[]}, rank_key}], selected[{provider, capability, action, role: primary\|specialist}], pattern (`route`), reason, confidence{level: high\|low, measured_signals[], unresolved[]}, fallbacks_used[] |
| ContextPack | task_id, provider_id, root, files[{path, sha256, bytes, reason}], budget_bytes, used_bytes, truncated, excluded[{path, reason}] |
| ExecutionResult | status, findings[], artifacts[{path, sha256}], evidence[], metrics{duration_ms, context_bytes, tokens} — cada métrica `{value, kind: measured\|estimated\|unknown}` |
| Evidence | id, epistemic (confirmed\|observed\|inferred\|proposed\|unresolved), subject, claim, location{path, line?}, hash?, producer, limitations[] |
| ExecutionReceipt | run_id, forge_version, inputs{task_sha256, context_sha256, routing_sha256}, provider{id, version, trust, manifest_sha256}, result_sha256?, started_at, finished_at, outcome (ok\|partial\|refused\|provider_failure\|ambiguous\|no_route) |

Reservados (nome registrado, sem implementação): ExecutionPlan, VerificationResult, Budget, RiskAssessment, GraphNode, GraphEdge, InstallationPlan, DecisionRecord, WorkspaceDescriptor, EnvironmentReport.

Regras:
- `schemas/*.json` = artefato publicado; dataclasses = implementação; contract test garante paridade.
- Redactor de secrets roda antes de qualquer persistência.

## 7. Componentes

```text
src/theforge/
├── cli/          argparse; parsing + render; sem lógica
├── contracts/    dataclasses, validação, JSON canônico, hash
├── protocol/     envelopes, SubprocessTransport, negociação
├── registry/     fontes, refresh via describe, cache, trust
├── routing/      matcher determinístico + explain
├── context/      Context Broker → ContextPack
├── forger/       orquestração task→route→context→execute→receipt
├── runs/         run store, receipts
├── environment/  doctor
├── security/     redaction, env allowlist, guardas de path/symlink
└── providers/echo/   echo-forge nativo (`python -m theforge.providers.echo`)
```

Interface interna: `ProviderTransport.call(op, payload) -> Response`. `SubprocessTransport` é a única implementação neste ciclo; adapters do ciclo 2 implementam a mesma interface.

### 7.1 Registry
- Fontes (precedência crescente por id): builtin (echo-forge) → usuário (`providers.toml` em `%APPDATA%\theforge\` / `$XDG_CONFIG_HOME/theforge/`) → projeto (`.forge/config/providers.toml`).
- Entrada: `id`, `argv[]`, `trust`.
- `registry refresh`: `describe` em cada provider, valida, grava `.forge/registry/<id>.json` com `manifest_sha256`.
- Trust: builtin\|trusted\|local\|unverified\|blocked. `unverified` listado, fora do routing salvo `--allow-unverified`. `blocked` nunca executado. Default de entradas sem trust explícito: `unverified`.
- Cache corrompido → descartado com aviso, refresh do provider.

### 7.2 Context Broker
- Seleciona `targets ∩ file_globs` do provider; ordena por (nº de globs casados desc, path asc); corta em `budget_bytes` (economy 64 KB, balanced 256 KB, max 1 MB).
- Rejeita: symlink resolvendo fora do root, componentes `..`, arquivos de secret (`.env*`, `*.pem`, `*.key`, `id_rsa*`, `id_ed25519*`, `*.pfx`, `credentials*`).
- Ignora: `.git`, `.forge`, `node_modules`, `.venv`, `venv`, `__pycache__`, `dist`, `build`.
- Exclusões registradas em `excluded[]`.

### 7.3 Estado `.forge/`

| Dir | Classe | Git |
|---|---|---|
| `config/` | persistent | committable |
| `registry/` | cacheable | ignorado |
| `runs/<run_id>/` (task, routing, context, result, receipt `.json` + `work/`) | persistent local | ignorado |
| `cache/` | ephemeral | ignorado |

`theforge init` cria `.forge/.gitignore` ignorando tudo exceto `config/` e o próprio `.gitignore`.

`run_id` = `YYYYMMDDTHHMMSSZ-<8 hex>`.

### 7.4 CLI (ciclo 1)
`init`, `doctor`, `status`, `registry list|show <id>|refresh`, `capabilities list|search <q>`, `providers health`, `ask "<texto>" [--capability id] [--action a] [--profile p] [--target path]... [--allow-unverified]`, `explain <run_id>`. Todos aceitam `--json` para saída máquina; default = texto humano.

## 8. Fluxo `ask` e routing

```text
ask → TaskSpec → snapshot registry (trust, protocolo, blocked)
    → RoutingDecision → health(selecionado) → ContextPack
    → execute(timeout) → valida → ExecutionResult + Evidence
    → ExecutionReceipt → resumo + run_id
```
Cada artefato persistido ao ser produzido.

Routing:
1. `--capability` presente → match exato; múltiplos providers → desempate trust rank (builtin > trusted > local > unverified) → provider id asc; desempate registrado.
2. Ausente → por par (provider, capability) coletar sinais casados:
   - dependencies: nomes de `pyproject.toml` (`[project].dependencies`, `[tool.poetry.dependencies]`), `requirements*.txt`, `package.json` (`dependencies`, `devDependencies`) no root;
   - file_globs sobre arquivos sob targets;
   - keywords sobre intent normalizado (lowercase, NFKD sem acento, tokens `\w+`).
3. rank_key = (nº tipos casados, n deps, n globs, n keywords), ordem desc; capabilities `unsupported` excluídas.
4. Confiança `high` ⇔ vencedor único em rank_key ∧ ≥2 tipos casados. Senão `low` → outcome `ambiguous`, lista candidatos, sugere `--capability`. Zero candidatos com sinal → `no_route`.
5. Action = `requested_action` ∨ `default_action`; action ∉ actions → erro de uso.
6. Selecionado com health `unavailable` → próximo candidato com mesmo rank tipo ≥2; registrado em `fallbacks_used`. Sem alternativa → `provider_failure`.

## 9. Erros e exit codes

| Situação | Comportamento | Exit |
|---|---|---|
| Sucesso / partial | resumo explícito | 0 |
| Uso inválido | mensagem | 2 |
| no_route / ambiguous | candidatos + diagnóstico | 3 |
| Timeout, crash, JSON malformado, schema inválido, major incompatível, request_id divergente | `provider_failure` com código `FORGE-*`; receipt gravado | 4 |
| `refused` | repassa code/field/unlock | 4 |
| Falha ao persistir (disco, permissão) | erro stderr; nada reportado como sucesso | 5 |

Invariante: nenhum caminho reporta sucesso sem ExecutionResult válido.

## 10. Testes

- Unit: contratos, canonical hash, routing (rank, desempate, confiança), broker (budget, symlink, `..`, secrets), redaction, parsing de deps.
- Conformance (`tests/conformance/`, parametrizada por argv): describe válido, negociação, health, execute, request inválido, capability não suportada → refused, major incompatível. Roda contra echo-forge; reusável no ciclo 2.
- Failure modes: `bad-forge` de fixture com modos timeout, crash, garbage, oversize, wrong-major, invalid-manifest, request-id-mismatch; provider ausente do PATH; cache corrompido; `.forge/` sem permissão.
- Fixtures de routing: `fixture-spark` / `fixture-api` (scripts mínimos, capabilities derivadas da auditoria) cobrindo §80 casos A e B + caso ambíguo.
- E2E: CLI via subprocess em workspace temporário: init → registry refresh → capabilities list → ask → explain.
- Golden: snapshot de `explain`.
- Offline: fixture autouse bloqueando `socket.socket.connect`.
- Property-based (`hypothesis`, dev): canonical JSON estável; redaction idempotente.

## 11. Quality gates

pytest verde · ruff · mypy --strict · paridade schemas↔dataclasses · fresh install (venv novo, `pip install .`, `theforge doctor`) · zero deps de runtime (teste lê `pyproject.toml`).

## 12. ADRs (`docs/adr/`)

0001 exec-protocol vs imports/MCP · 0002 JSON + convenção única de schema · 0003 Python >=3.11 stdlib-only · 0004 sem forge-kernel · 0005 routing determinístico, sem LLM no ciclo 1 · 0006 registry local + trust · 0007 ContextPack por referência · 0008 nome `theforge` + alias `forge`.

## 13. Docs

README (onboarding §61), `docs/architecture.md` (Mermaid), `docs/protocol.md`, `docs/provider-authoring.md`, `docs/security.md` (threat model resumido: provider malicioso, manifest adulterado, path traversal, symlink, injeção de shell, vazamento de credencial, stdout gigante), `docs/cli.md`, `CLAUDE.md` curto.

## 14. Critérios de aceite

1. Instalação limpa; `theforge doctor` reporta ambiente + providers.
2. `registry refresh` descobre echo-forge e fixtures; `capabilities list|search` funcionam.
3. `ask` roteia casos A e B deterministicamente e explica; caso ambíguo → `ambiguous`, exit 3.
4. Run grava TaskSpec, RoutingDecision, ContextPack, ExecutionResult, Evidence, Receipt; `explain` reconstrói decisão.
5. Todos failure modes de §10 degradam explicitamente; zero falso sucesso.
6. Conformance suite verde contra echo-forge.
7. Suite completa verde offline.
8. Secret plantado no workspace não aparece em nenhum artefato persistido.

## 15. Riscos e unknowns

- Overhead de processo por op (~100–300 ms) — aceitável no MVP; medir em ciclo 2.
- Mapeamento de capabilities do Spark Forge exigirá ids sintetizados pelo adapter (parity.yaml sem ids) — ciclo 2.
- Packaging do `knowledge/` do API Forge em wheel possivelmente quebrado — afeta ciclo 2.
- Keywords em PT e EN dependem da qualidade dos sinais declarados pelos providers.

## 16. Processo

`git init` em `the-forger/`; commits pequenos (§83); sem push, release ou publish.
