---
id: cyc101-05
title: hosts-mcp-certification
status: inbox
created: 2026-10-15
owner: the-forge
scope: ecosystem
cycle: "10.1"
wave: 4
priority: p0
risk: high
agent: devin
source: prompt_evo_cycle10.1.md §6 (GAP 04), §11 Wave 4
verification:
  - python scripts/check_gates.py --pytest
---

# Certificação real de hosts (Codex/Claude Code/Devin/Copilot) e MCP

## Escopo

- §6.1 discovery por host: instalação, versão, escopos, arquivos de config, MCPs,
  skills, agents, suporte real às capacidades — nunca presumir paridade.
- §6.2 MCP: instalação, registro, init pelo host, handshake, tools/list,
  invocation, timeout, process exit, invalid payload, permissões, remoção,
  reinstalação. Separar "teste direto de protocolo" de "executado via host".
- §6.3 skills: caminho, descoberta, metadados, trigger, arquivos referenciados,
  contexto, compat de versão.
- §6.4 agents/subagents: descoberta, especialização, delegação, contexto, tools
  autorizadas, handoff, recusa, resultado, evidence, receipt.
- §6.5 cenário multiagent real: "analise projeto de API e infra" → host usa
  The Forge, descobre API Forge + Platform Forge, delega, correlaciona, reporta.
  Sem alterações destrutivas.
- §6.6 context economy: medir tokens/bytes/handoffs/latência quando possível;
  sem ganho sem comparação válida.
- §6.7 classificação por combinação: VERIFIED / PARTIAL / BLOCKED / UNSUPPORTED /
  NOT_TESTED. Ausência de host instalado → BLOCKED/NOT_TESTED, nunca PASS.

## Aceite

- `docs/certification/cycle-10.1/hosts-mcp.md` com matriz host × capacidade e
  evidência por célula. Só VERIFIED com execução real.
