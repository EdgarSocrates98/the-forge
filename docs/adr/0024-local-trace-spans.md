# ADR 0024 — Trace local é um campo do RunTelemetry, não um segundo sistema

- Status: aceito (2026-10-05)

## Contexto

O ciclo 3 pede observabilidade agentic: tornar visíveis runs, chamadas a
provider e handoffs, sem plataforma externa — `trace` responde *o que
aconteceu*, `explain` responde *por quê*. A spec permite `Trace/v1`+`Span/v1`
ou adaptar `RunTelemetry`, com uma restrição explícita: não criar dois sistemas
redundantes. `RunTelemetry` já é o artefato de observabilidade persistido,
linkado ao receipt, escrito em todo desfecho — um `Trace` separado duplicaria
run_id, timestamps, profile e a maior parte do conteúdo.

## Decisão

- **`Span` vive dentro de `RunTelemetry`** (`spans: list[Span]`, aditivo):
  `id` `s<N>` na ordem de início, `start_ms`/`duration_ms` medidos no relógio
  monotônico (offsets — imunes a ajustes de relógio de parede), `parent`,
  `status` (`error` quando o bloco lançou) e `attributes` limitadas.
- **Um mecanismo só de medição**: `phase()` é implementada sobre `span()` — a
  mesma instrumentação alimenta a métrica agregada e o span do trace; medir uma
  fase continua custando duas leituras de relógio, e o tempo de uma fase que
  falha ainda acumula (o span sai com `status="error"`).
- **Nomes livres, contrato fechado**: `provider:<id>`, `node:<id>`, `handoff`,
  `verification`, `synthesis`, `negotiation` — os labels são decididos no call
  site; o contrato só exige limites (nome ≤80, attrs ≤16×120, ≤256 spans, ids
  únicos, `parent` resolve a um span anterior).
- **`theforge trace <run>`** lê só o artefato persistido — nenhum provider
  inicia; exporters futuros são opcionais e o trace é offline por construção.

## Consequências

- Artefatos `telemetry` anteriores à Wave J continuam válidos (`spans` ausente
  vale "não registrado") — aditivo dentro de `RunTelemetry/v1`.
- A thread-safety é local: ids e appends sob um lock no recorder; spans de nós
  concorrentes ordenam pelo `id` de início, não pela chegada.
- O trace não pode conter a si mesmo: o span `synthesis` fecha antes de
  `build()`, então a serialização do artefato nunca aparece no trace.
