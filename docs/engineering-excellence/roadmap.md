# Engineering Excellence Roadmap

## Wave 0 — baseline

Resultado: spec ativa, audit, parity matrix e gap analysis.  
Gate: oito repos identificados; baseline commits registrados; gaps priorizados.

## Wave 1 — audit command

Resultado esperado: `theforge excellence audit` com texto/JSON, códigos previsíveis, testes e docs.  
Gate: execução reproduzível sem rede; gap encontrado não some em saída humana.

## Wave 2 — federation contract

Resultado esperado: projection de capabilities existentes, negotiation, confidence, cost, receipts.  
Gate: nenhum registry local perde autoridade.

## Wave 3 — context and planning

Resultado esperado: glossary/context pointers/task graph ligados por referências.  
Gate: plano proporcional; sem pipeline gigante para tarefa pequena.

## Wave 4 — quality loop

Resultado esperado: TDD/risk gates/reviews/diagnostics/fitness.  
Gate: código, spec e contrato revisados de forma independente.

## Wave 5 — benchmark and UX

Resultado esperado: benchmark comparável, retro, compat matrix, onboarding visual, CLI/TUI/Portal resilient.  
Gate: TTY, non-TTY, low width, colorless, Unicode-poor e host adapters cobertos.

## Release rule

Cada wave exige commit isolado, teste local, evidência, docs, revisão e CI verde antes de merge. Falha bloqueia wave dependente.
