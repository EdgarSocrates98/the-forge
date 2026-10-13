# ADR 0042 — forge-contracts: auditoria empírica reafirma "não extrair"

- Status: aceito (2026-10-07)
- Cycle 4, Wave K — phases 73–79

## Contexto

O ciclo pede um estudo empírico antes de qualquer extração de
`forge-contracts` (§73: "DO NOT EXTRACT YET — first perform empirical
audit"). O ADR 0031 (cycle 3.1) já escolhera a Opção B — `schemas/` como
repositório de contratos compartilhado, sem pacote. A Wave K re-verifica a
decisão com evidência fresca dos quatro repos.

## Evidência (scorecard completo em `docs/contract-stability.md`)

- Nove conceitos candidatos auditados; nenhum atinge o threshold §76
  (≥3 consumidores reais + semântica estável + tradução mecânica).
- Evidence/Finding/Handoff divergem de propósito entre repos — pointer
  lazy (doctor), provenance record (api-forge), claim epistêmico
  (the-forge). Não é reshape mecânico.
- Frameworks incompatíveis para um pacote único: the-forge é stdlib-only
  (invariante), api-forge é pydantic, doctor usa ContractModel próprio.

## Decisão

Manter a Opção B: `schemas/` é a camada de interoperabilidade. Nenhum
código extraído neste ciclo. Gatilho de reavaliação registrado no doc:
adoção real dos mesmos arquivos de schema por ≥2 repos em produção.

## Consequências

- `forge-contracts` permanece uma não-decisão positiva: o custo real de
  duplicação segue baixo e a independência de release dos repos irmãos é
  preservada.
- O conteúdo proibido do §79 (routing, planner, registry, memory, economy,
  runtime, CLI, agents) fica registrado permanentemente — qualquer extração
  futura continua vedada de conter kernel.
