# ADR 0054 — AgentSpec: autoridade fechada, sem auto-escalonamento

- Status: aceito (2026-10-08)

## Contexto

O prompt agentic (§18-32, §43-50, §70-74) pede agentes especializados:
router, discovery, negotiator, installer, planner, orchestrator de execução,
orchestrator de verificação, debugger. O risco central de qualquer sistema
de agentes é escalonamento de autoridade — um agente que aprova o próprio
plano, concede trust ou pula verificação é um confused deputy por
construção.

## Decisão

`AgentSpec/v1` (`src/theforge/contracts/agent.py`, registry
`src/theforge/agents.py`) torna a autoridade uma propriedade do contrato:

- `authority` é literal fechado: `propose`, `classify`, `advise`,
  `execute-approved`. Não existe autoridade "approve" — aprovação é gate
  humano/policy, não uma classe de agente.
- `UNIVERSAL_FORBIDDEN = (grant-trust, approve, waive-verification,
  modify-registry)` — toda spec é obrigada a declará-los como forbidden;
  omitir quebra a construção. Trust, aprovação, bypass de verificação e
  escrita no registry são portas que nenhum agente abre.
- `check_authority` aplica três paredes em ordem: universal forbidden →
  `forbidden_actions` da spec → teto da classe de autoridade. Uma ação que
  o teto não alcança é negada mesmo se a spec esquecer de proibir.
- `execute-approved` alcança `install`/`execute` somente porque o plano
  aprovado já existe — `bootstrap-installation` tem `verify` forbidden:
  quem instala nunca verifica o próprio trabalho.
- O vocabulário de ações é fechado (`KNOWN_ACTIONS`): ações desconhecidas
  falham a validação, então uma spec não pode inventar `become-root`.
- `context_budget_bytes`/`max_skills` são bounded por construção — nenhum
  agente recebe o repo inteiro por default (§34-35).

## Consequências

- A matriz de não-escalonamento é testável: `check_authority` é pura e a
  suíte cobre todas as specs contra todas as ações universais.
- Um arquivo `wrong.toml` declarando `id` diferente falha — filename e
  identidade são a mesma coisa.
- Agents delegam *trabalho bounded*; nunca *decisão de produto* nem *gates*.
