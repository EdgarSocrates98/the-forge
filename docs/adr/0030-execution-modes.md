# ADR 0030 — Modos avançados de execução: concorrência limitada, ordem canônica, decisão auditável

- Status: aceito (2026-10-07)

## Contexto

[ADR 0018](0018-multi-provider-execution.md) estabeleceu o plano sequencial
(`route`, `pipeline`). A spec do ciclo 3 (Wave E) pede os modos que a estrutura
permite: `delegate` (subtarefas independentes), `parallel` (nós concorrentes
por nível de dependência) e `debate` (proposers + referee com `DecisionRecord`
auditável). Cada modo estende o scheduling, não a semântica: os mesmos gates de
health, policy, contexto e verificação valem por nó.

## Decisão

- **Cinco padrões executáveis** (`route`, `pipeline`, `delegate`, `parallel`,
  `debate`); outros valores são `FORGE-PLAN-PATTERN-RESERVED`. O decompositor
  só emite `route`/`pipeline`; os demais entram por `--from FILE` ou proposta
  semântica validada — o core não inventa estrutura concorrente a partir de
  linguagem natural.
- **Concorrência por nível de dependência**: nós do mesmo nível rodam num
  `ThreadPoolExecutor` limitado a `MAX_PARALLEL_NODES = 4` — provider failure
  ou timeout num nó não segura nem contamina os irmãos (exceção do nó vira
  `outcome` do nó, nunca do plano).
- **Ordem canônica é topológica, sempre**: resultados são registrados na ordem
  topológica com desempate por id — nunca na ordem de conclusão — para que
  replay, explain e comparação de runs leiam a mesma sequência.
- **`delegate` proíbe dependência entre especialistas** (subtarefas seladas);
  **`debate` exige ≥2 `proposer` + 1 `referee`** que depende de todos e os
  declara em `inputs`. O referee recebe o handoff com outcome + findings +
  evidência + verificação de cada proposer.
- **`DecisionRecord/v1` é o desfecho do debate**: `question`, `options` (cada
  uma citando `position`, `evidence` e `risks` extraídos verbatim do resultado
  do proposer), `evidence` completa, `tradeoffs`, `chosen`, `rejected`,
  `rationale`, `confidence`, `unknowns`. Sem a evidência `id="decision"` do
  referee com a claim de um proposer, `chosen="unresolved"` — o core nunca
  decide o mérito.

## Consequências

- `provider_calls` e `handoff_bytes` sobem com o fan-out — medidos pela
  telemetria e pelo benchmark de runs, não assumidos.
- Um debate auditável responde "quem disse o quê" sem reexecução: posições,
  evidências e a razão do referee estão no artefato.
- Nó `skipped`/`blocked_by` e `FORGE-PLAN-DEPENDENCY-FAILED` mantêm a falha
  parcial visível: o plano registra exatamente onde a prova parou.
