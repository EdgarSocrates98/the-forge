# Repository baseline — Cycle 0.5

Data da coleta: 2026-11-07 (America/Sao_Paulo)  
Workspace: `E:\projetos\FORJAS`  
Ambiente de execução: Windows; PowerShell; Python 3.14.6; Node.js v24.16.0;
npm 12.0.2; uv 0.12.23. Os projetos Python continuam testados com seus
ambientes `uv` e restrições declaradas em cada `pyproject.toml`.

## Referências observadas

| Repository | URL | Branch/HEAD observado | Pacote / versão | Manifest | Runtime | Estado local | Riscos iniciais |
|---|---|---|---|---|---|---|---|
| api-forge | `github.com/EdgarSocrates98/api-forge` | `main` / `011129ce4bd7` | `apiforge-af` 0.3.2; `apiforge.__version__=0.3.2` | `forge.json` `api-forge`; `forge.agentic.json` 0.3.2 | Python >=3.12 | alterações geradas `.codebase-memory/` | versão e identidade precisam ser consumidas como conceitos distintos |
| forge-doctor-api | `github.com/EdgarSocrates98/forge-doctor-api` | `main` / `5c04fe78dc11` | `forge-doctor-api` 0.3.1 | `forge.json` `forge-doctor-api`; manifest agentic 0.3.1 | Python >=3.11 | alterações geradas `.codebase-memory/` | múltiplos contratos ForgeRequest/ForgeHandoff exigem negociação explícita |
| data-sentinel-forge | `github.com/EdgarSocrates98/data-sentinel-forge` | `main` / `a74f15f6dfa8` | `data-sentinel-forge` 0.5.2 | `forge.json` e manifest agentic 0.5.2 | Python >=3.11 | três documentos de benchmark/evaluation modificados pelo usuário | especialista declara superfície rica, mas adaptador The Forge ainda não está provado |
| the-forge | `github.com/EdgarSocrates98/the-forge` | `cycle-0.5-compatibility-hardening` sobre `main` / `5ba6753cd5ba` | `theforge-core` 0.7.4 | `forge.json` e contratos do control plane | Python >=3.11 | índice `.codebase-memory/` gerado | é o proprietário de descoberta, roteamento e governança; não deve executar domínio alheio |
| forge-agent-bridge | `github.com/EdgarSocrates98/forge-agent-bridge` | `main` / `963e09b42023` | `forge-agent-bridge` 0.2.1 | `forge.json` e `forge/AgentBridgeEvent/v1` | Python >=3.11 | `uv.lock` modificado localmente | providers reais podem estar indisponíveis; eventos e retenção são P1 |
| code-atlas-forge | `github.com/EdgarSocrates98/code-atlas-forge` | `main` / `9025ebfbc63e` | `code-atlas-forge`; versão exposta pelo módulo | `forge.json` anuncia `forge_id=code-atlas` | Python >=3.12 | `.codebase-memory/` e `uv.lock` não rastreados | identidade diverge do nome do repositório; precisa de adaptador/correção compatível |
| forge-lens | `github.com/EdgarSocrates98/forge-lens` | `main` / `a5bba59c72d7` | `forge-lens-fl` 0.2.1 | `forge.json` e manifest agentic 0.2.1 | Python >=3.11 | limpo | correlação opcional com Bridge deve preservar semântica dos traces |
| forge-portal | `github.com/EdgarSocrates98/forge-portal` | `main` / `5f8258d8eca7` | `forge-portal-app` 1.1.1 | `package.json`/CLI `forge-portal`; não possui `forge.json` | Node/Angular 22; npm | capturas, relatórios e auditorias visuais gerados modificados/não rastreados | PortalApi/1 é a fronteira; não se deve inferir um Forge especialista a partir do app |

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
