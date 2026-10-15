---
id: cyc10-01
title: onboarding-golden-paths
status: inbox
created: 2026-10-15
owner: the-forge
scope: ecosystem
cycle: 10
wave: 4
priority: p2
risk: medium
agent: codex
source: prompt_evo_cycles.md §10.2, §10.3, §10.4
verification:
  - python scripts/check_gates.py --pytest
---

# Onboarding, Getting Started e Golden Paths

## Outcome

Jornada de primeiro uso (Discover→Install→Choose→Configure→Validate→First Task→Evidence→Advanced) sem exigir dezenas de comandos; guias Getting Started por perfil com as 8 seções obrigatórias; quatro Golden Paths reproduzíveis.

## Grill gate

- Problema observado: desenvolvedor externo não consegue instalar/usar sem conhecimento privado.
- Usuário afetado: novos usuários por perfil (backend, data AWS/Azure, platform, usuários de Claude Code/Codex/Devin/Copilot, CLI/TUI, Portal).
- Falha concreta: abandono no primeiro contato; "funcionou na minha máquina".
- Decisão: jornada única de onboarding + guias por perfil (pré-reqs, instalação, config, primeiro comando, resultado esperado, explicação, troubleshooting, próximos passos) + Golden Paths Spark AWS / API / Platform / Multi-Forge.
- Fora de escopo: validar exemplos manualmente quando automação for possível; promessas de uso sem experiência técnica.
- Critério de parada: desenvolvedor externo segue um Golden Path documentado, instala, executa cenário real e compreende o resultado — sem instruções privadas.

## Acceptance

- Onboarding unificado cobrindo os 8 estágios do §10.2.
- Guias por perfil (lista §10.3), cada um com as 8 seções obrigatórias e exemplos validados automaticamente quando possível.
- 4 Golden Paths demonstrando: instalação, seleção de especialista, diagnóstico, evidências, recomendações, testes, resultado.
- Validação dos exemplos em CI ou script reproduzível (não só documentação).

## Constraints

- Documentação reflete comportamento atual; links para fontes oficiais por repo.
- Sem depender de caminhos privados do desenvolvedor.

## Rejected

- Guia que exige conhecimento de dezenas de comandos no primeiro uso.

## Pending

- ⚠ Depende de cyc8-02 (instalação real como pacote) para os passos de Install.
- ⚠ Golden paths usam demos sintéticas (§10.11) — alinhar fixtures com cyc9-*.
