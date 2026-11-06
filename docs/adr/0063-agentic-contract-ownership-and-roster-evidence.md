# ADR 0063 — ownership dos contratos agentic e evidência de roster

- Status: aceito para a resolução Goldfish (2026-11-06)

## Decisão

O contrato canônico de definição de agente permanece
`theforge/AgentSpec/v1`, de propriedade do The Forge, em
`src/theforge/contracts/agent.py`. A superfície declarativa de cada Forge
especialista permanece `forge/SpecialistAgenticManifest/v1`, de propriedade do
contrato de integração do The Forge, em
`src/theforge/contracts/specialist.py`. O termo “AgentSpec v2” usado no draft
não é um schema: é tratado como uma necessidade de composição até que uma
lacuna medida prove que uma extensão compatível não basta.

`forge.agentic.json` é um manifesto declarativo; não é um registry, não concede
trust e não transforma uma capability não observada em executável. Os rosters
nativos (`agentic/agents` ou `agents`) são evidência local comparada por
`theforge.agent_roster.inspect_roster`. A projeção pode ser
`CONFORMANT`, `DRIFT`, `STALE`, `CONFLICT` ou `UNKNOWN`; apenas o lifecycle,
health, trust e routing existentes promovem disponibilidade.

Projeções `.codex/agents` e `.claude/agents` não são novas autoridades. Um
adapter de host pode renderizar o mesmo AgentSpec e deve conservar id,
authority, contratos, limites e forbidden actions. Migração futura é aditiva:
primeiro atualizar `AgentSpec/v1`, manifest e adapter em conjunto, depois
adicionar testes de compatibilidade; nenhuma mudança silenciosa de schema é
permitida.

## Alternativas rejeitadas

1. Criar um `AgentSpec/v2` paralelo: duplicaria autoridade e quebraria a
   compatibilidade entre The Forge, Portal e hosts.
2. Fazer o catálogo possuir a verdade de execução: confundiria declaração,
   instalação, trust, frescor e health.
3. Preencher manifestos automaticamente com nomes de arquivos: mascararia
   drift e promoveria assets não verificadas.

## Consequências operacionais

- Catálogo e Portal exibem a projeção com fonte e evidência, preservando
  `UNKNOWN` quando o checkout não fornece roster verificável.
- Routing mantém gates de capability, estado, trust e health; roster
  inconclusivo é sinal de risco/explicação, nunca autorização.
- O teste de conformance é determinístico e cobre igualdade, drift, stale,
  conflito e ausência de evidência.
- Não há novo runtime, banco, transporte, ledger ou execução remota.
