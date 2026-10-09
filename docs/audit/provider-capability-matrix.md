# Provider capability matrix (FASE 0)

Capabilities determinísticas executáveis via adapter (não skills, não
agents — operação verificável):

| Capability | the-forge | api | aws | azure | platform | d-data | d-api |
|---|---|---|---|---|---|---|---|
| analyze (artefato→facts) | — | OpenAPI/FastAPI | pyspark/plan/event-log/iceberg/… | analyze * | analyze * | scan/repo | scan |
| judge (facts→findings) | — | sim | sim | sim | sim | checks | checks |
| playbook/workflow | — | dispatch | playbook | sdd | sdd | — | — |
| doctor (health) | doctor | doctor | doctor | doctor | doctor | install doctor | script doctor |
| economy report | economy | economy | economy report | — | economy | — | — |
| mcp tools | N/A | apiforge-mcp | 143 | serve | platformforge-mcp | 13 | mcp |
| collect (cloud) | — | collect AWS | collect * | — | — | — | — |

## Skills (workflow para o host — NÃO capability)

33 / 15 / 60 / 22 / 12 / 0 / 0 — publicadas em `.claude/skills/` e
mirrors; consumo depende do host.

## Agents (definições — NÃO capability determinística)

8 (AgentSpec, autoridade fechada) / 32 / 19 (14 coord + 5 executors) /
40 / 41 / 0 / 0.

## MCP tools expostas (tools/list real)

- forge-doctor-data: **13 tools** (handshake real executado).
- aws: SDK ausente no env testado — FAIL honesto.
- api/azure/platform/doctor-api: servidor existe; handshake não
  executado — UNVERIFIED.
