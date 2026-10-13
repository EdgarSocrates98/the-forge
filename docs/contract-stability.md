# Contract stability scorecard — `forge-contracts` extraction study

Cycle 4, Wave K — §73–79. Auditoria empírica: extrair `forge-contracts` só se
houver **≥3 consumidores reais** + **semântica provada estável** +
**tradução de adapter majoritariamente mecânica** (§76). Data da auditoria:
2026-10-07. Repositórios comparados: `the-forge`, `forge-doctor-api`,
`api-forge`, `spark-forge-aws`.

## Framework de cada repo

| repo | runtime de contratos | versionamento |
|---|---|---|
| the-forge | dataclasses frozen, **stdlib-only** (invariante) | `schema = "theforge/<Name>/v<N>"` string |
| api-forge | **Pydantic** `VersionedContract` (extra=forbid) | `version: Literal[1]` campo inteiro |
| forge-doctor-api | `ContractModel` dataclass próprio | `contract_version` string por payload |
| spark-forge-aws | sem camada de contratos compartilhável (consome via adapter) | — |

Três frameworks, três regras de versionamento — a fronteira comum real é o
JSON Schema publicado em `schemas/` (Opção B do ADR 0031).

## Scorecard por conceito candidato (§74/§75)

| conceito | the-forge | forge-doctor-api | api-forge | semântica equivalente? | consumidores |
|---|---|---|---|---|---|
| ProducerIdentity | `Producer{id,version}` | — (producers são check ids) | `decided_by`/`from_agent` strings | **não** | 1 |
| Evidence | `Evidence{id,epistemic,subject,claim,producer,hash,limitations,derived_from}` | `Evidence{ref,kind,source,detail}` — ponteiro lazy | `EvidenceRef{ref,kind,level}` + `EvidenceRecord{level,source,confidence,refs}` | **não** — claim vs pointer vs provenance record | 1 (3 semânticas) |
| Finding | `{id,title,severity∈info..critical}` | `{check_id,severity∈error\|warning\|info\|pass,category,...}` | modelos nativos de finding | **não** — eixos de severidade divergem | 1 |
| UnknownFact | `unknowns: list[str]` (não-tipado) | `UnknownFact` modelado | `limitations` tuples | **não** | 1 |
| ArtifactReference | `Artifact{path,sha256}` | — | `ArtifactRef{path,sha256,kind,evidence_level}` | **parcial** — campos extras, pydantic | ~1.5 |
| CapabilityRef | string validada por regex (`CAPABILITY_REF`) | — | — | n/a | 1 |
| Handoff | `Handoff` — evidence bus tipado (`HandoffItem`, provenance) | `HandoffBundle` (scan bundle) | `HandoffRecord{handoff_id,from_agent,to_agent,reason,refs}` — roteamento de agente | **não** — três propósitos distintos | 1 |
| ContractVersion | string `theforge/<Name>/v1` | `contract_version` str | `version: Literal[1]` int | **não** | — |
| EpistemicStatus | `Epistemic = confirmed\|observed\|inferred\|proposed\|unresolved` | confidence strings livres | `EvidenceLevel` enum próprio | **não** | 1 |

## Estabilidade temporal

Os contratos `theforge/<Name>/v1` são estáveis **dentro do the-forge** desde o
cycle 1 — apenas aditivos nos cycles 2/3/3.1/4 (`Capability.offer`,
`mcp_requires`, `TaskSpec.requirement`, `RoutingDecision.shadow`, campos de
observação). Mas §76 exige estabilidade de *semântica compartilhada entre
consumidores* — e a evidência acima mostra o oposto: cada repo evoluiu sua
própria semântica para Evidence/Finding/Handoff deliberadamente (doctor:
diagnóstico lazy-pointer; api-forge: provenance levels + agentic records;
forge: claims epistêmicas com producer e hash).

## Decisão

**Não extrair.** Nenhum candidato satisfaz o threshold:

- consumidores reais com mesma semântica: máximo ~1.5 (ArtifactReference),
  nunca ≥3;
- semântica estável compartilhada: falha — os conceitos irmãos divergem em
  campos obrigatórios, enums e propósito;
- tradução mecânica: falha — remapeamento de enums, reshape de campos e
  tradução de framework (stdlib dataclass ↔ pydantic) não são mecânicos.

**Manter a Opção B**: `schemas/` é o repositório de contratos
(language-neutral, JSON Schema draft 2020-12); adapters continuam
responsáveis pela tradução nativo→protocolo — fronteira que já existe e já
está testada (`test_schemas.py`, `test_conformance.py`).

**Gatilho de reavaliação**: quando ≥2 repos irmãos passarem a consumir os
*mesmos arquivos* JSON Schema de `schemas/` para validar payloads em
produção (não em testes), re-rodar este scorecard — aí o consumidor real
existe e a semântica está demonstrada pelo uso, não por inspeção.
