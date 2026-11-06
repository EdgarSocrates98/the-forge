# Resolução dos achados Goldfish — ecossistema agentic

Este documento registra a primeira implementação da spec
`egm-resolve-agentic-ecosystem-2026-11-06`. Ele separa fato observado,
projeção e lacuna não verificada; não transforma intenção de produto em
capability.

## Decisões fechadas

- Ownership: `theforge/AgentSpec/v1` + `forge/SpecialistAgenticManifest/v1`;
  não existe `AgentSpec v2` implícito. Ver ADR 0063.
- Catálogo: projeção read-only de `catalog_ids`, lifecycle, manifest, registry,
  health e evidências. Não existe segundo lifecycle.
- Portal: “Nova investigação” deve compor `/tasks/plan` → plan token →
  confirmação → `/tasks/execute` → receipt/eventos. Cancelamento, reconexão,
  falha e desconhecido são estados da tarefa/receipt, não uma máquina paralela.
- Spark: o golden path continua sendo a sequência `ask` → `analyze` →
  `case show`/`next-step` sobre fixtures/replay. Replay, execução live e
  verificação independente precisam ser rotulados separadamente.

## Implementação nesta fatia

`theforge.agent_roster.inspect_roster` compara manifest e rosters nativos sem
importar nenhum provider. O resultado traz `state`, ids declarados/observados,
fontes e evidência para consumo por catálogo/Portal. O resultado não autoriza
routing e retorna `UNKNOWN` quando não há roster canônico.

`SpecialistView` e `specialists.to_rows` agora carregam essa projeção como
`agent_roster`, mantendo lifecycle, manifest e roster como campos separados.
O endpoint Portal `/specialists` também expõe esse campo de forma aditiva;
quando a instalação só fornece um manifest empacotado, o campo permanece
ausente/`UNKNOWN`, sem inferir roster vazio.

Leitura do workspace em 2026-11-06: os manifests de `the-forge`,
`spark-forge-aws`, `spark-forge-azure`, `api-forge` e `platform-forge` foram
sincronizados com seus rosters canônicos e retornam `CONFORMANT`; a mesma
correção foi aplicada ao `product-forge`, descoberto pelo gate federado. Os
doctors sem roster nativo permanecem `UNKNOWN`. Nenhum desses estados é
promovido a capability ou trust.

O teste `tests/test_agent_roster_conformance.py` cobre:

- igualdade manifest/roster (`CONFORMANT`);
- declaração vazia com roster real (`DRIFT`);
- agente declarado sem arquivo (`STALE`);
- ausência de roster (`UNKNOWN`);
- fontes canônicas divergentes (`CONFLICT`).

## Mapa de evidências existentes

| Tema | Fonte canônica | Estado | Limitação honesta |
|---|---|---|---|
| AgentSpec/manifest | `contracts/agent.py`, `contracts/specialist.py`, ADR 0063 | PASS | host load real continua dependente do host |
| catálogo/lifecycle | `specialists.py`, ADR 0062 | PASS | disponibilidade parcial permanece possível |
| routing | `discovery.py`, `routing.py`, testes de negotiation/federation | PASS | histórico é sinal de ranking, não gate de cold start |
| Portal/task | `portal_adapter.py`, `_forge_portal.py`, ADR 0059 | PASS | UI “Nova investigação” visual e acessibilidade precisam do gate do forge-portal |
| Spark golden path | `docs/onboarding/golden-paths/spark-aws.md`, fixtures/replay | REPLAY/LOCAL | execução live AWS não é afirmada por replay |
| telemetry | `_portal_telemetry.py`, trace/receipt contracts | PARTIAL | provider sem trace permanece `partial_trace`/`telemetry_unavailable` |

## Guardrails

- Manifests, skills, paths, comandos, outputs e credenciais ficam em trust
  boundaries distintas; nenhum campo declarativo concede trust.
- Orçamentos devem usar unidades observáveis (bytes, passos, tempo e chamadas)
  e registrar `unknown` quando custo/uso não é medido. Hard stops continuam no
  executor/policy existente.
- Planos Portal expiram, são assinados e consumidos uma vez; retry usa o task
  id/receipt existente, sem duplicar execução.
- Fixture drift exige hash/fingerprint atualizado e revisão; resultado
  `BLOCKED`, `NOT_RUN` ou `UNKNOWN` não vira `PASS`.
- Não foram feitos push, publicação, mutação de produção, execução remota ou
  gasto de cloud.

## Governança operacional nesta fatia

O ADR 0064 fecha os riscos transversais que não pertencem a um provider:
orçamento é expresso em unidades observáveis com hard stop; custo não medido
permanece `unknown`; manifestos, skills, paths, comandos, credenciais e
outputs continuam em trust boundaries distintas; e a receipt local marca
`partial_trace`/`telemetry_unavailable` quando o provider não entrega
telemetria suficiente. Histórico de verificação influencia ranking e risco,
mas não é gate de cold start. Retry, cancelamento e reconexão continuam no
task id/receipt canônico, sem um segundo ledger.

A evidência de aceitação está no próprio ADR 0064, na conformance de roster e
no contrato executável do golden path Spark. Esta fatia não afirma execução
live, custo real de provedor ou verificação independente.

## Próximos gates

1. Integrar a projeção de roster ao endpoint de catálogo do Portal, mantendo o
   schema de resposta aditivo.
2. Executar o gate visual/e2e do `forge-portal` para a jornada “Nova
   investigação”.
3. Rodar a conformance Spark no ambiente com diretório temporário funcional e
   separar receipts `REPLAY_VERIFIED`, `LIVE_EXECUTED` e
   `INDEPENDENTLY_VERIFIED`.
