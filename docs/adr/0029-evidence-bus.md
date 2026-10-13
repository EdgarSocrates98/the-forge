# ADR 0029 — Handoff como bus de evidência tipada, não blob de contexto

- Status: aceito (2026-10-07)

## Contexto

O handoff da Wave D original era uma lista de referências — suficiente para
passar artifacts, mas sem estrutura: o consumidor não sabia o que era decisão,
o que era evidência, nem de onde cada item veio. A spec do ciclo 3 (Wave D v2)
pede um evidence bus: objetos de conhecimento tipados com origem completa,
deduplicação entre produtores e filtragem pela necessidade declarada do
consumidor — "apenas o contexto necessário" como invariante, não como aspiração.

## Decisão

- **`Handoff/v2`: itens tipados** — `decision`, `verification` (o resumo do
  `VerificationResult` do run de origem), `finding`, `evidence`, `artifact`,
  `constraint`, `assumption` — cada `HandoffItem` com `origin` completa
  (provider, run, nó) e regras de forma por kind (`evidence` exige `epistemic`,
  `decision`/`finding` exigem `claim`, `artifact` exige `hash`; epistemic é
  proibido onde não se aplica — o contrato rejeita a mistura).
- **Proveniência preservada, não reescrita**: `derived_from` e `epistemic`
  passam verbatim; conteúdo idêntico de várias origens é enviado uma vez com
  `also_from` listando todas — deduplicação nunca apaga quem também viu.
- **Necessidade declarada filtra**: `relations.consumes` do consumidor remove
  artifacts declaradamente irrelevantes **antes** do orçamento de bytes; o
  corte por tamanho continua por último e visível (`truncated`).
- **Gravado antes do envio**: o handoff é persistido (`handoff.json`) antes do
  `execute` do nó e vai ao provider byte-a-byte como gravado — o receipt do nó
  o liga por hash (`inputs.handoff_sha256`), e o resume prova reuso por
  identidade do handoff reconstruído, não por igualdade aproximada.
- **Nunca instrução**: o conteúdo do handoff é dado não-confiável para o
  consumidor (o adapter trata como facts, não como comandos — a regra de
  authoring está em `provider-authoring.md`); segredos nunca entram — o pack
  de contexto os exclui na origem e `redact` cobre a persistência.

## Consequências

- Um nó consumidor recebe *o que precisa*: evidência com proveniência,
  verificações de upstream, decisões com razão — e nada além.
- `handoff_bytes` é medido por run (benchmark da Wave P), e um handoff
  gigante ou duplicado é um problema observável, não um vazamento silencioso.
- O resume consegue provar "o mesmo input" por identidade de hash — a base da
  reutilização de nós do [scheduler durável](0018-multi-provider-execution.md).
