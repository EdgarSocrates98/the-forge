# Prompt Coverage Matrix — `prompt_evo*.md`

Auditoria de completude: cada prompt de evolução mapeado para implementação,
testes, relatório e status. Data: 2026-10-08. Branch `devin/agentic-benchmarks`.

Regra honesta: `completo` significa que os critérios de aceite/DoD do prompt
têm evidência no repo — não que todo item opcional ou "possível" foi
implementado (o próprio Feature Freeze proíbe expandir escopo sem ADR).

| Prompt | Escopo | Evidência principal | Status |
|---|---|---|---|
| `prompt_evo_inicial.md` | Fundação: control plane, protocolo Forge, contratos, run store | `src/theforge/`, `schemas/`, relatório `cycle-2.md` | completo |
| `prompt_evo_passo1.md` | Primeira vertical: routing determinístico, staging, verificação | `routing/`, `planning/validate.py`, `cycle-2.md`/`cycle-2.1.md` | completo |
| `prompt_evo_cycle2_cycle3.md` | Dois adapters reais (sparkforge_aws, apiforge), execução local, evidência | `adapters/sparkforge_aws`, `adapters/apiforge`, `cycle-3.md` | completo |
| `prompt_evo_cycle3_1.md` | Hardening: waves A–J, context economy, policy | `cycle-3.1*.md` (10 docs), `run_context_economy.py` | completo |
| `prompt_evo_cycle4.md` | Capability mesh, install plan v2, registry sources | `capability_graph.py`, `registry/install_plan.py`, `cycle-4.md` | completo |
| `prompt_evo_cycle4_final.md` | Fechamento 4.x: Global Stop, StrategyPolicy, remote trust | `control/`, `learning/`, `remote/`, `cycle-4.1.md` | completo |
| `prompt_evo_cycle5.md` | Memory, graph v2, execution targets, federated trace | `memory/`, `simulation.py`, `cycle-5.md` | completo |
| `prompt_evo_cycle5_final.md` | Reality sync, B01–B15, freeze, scorecard | `run_scenarios.py`, `cycle-5.1*.md`, `scorecard` | completo |
| `prompt_evo_cycle5.1.md` | Expansão 4→6, maturidade derivada, B16–B25, onboarding genérico | adapters Azure/Platform, `cycle-5.1-ecosystem.md` | completo |
| `prompt_evo_engenharia_agentica.md` | Skills/subagents, resolver propose→validate, **A01–A15**, relatório §100 | **`run_agentic.py` (novo), `agentic-ecosystem.md` (novo)** | completo (era o gap) |

## O que faltava e foi entregue nesta wave

O prompt agentic exige explicitamente `A01–A15`, a comparação
deterministic×agentic (§88), os contadores de fallback (§89), os estados de
instalação (§90) e o relatório final com veredicto (§100). Nada disso existia
— os cenários B são de outro prompt e não satisfazem a série A por osmose.

Entregue:

- `scripts/bench/run_agentic.py` — 15 cenários A sobre os 6 adapters em
  replay; `routing_metrics` medido por execução (`requests=11`,
  `deterministic_resolved=8`, `fallback_needed=3`, `accepted=1`,
  `rejected=2`, `unnecessary=0`).
- `docs/reports/agentic-ecosystem.md` — todas as seções §100 +
  `agentic-scenarios.json` machine-readable.
- `tests/test_bench.py` — contratos da suíte (códigos, chaves §89).

## Itens intencionalmente não implementados (deferidos/proibidos)

Decisões de produto registradas, não esquecidas:

| Item | Motivo |
|---|---|
| Remote/federated transport real | diferido por design desde o Cycle 4; contratos de política/recibo testados (B07/B13); Feature Freeze proíbe transporte novo sem ADR → veredicto REMOTE_BLOCKED |
| Agents `ecosystem-router`/`forge-verifier` | duplicariam o `route()` determinístico / a verificação por contrato — o prompt proíbe duplicar conhecimento de domínio e inventar formatos |
| Marketplace / SaaS plane / runtime distribuído | fora do escopo; exigiria ADR |
| Live resolver (LLM) | nenhum adapter real declara op `resolve`; os caminhos são exercidos via `proposal_selection`/`resolve_candidates` (pure functions) |
| CI remota | quota de GitHub Actions esgotada (decisão do owner); evidência local máxima |

## DoD do prompt agentic — respostas diretas

| Pergunta | Resposta | Prova |
|---|---|---|
| Sabe o que cada Forge é? | sim | manifests replay + `specialist-reality.json` |
| Sabe quando usar cada um? | sim | A01–A04, routing por capability |
| Sabe instalar cada um? | sim | A09 `plan_installation` staged |
| Sabe verificar instalação? | sim | health replay + fingerprint (A11) |
| Descobre capabilities reais? | sim | 35 caps via describe dos 6 adapters |
| Distingue AWS Spark de Azure Spark? | sim | A01/A02, B20–B23 — sem equivalência falsa |
| Compõe API + Platform? | sim | A05 (e B18) |
| Compõe Data + Platform? | sim | A13 multi-domain |
| Doctors verificam independente? | sim | A07 cadeia ordenada; B08 `verified_by` |
| Agents propõem sem bypassar gates? | sim | A08/A12 propose→validate, rejeição medida |
| Subagents com contexto limitado? | sim | A15: resolver recebe só candidatos elegíveis |
| Skills pequenas e focadas? | sim | 17 kiro-*, média 7.9 KB; domínio fica no repo do especialista |
| Onboarding genérico de novos Forges? | sim | B25 + `test_generic_onboarding.py` |
| Provider output injeta instruções? | não consegue | A12: trust inerte, resolver gated, pick validado |
| Agents escalam autoridade? | não | trust vem só do `ProviderEntry` do operador |
| Instalação é segura? | sim | A09: 8 estágios pending + approval obrigatória |
| Drift de skill detectável? | sim | A11: fingerprint divergente un-fresh em 3 camadas |
| Custo de contexto medido? | sim | A15 + `routing_metrics` + memory ROI existente |
