# FASE 8.2 — Jornadas de usuário: execução real

> Cada jornada foi executada com as ferramentas reais, não simulada.
> Estado por jornada: **VERIFIED** (evidência nesta sessão/programa),
> **PARTIAL** (etapa host-only documentada, não reproduzida) ou
> **UNVERIFIED**. Evidência detalhada nos relatórios de fase de cada repo
> (`docs/experience/faseN-report.md`).

## Jornada 1 — instalar Spark Forge AWS, abrir Devin, pedir análise

**VERIFIED** (etapa host manual por desenho).

- `./setup.sh` → bootstrap real, launcher `sparkforge-aws` no PATH.
- `sparkforge-aws install` num scratch repo → `completed`, status
  `healthy`, `.mcp.json` + 60 skills + mirrors nos diretórios de host.
- `devin mcp list` → server `sparkforge-aws` registrado nativamente.
- `sparkforge-aws ai devin` → `READY` (binário + versão + login +
  integração saudável). `ai devin --launch` abre o host real no TTY.
- Análise real: `analyze pyspark` no fixture extraiu
  `dataframe_writer_v1` com proveniência + sha256 (e também via
  `theforge task run` — COMPLETED, exit 0).

## Jornada 2 — instalar API Forge, abrir Claude, revisão de contratos

**VERIFIED** (mesma fronteira de host).

- `apiforge install apply` → recibo `completed`; `.mcp.json` com
  `apiforge`, 136 mirrors, AGENTS.md com bloco gerenciado.
- `devin mcp list`/`claude` host flow → READY/SUPPORTED.
- `apiforge analyze <contrato>` em fixture OpenAPI — findings reais;
  `contract diff` entre v1/v2 detecta breaking changes com evidência.

## Jornada 3 — instalar Platform Forge, abrir Codex, análise de infra

**VERIFIED** com limitação declarada.

- `platformforge install` → healthy; 12 skills + 41 agents mirror.
- `platformforge hosts` → claude/devin/codex SUPPORTED+READY.
- `analyze iac` num fixture Terraform real: finding `PF-IAC-003`
  violated; `graph build` → blast radius real
  (`db` → `eks_cluster.c` via `depends_on`, com nota correlação≠causação).
- **Limitação registrada:** Codex não lê `.mcp.json` de projeto —
  o recibo declara `mcp-scope:codex NOT_APPLICABLE`; usar
  `--scope user` ou `codex mcp add` (verificado no codex-cli 0.160.0).

## Jornada 4 — Forge Doctor Data diagnosticando um projeto

**VERIFIED.**

- `forge-doctor-data install` → healthy; `mcp-verify` handshake real
  (14 tools, invoke PASS).
- `scan .` num fixture de dados: **342 checks, 52 pass/17 info/3 warn/0
  error** com citação de regra.
- `hosts` → devin READY; `get_host_status` MCP read-only.
- `agent context` → contexto para host gerado.

## Jornada 5 — Forge Doctor API avaliando uma API

**VERIFIED.**

- `forge_install.py install` → `completed`/`healthy`.
- `scan .` num fixture FastAPI+OpenAPI: **21 findings reais**
  (APISEC001, APISEC011, DRIFT001).
- `diff api/v1 api/v2` → **2 BREAKING** (`POST /products` removido;
  param `id` string→integer) com cadeia de evidência.
- `blast-radius` → clientes afetados; `unknown` onde falta evidência.
- `mcp-verify` → handshake real, 17 tools; `devin mcp list` nativo.
- `forge_hosts.py` → 3 READY + copilot NOT_DETECTED honesto.

## Jornada 6 — The Forge: especialistas e tarefa multi-Forge

**VERIFIED** (workspace = o próprio monorepo).

- `theforge init` → `.forge/`; `specialists list` → **7 forjas**
  descobertas com manifesto agentico real; estado `DEGRADED` honesto
  onde o CLI não está no PATH.
- `theforge ask "analisar o contrato openapi"` → RoutingDecision/v1:
  `api-forge api.analyze` (2 tipos de sinal, confiança alta); executou
  e propagou recusa nomeada do provider
  (`AF-OPENAPI-UNSUPPORTED-VERSION`) — roteador e fronteira de erro
  funcionam ponta a ponta.
- `theforge task run --provider spark-forge-aws` → COMPLETED (exit 0,
  2053ms) via bootstrap por checkout — delegação real cross-forge.
- `theforge graph --federated` → view 235 nós/595 arestas + notas
  honestas por provider.
- `theforge agents list` → 8 agentes com autoridade fechada + budgets.

## Jornada 7 — Graph Studio para explorar impacto

**VERIFIED** (servidor real + federação real, sem browser).

- `theforge graph --federated --root E:\projetos\FORJAS --ui
  --no-browser` → `ThreadingHTTPServer` real em `127.0.0.1`; `curl`
  retorna a página Forge Graph Studio (canvas, painéis de inspeção,
  estilos por `epistemic_state`).
- Federação real no workspace FORJAS: **2 views emitidas** —
  `the-forge` (235 nós/595 arestas) e `forge-doctor-data` (16n/10e,
  via o interpretador do próprio checkout); **4 recusas nomeadas** —
  `PF-GRAPH-NOGRAPH`, `SF-GRAPH-NO-INDEX`, `SFA-GRAPH-NO-GRAPH`,
  `AF-GRAPH-NOT-FOUND`; 2 notas honestas (`the-forge` sem
  `cli_entry` por desenho; `forge-doctor-api` com dialeto
  `graph <alvo> --view` congelado no RC).
- platform-forge `graph view --ui` abre studio equivalente no
  scratch instalado.
- Limitação honesta: navegação em browser real não reproduzida nesta
  sessão headless — o servidor e o payload são reais; o clique humano
  fica para o operador.

## Jornada 8 — sem TUI, CI/headless

**VERIFIED.**

- Todo verbo crítico aceita `--json`/`--format json` (theforge,
  apiforge, sparkforge-aws, platformforge, doctor-data, doctor-api) —
  `capabilities list --json` emitiu o catálogo federado completo.
- TUIs recusam honestamente sem TTY (`home requires a TTY`,
  NonInteractive) — nunca degradam em silêncio.
- `hosts launch` recusa `no_tty`; `observe`/`status` seguem read-only.
- Contrato de paridade: `test_bare_entry_wired_with_headless_fallback`
  exige gate `isatty` nos 7 entrypoints.

## Resumo

| Jornada | Estado | Evidência-âncora |
|---|---|---|
| 1 Spark+Devin | VERIFIED | install healthy + `ai` READY + analyze real |
| 2 API+Claude | VERIFIED | install completed + analyze/diff real |
| 3 Platform+Codex | VERIFIED* | iac finding + blast real; *codex project-scope N/A declarado |
| 4 Doctor Data | VERIFIED | 342 checks reais + handshake |
| 5 Doctor API | VERIFIED | 21 findings + 2 breaking + handshake |
| 6 The Forge | VERIFIED | RoutingDecision + task COMPLETED + federação |
| 7 Graph Studio | VERIFIED | servidor 127.0.0.1 + payload real; browser manual |
| 8 Headless | VERIFIED | --json pleno + recusas no_tty honestas |
