# ADR 0057 — Loop Factory como fila operacional de specs

- Status: aceito (2026-10-08)

## Contexto

A camada agentic entrega resultado, mas a entrada de trabalho ainda era informal:
"pedir algo ao agente" não deixava fila visível, gate de decisão explícito nem
trilha de verificação por tarefa. Loop Factory resolve exatamente isso: cada
tarefa é um spec em Markdown e a pasta onde ele mora é o estado
(`inbox → active → archive`). A fronteira dele — automatizar implementação e
verificação, nunca decisões de produto — é a mesma fronteira que os trust/approval
gates do core impõem na execução.

## Decisão

- Adotar o `loop-factory` CLI como ferramenta de desenvolvimento
  (`pip install -e` a partir do checkout; zero dependência de runtime — o core
  segue stdlib-only).
- `factory/specs/` é versionado: o spec é a fonte de verdade da tarefa.
- `factory/prompts|runs|reviews|logs` são artefatos de auditoria gerados e
  ficam fora do git (`.gitkeep` preserva a estrutura).
- O grill gate (`grill: completed` ou seção `# Grill Gate` preenchida) é
  pré-requisito de dispatch — no modo autônomo specs sem gate são reportados
  "needs grilling", nunca respondidos por agente.
- `archive --accepted` é decisão humana: o loop para no review, sempre.
- `verification:` nos specs aponta para os gates reais do repo (pytest, ruff,
  mypy, `audit_assets.py`) — verificação independente é a evidência.
- Coexistência com Kiro: Loop Factory é a fila operacional de tarefas pequenas e
  verificáveis; `.kiro/specs/` segue para features com spec completa em 3 fases.

## Consequências

- Toda tarefa passa a ter prompt gerado, run record e review registrados —
  reproduzível e auditável, alinhado com `planned != observed`.
- Direção de produto continua explícita e humana: specs malformados param no
  grill gate, não viram código por acidente.
- Specs podem referenciar a camada agentic (`forge-*` skills, agentes) sem
  duplicar autoridade — o loop opera dentro da autoridade fechada de cada papel.
