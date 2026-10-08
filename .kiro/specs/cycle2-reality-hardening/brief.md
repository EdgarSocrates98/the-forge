# Brief: cycle2-reality-hardening

## Problem
Core do Cycle 1 aceita estados semanticamente inválidos, tem gaps de trust/cache/ambiente e não possui CI; adapters reais (Wave B) não podem ser construídos sobre essa base.

## Current State
Ver Introduction de `requirements.md` (auditoria 2026-10-02).

## Desired Outcome
Invariantes de contrato, protocol/routing adversarial, trust/cache/identidade, env/cwd, policy/risk foundation e CI com gates mecânicos, todos testados.

## Approach
Endurecer o core existente in-place, sem novos runtimes nem dependências.

## Scope
- **In**: Requirements 1–7 de `requirements.md`.
- **Out**: demais waves (ver `.kiro/steering/roadmap.md`).

## Boundary Candidates
- Validação semântica de contratos
- Transporte/protocol
- Routing
- Registry/trust/cache
- Ambiente de provider
- Policy/risk
- CI

## Out of Boundary
- Adapters reais, contexto v2, multi-provider, paridade agentic

## Upstream / Downstream
- **Upstream**: Cycle 1
- **Downstream**: real-provider-integration, context-intelligence-v2

## Existing Spec Touchpoints
- **Extends**: Cycle 1 core
- **Adjacent**: specs do roadmap

## Constraints
Ver `.kiro/steering/roadmap.md`.
