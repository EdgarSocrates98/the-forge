# ADR 0005 — Routing determinístico primeiro, sem LLM no ciclo 1

- Status: aceito (2026-10-02)

## Decisão
Ranking lexicográfico por (tipos de sinal casados, deps, globs, keywords), usando sinais declarados pelos providers. Confiança `high` exige vencedor único e ≥ 2 tipos de sinal. Fora disso o resultado é `ambiguous`, com candidatos e a dica `--capability`.

## Motivo
Barato, reprodutível, explicável. Não existe peso inventado.

## Consequências
Pedidos vagos exigem `--capability`. O LLM entra num ciclo futuro, só para resolver ambiguidade.
