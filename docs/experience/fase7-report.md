# FASE 7 — the-forge: relatório de experiência

> Objetivo da fase: entregar o hub do ecossistema — discovery, roteador
> agentico, one-command setup, host launch, TUI, federação, manual PT-BR
> e E2E multi-forge real.

## Estado

**Concluída.** Evidência abaixo.

## O que foi implementado

### 1. Hosts AI (`src/theforge/hostflow.py`)

O the-forge já detectava hosts por evidência (`hosts list|status`) e
ativava integração (`hosts activate`). Faltava a camada operacional dos
irmãos — adicionada:

- `theforge hosts observe [host]` — recibo por host: binário
  (`shutil.which`), versão (`<bin> --version`), login via subcomando
  oficial (`claude auth status`, `devin auth status`,
  `codex login status`; copilot reporta `logged_in: null` — sem comando
  de status documentado) e integração do workspace via
  `install.service.status` (drift `unverified` sem ledger — honesto).
- `theforge hosts launch <host>` — abre UM host herdando o terminal.
  Recusas nomeadas: `host_absent`, `login_required` (com `login_hint`),
  `no_tty`. O recibo nunca carrega saída de auth (pode listar caminhos
  de credencial).
- `render.hosts_flow` — saída textual dos estados.

Testes: `tests/test_hosts_flow.py` (8 testes) portado do platform-forge
— todo passo injetável (`which`/`runner`/`exec_host`); nada toca binário
real. Registrado em `conftest.py FILE_MARKERS` (`unit`/`security`/`integration`).

### 2. Documentação PT-BR

Cinco receitas novas em `docs/learn/recipes/` (formato problema →
solução → por quê → quando → quando não → saída esperada → verificação
→ limitações → erros comuns → uso por agentes):

`instalar-theforge`, `ask-router`, `hosts-observe-launch`,
`federacao-multi-forge`, `tui-command-center`.

Índice `docs/learn/README.md` atualizado; `docs/hub/hosts.md` ganhou a
seção "Observação e launch". Rationale: `hosts observe` e `hosts launch`
com folhas próprias em `command-rationale.json`. Regen: divergência
zero, `check_docs` 0 problemas em 251 arquivos.

## E2E real — workspace multi-forge (`E:\projetos\FORJAS`)

O próprio monorepo serve de workspace: `.forge/` inicializado, 7
checkouts irmãos com `forge.agentic.json`.

| Passo | Evidência |
|---|---|
| `forge init` | `.forge/` com `config`, `cache`, `delegations`, `runs` |
| `forge specialists list` | **7 forjas descobertas** com manifesto agentico e checkout real; estado `DEGRADED` honesto onde o CLI não está no PATH ("install_root missing and cli not runnable") |
| `forge agents list` | 8 agentes AgentSpec/v1 com autoridade fechada e budget de contexto |
| `forge doctor` | checks reais (os, architecture, python 3.14.6, git, host, workspace `.forge/`) |
| `forge ask "analisar o contrato openapi"` | **RoutingDecision/v1 real**: `api-forge api.analyze` selecionado por 2 tipos de sinal (file_globs + keyword `openapi`), confiança alta; executou de verdade e propagou a **recusa nomeada do provider** (`AF-OPENAPI-UNSUPPORTED-VERSION`: openapi deve ser 3.1.x, encontrado 3.0.0) com `unlock` — roteamento e fronteira de erro funcionam ponta a ponta |
| `forge task plan "analyze pyspark"` | argv real por provider — incluindo bootstrap por checkout (`python -c sys.path.insert`) quando o CLI da forja não está instalado |
| `forge task run --provider spark-forge-aws --target <fixture>` | **COMPLETED, exit 0, 2053ms** — `analyze pyspark` real no fixture: extrator `pyspark_ast@0.1.0` achou `dataframe_writer_v1` com proveniência + sha256 do artefato |
| `forge graph --federated` | view local **235 nós / 595 arestas** (`forge/ForgeGraphView/v1`), merge por namespace; notas honestas por provider (`PF-GRAPH-NOGRAPH`, `SF-GRAPH-NO-INDEX`, `ModuleNotFoundError: typer` onde o produtor precisa do venv da forja) |
| `forge hosts observe` | claude/devin/codex `SUPPORTED` com versões reais (2.1.295, 3000.11.3, 0.160.0), integração `unverified` honesta; copilot `NOT_DETECTED` |

## Limitações honestas

- Especialistas aparecem `DEGRADED` quando o CLI da forja não está no
  PATH — o discovery reporta, não esconde; `task run` contorna via
  bootstrap por checkout quando possível.
- Produtores de grafo federado rodam no interpretador do the-forge —
  forjas cujo produtor precisa de deps próprias (ex.: `typer`) reportam
  nota explícita em vez de falhar o merge.
- Copilot: `logged_in: null` — não há subcomando de status documentado.
- `hosts launch` exige TTY e um host explícito; `observe` é read-only.
- `ask` executa a delegação — sem `--use`/aprovação explícita a rota é
  da máquina; o plano (`task plan`) é a fronteira humana de revisão.

## Gates

| Gate | Resultado |
|---|---|
| `tests/test_hosts_flow.py` | 8 passed |
| `check_docs` | 0 problemas (251 arquivos) |
| divergência | 0 missing, 0 undocumented |
| rationale | `hosts observe`/`hosts launch` com folhas próprias |
| ruff | limpo nos arquivos tocados |
| paridade cross-forge | `test_experience_parity` 4/4 — i18n canônico promovido (`diff_old`/`diff_new`) e re-vendored aos 6 irmãos; inventário `ai` do spark-forge-aws re-gerado |
| **suíte integral** | **4853 tests, 1 failure** (junitxml) — `test_examples_use_canonical_cli` flagrou o alias `forge` nos blocos shell das receitas novas; corrigido para `theforge` canônico, rerun focado verde. Skipped: 7 |
