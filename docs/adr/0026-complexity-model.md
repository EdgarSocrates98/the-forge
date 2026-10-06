# ADR 0026 — Perfil por avaliação de complexidade medida, não por heuristicão única

- Status: aceito (2026-10-07)

## Contexto

Até o ciclo 2, `--profile auto` era resolvido por um único sinal (número de
targets) — um proxy fraco que tratava "revise este arquivo" e "migre o data
lake" do mesmo jeito. A spec do ciclo 3 (Wave A) pede um modelo de
complexidade: a tarefa é medida por dimensões declaradas, o resultado escolhe o
perfil e a escolha é auditável — sem LLM no core e sem chute: quando a medição
não cobre o suficiente, o sistema diz que não sabe.

## Decisão

- **`ComplexityAssessment/v1` determinístico** (`forger.complexity`): dimensões
  declaradas (`repositories`, `technologies`, `actions`, `providers`,
  `targets`, `roles`, `dependencies`, `signals`) cada uma com `value`,
  `weight` e `evidence`; o `score` é a média ponderada das dimensões medidas e
  `confidence` é a fatia do peso total que foi realmente medida. Uma dimensão
  sem dado é `unknown` — nunca contribui zero fingido.
- **Profile pelo level medido**: `trivial→economy`, `moderate→balanced`,
  `high→max` (thresholds em `complexity.toml`, usuário/projeto, projeto vence);
  `confidence < 0.5` cai para `balanced` com `profile_reason` explicando —
  incerteza degrada para o meio, nunca para cima nem para baixo.
- **`auto` grava a avaliação**: o artefato `complexity` é persistido e linkado
  no receipt (`inputs.complexity_sha256`); `--profile` explícito não avalia —
  pedido explícito vence medição.
- **Config auditável**: `complexity.toml` pode ajustar pesos e thresholds por
  camada; `config_source` registra quais camadas alimentaram a política.

## Consequências

- `auto->economy` num pedido de um arquivo e `auto->max` numa tarefa
  multi-repo são explicáveis: `explain` mostra `Complexity:` com level, score,
  confidence e o motivo da seleção.
- O modelo é um input de orçamento, não um roteador: nenhuma dimensão escolhe
  provider, e uma avaliação adversarial não contorna policy — um `complexity.toml`
  malicioso só mexe nos próprios limites da workspace que o contém.
- Runs sem avaliação (profile explícito, ou anteriores à Wave A) mostram
  `complexity=-` no receipt — ausência honesta, não zero.
