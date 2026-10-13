# ADR 0004 — Sem forge-kernel por enquanto

- Status: aceito (2026-10-02)

## Contexto
A auditoria encontrou conceitos convergentes (receipts, context, budget, workspace manifest) com schemas divergentes.

## Decisão
Nenhum pacote compartilhado entre os três projetos. O ponto de integração é o protocolo.

## Reavaliar quando
A mesma abstração estiver provada em ≥ 2 providers via protocolo e a duplicação gerar defeito real.
