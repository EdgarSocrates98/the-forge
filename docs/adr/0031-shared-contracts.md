# ADR 0031 — Contratos compartilhados: schema repository agora, pacote talvez nunca

- Status: aceito (2026-10-07)
- Phases: 27 (audit), 28 (decisão), 29 (non-goal)

## Contexto

O ciclo 3.1 deixou ao menos quatro implementações reais de conceitos irmãos:

- `theforge/contracts/` — os contratos do Forge Protocol (ExecutionResult,
  Evidence, Handoff, PlanRequest…), dataclasses Python com serialização
  canônica e schemas JSON publicados em `schemas/`.
- `forge_doctor_data/contracts/` + `sdk.py` — a camada de contratos do Doctor
  Data (HandoffBundle e modelos de scan).
- `forge_doctor_api/core/models.py` + `handoff/` — `Evidence`, `Finding`,
  `UnknownFact`, `HandoffBundle`/`ApiHandoffBundle`, envelope e delta.
- `apiforge` e `sparkforge_aws` — modelos internos de domínio (cases, facts,
  findings nativos), traduzidos para o protocolo pelos adapters.

A tentação: extrair um pacote `forge-contracts` para deduplicar. Phase 28 pede
a decisão explícita; Phase 29 veda `forge-kernel` (routing, planning, memory,
runtime, agents) neste ciclo — qualquer extração se limita a data contracts,
schemas, version negotiation e canonical serialization.

## Opções

- **A — contratos JSON duplicados (status quo).** Cada repo valida sua visão;
  os adapters traduzem nativo → protocolo. Custo real observado: baixo — as
  traduções vivem no adapter (200–400 linhas), e `test_schemas.py` +
  `test_conformance.py` já seguram o alinhamento com os schemas publicados.
- **B — shared schema repository only.** `schemas/` já é isso: JSON Schema
  publicado por contrato, `additionalProperties: false` nos artefatos
  core-only, schemas abertos nos documentos que cruzam o protocolo. Doctors
  podem validar contra os mesmos arquivos sem depender de Python.
- **C — pacote `forge-contracts` stdlib-only.** Remove a duplicação de
  definições, mas **não** remove a tradução: o adapter ainda precisa converter
  `forge_doctor_api.core.models.Evidence` → `theforge/…/v1`. Em troca cria um
  acoplamento de release entre quatro repos com ciclos independentes — exato
  oposto do "specialist independence" que o protocolo protege.
- **D — forge-kernel.** Vetado pela Phase 29: routing/planning/memory/runtime
  compartilhados transformariam o control plane num monorepo distribuído.

## Decisão

**B agora; C revisitável.** O repositório de schemas (`schemas/*.schema.json`
+ gerador `theforge.contracts.schema`) é formalmente promovido a superfície de
interoperabilidade: a fonte da verdade do formato é o JSON Schema publicado,
não o dataclass que o gerou. Cada implementação prova conformidade contra o
schema — não contra o código Python alheio.

`forge-contracts` (C) só volta a ser considerado se surgir uma quinta
implementação real de protocolo que queira reusar as definições em Python —
hoje o custo de duplicação é menor que o custo de acoplamento de release.

**D nunca.** Nenhum kernel neste ciclo nem no roadmap declarado.

## Consequências

- O que pode ser compartilhado sem nova dependência já é: schemas JSON,
  convenção `theforge/<Name>/v1`, serialização canônica documentada
  (`canonical_json` em `protocol.md`), negociação de versão (`protocols[]` no
  manifest + `PROTOCOL_V1`).
- Os Doctors mantêm seus modelos nativos — a perda de fidelidade é
  impossível de esconder: a tradução é explícita no adapter, e campos sem
  equivalente são preservados verbatim (ADR: lossless translation, Phase 73).
- Uma mudança de contrato exige: bump documentado em `docs/versioning.md`,
  regen de `schemas/`, e os adapters não precisam mudar até optarem pelo campo
  novo (additive-only é a regra do protocolo).
