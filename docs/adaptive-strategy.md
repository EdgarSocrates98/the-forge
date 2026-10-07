# Estratégia adaptativa: shadow champion/challenger (Cycle 4, Wave H)

A decisão de routing pode carregar um `shadow` — a recomendação de qual
provider a história medida preferiria (§51-55, §102-103). É **advisory**:
nunca executa, nunca muda `selected`, nunca é promovida automaticamente.

## Quando o shadow dispara

Só quando um challenger supera a barra de promoção em **evidência**:

- **observações suficientes** — maturidade `warming` (≥3 runs) ou `mature`
  (≥8) no histórico daquele `(provider, capability, surface)`; história
  `cold` (1-2 runs) nunca aconselha — nenhuma decisão sai de uma amostra
- **qualidade não degrada** — `verified_rate` do challenger ≥ a do incumbente
- **melhoria de custo/contexto observada** — `avg context_bytes` estritamente
  menor quando o incumbente tem história comparável; quando o incumbente
  **não tem** história na surface atual, qualquer challenger com runs
  verificados qualifica (a própria ausência é a evidência)
- **mesma surface** — a comparação nunca cruza fingerprints: provider que
  mudou de surface tem história nova e não herda números

## Exemplo

```text
Selected:   a-forge security.scan:run (confidence high)
Reason:     requested capability security.scan; 2 providers declare it, ...
Shadow:     b-forge preferred by measured history (mature, advisory —
            runs 8 (mature); verified_rate 1.00 vs 0.80;
            avg context_bytes 12 vs 480)
```

O shadow viaja no artefato `routing` do run (`RoutingDecision.shadow`), então
`explain` e replay mostram a mesma recomendação que o routing emitiu.

## Limites (por design)

- **Não-promoção agressiva**: o challenger é sempre "candidato" — nunca se
  afirma que ele *teria sido melhor* sem evidência real (§103).
- **Risco domina custo** (§53): o shadow é economia; trust, policy e hard
  gates continuam decidindo a seleção.
- **Anti-viés**: o shadow nasce do `ProviderPerformance` store — o mesmo
  corpus não treina e avalia políticas adaptativas futuras (§104).
