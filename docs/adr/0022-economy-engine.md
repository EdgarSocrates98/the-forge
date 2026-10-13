# ADR 0022 — Economia: `RunBudget`, promoção limitada e histórico medido

- Status: aceito (2026-10-05)

## Contexto

Até a Wave H o perfil efetivo de um run existia só na telemetria: nada dizia,
de forma auditável e ligada ao receipt, *quanto* o run podia gastar — nem se um
perfil pedido explicitamente era estreito demais para a complexidade medida.
Duas perguntas do ciclo 3 ficavam sem resposta verificável: "o contexto enviado
rendeu?" (ROI) e "qual provider entrega melhor?" — que, respondida sem cuidado,
viraria um ranking subjetivo de agentes.

## Decisão

### `RunBudget/v1` é o contrato do que o run podia gastar
Gravado como artefato `budget` em todo run que resolve um perfil — `ask` e
plano — e ligado ao receipt por `inputs.budget_sha256`. Carrega os bounds
efetivos (contexto, arquivos, chamadas, timeout, paralelismo, rodadas) e os
`adjustments` aplicados. O que o run gastou de fato continua na telemetria;
o budget é o teto, auditável por hash.

### Promoção é elástica e de um degrau só
`--profile auto` já segue a avaliação de complexidade. Num perfil explícito a
avaliação também roda: se o `selected_profile` medido supera o pedido, os
campos elásticos (`budget_bytes`, `max_files`, `negotiation_rounds`) promovem
**um degrau** — economy→balanced→max — e nunca mais. `max_providers`,
`execute_timeout_s`, `verification` e `fallback` **não promovem**: são os
campos que alargam o blast radius, e um perfil pedido explicitamente não deve
crescer sozinho em providers, tempo ou stringência. Comparar com
`selected_profile` (e não com `level`) mantém o fallback de baixa confiança
intocável: evidência fraca não pode empurrar orçamento. Quando a promoção
acontece, o `ComplexityAssessment` é persistido como evidência e o
`budget.adjustments` diz o que mudou. Um run de plano grava o próprio budget
(`provider_calls` = nós); cada nó promove dentro do seu run.

### Context ROI é medido, não inferido
`files_cited`/`evidence_returned`/`findings_returned` na telemetria respondem,
por run, o quanto do pack enviado voltou como evidência. `files_cited` conta
arquivos do pack que aparecem em `subject`/`location.path` da evidência — um
critério simples e honesto (evidência sem path citável não conta). Runs sem
resultado registram zero explícito, não `unknown`.

### Histórico medido nunca é ranking
`.forge/metrics/provider-performance.json` guarda `ProviderPerformance/v1`:
por provider+capability, desfechos, runs verificados, evidências, artifacts,
bytes/arquivos enviados e citados, latência total. É **fator de desempate
secundário**: no routing explícito ordena iguais em trust antes do id; no
routing por sinais resolve só um empate de `rank_key` com um único vencedor
estrito — e a igualdade de raw-presence entre os empatados é a *mesma*
ambiguidade, decidida junto. Abaixo do piso de sinais, com histórico igual,
sem histórico ou diante de um rival não-empatado com presença crua maior, o
run continua `ambiguous`. Trust, policy, compatibilidade e capability nunca
são consultadas ao histórico — filtram antes. A chave é transparente:
verificação primeiro, entrega depois, latência, volume por último.

## Consequências

- Todo o crescimento de orçamento é observável: `adjustments` no artefato e
  limitações no receipt dizem quem promoveu e por quê.
- O store de métricas é best-effort e fail-closed: arquivo malformado é
  ignorado com nota; falha de escrita é limitação, nunca erro do run.
- Sem "score de qualidade de agente" — só métricas observáveis.
- O desempate é determinístico dado o estado do store: runs iguais com o mesmo
  histórico decidem igual.
