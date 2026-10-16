---
id: cyc101-07
title: security-dependency-closure
status: inbox
created: 2026-10-15
owner: the-forge
scope: ecosystem
cycle: "10.1"
wave: 5
priority: p0
risk: medium
agent: devin
source: prompt_evo_cycle10.1.md §9 (GAP 07), §11 Wave 5
verification:
  - python scripts/check_gates.py --pytest
---

# Auditoria de segurança e dependências nos commits do baseline

## Escopo

Auditar nos 9 repos (§9):

- Dependências Python (pip-audit/uv audit) e npm (npm audit) — lockfiles inclusos.
- Vulnerabilidades publicadas; revalidar `cryptography` no api-forge atual.
- SBOM existente ou gerar; licenças das dependências.
- Tokens/secrets: scan de histórico atual (gitleaks ou equivalente offline).
- GitHub Actions: permissões, pin de actions por SHA, `permissions:` mínimos.
- MCP permissions declaradas vs. exercidas.
- Portal local: loopback, command execution, path traversal, symlink escape.
- Prompt injection / agent escalation: superfícies agentic já auditadas — reexecutar.
- Supply chain: integridade de artefatos, proveniência.

## Registro por finding

Vulnerabilidade · severidade · pacote · versão · exploitability · correção ·
regressão · risco residual — em `docs/certification/cycle-10.1/security.md`.

## Regras

- Não bloquear releases por findings irrelevantes sem justificativa técnica.
- Nunca ignorar silenciosamente falha crítica — escalar.
- Deep scan apenas quando permissões disponíveis; registrar o que não rodou.

## Aceite

- security.md com tabela de findings (ou zero-findings comprovado por ferramenta
  + saída), risco residual e pendências explícitas.
