# Repository baseline — Cycle 0.5

Data da coleta: 2026-11-08 (America/Sao_Paulo)
Workspace: `E:\projetos\FORJAS`  
Ambiente de execução: Windows; PowerShell; Python 3.14.6; Node.js v24.16.0;
npm 12.0.2; uv 0.12.23. Os projetos Python continuam testados com seus
ambientes `uv` e restrições declaradas em cada `pyproject.toml`.

## Referências observadas

| Repository | URL | Branch/HEAD observado | Pacote / versão | Manifest | Runtime | Estado local | Riscos iniciais |
|---|---|---|---|---|---|---|---|
| api-forge | `github.com/EdgarSocrates98/api-forge` | `main` / `72b8304a801a` (igual a `origin/main`) | `apiforge-af` 0.3.2; `apiforge.__version__=0.3.2` | `forge.json` `api-forge`; `forge.agentic.json` 0.3.2 | Python >=3.12 | 1 alteração local pré-existente | versão de pacote, manifest e protocolo continuam eixos distintos |
| forge-doctor-api | `github.com/EdgarSocrates98/forge-doctor-api` | `main` / `5c04fe78dc11` (igual a `origin/main`) | `forge-doctor-api` 0.3.1 | `forge.json` `forge-doctor-api`; manifest agentic 0.3.1 | Python >=3.11 | 1 alteração local pré-existente | múltiplos contratos ForgeRequest/ForgeHandoff exigem negociação explícita |
| data-sentinel-forge | `github.com/EdgarSocrates98/data-sentinel-forge` | `main` / `e222af87e000` (igual a `origin/main`) | `data-sentinel-forge` 0.5.2 | `forge.json` e manifest agentic 0.5.2 | Python >=3.11 | 3 documentos de benchmark/evaluation pré-existentes | manifest/roster agora é descoberto; adapter de execução The Forge ainda não é prova de diagnóstico externo |
| the-forge | `github.com/EdgarSocrates98/the-forge` | `main` / `547be2208ee0` (igual a `origin/main`) | `theforge-core` 0.7.4 | `forge.json` e contratos do control plane | Python >=3.11 | `.audit-work/` e `.codebase-memory/` pré-existentes | é o proprietário de descoberta, roteamento e governança; não deve executar domínio alheio |
| forge-agent-bridge | `github.com/EdgarSocrates98/forge-agent-bridge` | `main` / `83169b3d3347` (igual a `origin/main`) | `forge-agent-bridge` 0.2.1 | `forge.json` e `forge/AgentBridgeEvent/v1` | Python >=3.11 | `uv.lock` pré-existente | providers reais podem estar indisponíveis; eventos e retenção são P1 |
| code-atlas-forge | `github.com/EdgarSocrates98/code-atlas-forge` | `main` / `dda7c92998ff` (igual a `origin/main`) | `code-atlas-forge` 1.1.1 | `forge.json` e `forge.agentic.json` anunciam `code-atlas-forge`; CLI continua `code-atlas` | Python >=3.12 | `.codebase-memory/` e `uv.lock` pré-existentes | nome do distribuidor/CLI/provedor continua deliberadamente separado |
| forge-lens | `github.com/EdgarSocrates98/forge-lens` | `main` / `a5bba59c72d7` (igual a `origin/main`) | `forge-lens-fl` 0.2.1 | `forge.json` e manifest agentic 0.2.1 | Python >=3.11 | limpo | correlação opcional com Bridge deve preservar semântica dos traces |
| forge-portal | `github.com/EdgarSocrates98/forge-portal` | `main` / `91e4697bff24` (igual a `origin/main`) | `forge-portal-app` 1.1.1 | `package.json`/CLI `forge-portal`; não possui `forge.json` | Node/Angular 22; npm | capturas, relatórios, `.codebase-memory/` e auditorias visuais pré-existentes | PortalApi/1 é a fronteira; não se deve inferir um Forge especialista a partir do app |

## Superfícies públicas observadas

| Projeto | CLI/superfície principal | Testes e contratos existentes |
|---|---|---|
| API Forge | `apiforge` — capabilities, context, forge protocol, handoff, health | Forge Protocol v1, task/evidence/handoff; suíte API Forge executada anteriormente |
| Doctor API | CLI Doctor/API e SDK/handoff | `ForgeRequest`, `ForgeHandoff`, `ForgeReceipt`, `ForgeResult`, `ApiHandoffBundle`; suíte e gates de versão |
| Data Sentinel | `data-sentinel` — analyze, capabilities, doctor, report, lineage, spark, sql, mcp | manifest agentic, quality/lineage/evidence e adaptadores de diagnóstico |
| The Forge | `theforge`/`forge` — discovery, catalog, install, lab, receipts | contratos de instalação, experiência, manifest, receipts e replay adapters |
| Agent Bridge | `forge-bridge` — status, providers, doctor, sessions, serve | `forge/AgentBridgeEvent/v1`, sessões, replay, redaction e provider inventory |
| Code Atlas | `code-atlas` — index, search, graph, impact, federation, mcp | `DomainExtractionResult`, entidades/relacionamentos e fixtures de indexação |
| Forge Lens | `forge-lens` — traces, stats, capabilities, serve, mcp-serve, replay | contratos de traces, correlação, custos, security e MCP |
| Forge Portal | app Angular + `tools/portal-cli.mjs`; contrato de entrega `PortalApi/1` | testes Angular/CLI, deep visual gate, axe/reflow e adapters PortalApi |

## Estado do checkout

Os checks locais foram executados antes da coleta e repetidos para confirmar
HEAD/branch. Os diretórios `.codebase-memory/` são artefatos do inventário
estrutural, não alterações de produto. Não foram usados `reset`, `clean`, force
push ou merge direto em `main`.

## Limite desta linha de base

Este documento registra o estado observado, não uma aprovação de integração.
As declarações de adaptador, roteamento, telemetria e provider serão elevadas a
`IMPLEMENTED_AND_TESTED` somente após o laboratório local produzir evidência
real e reprodutível.
