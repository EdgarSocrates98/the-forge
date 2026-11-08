# Agent Bridge remediation

## FAB-001 — eventos

`events.normalize` mantém o tipo nativo desconhecido como `runtime.unknown` e
reserva `runtime.error` para erro real do provider ou falha explícita. O evento
continua com payload seguro e redigido, permitindo replay sem apresentar evento
desconhecido como falha.

## FAB-002 — retenção e replay

`DurableEventStore` foi revalidado para limite por eventos, limite por bytes,
marcador de truncamento, idempotência, replay por cursor e arquivo JSONL
malformado. O marcador é observável e não é confundido com evento de usuário.

## FAB-003 — sanitização

A redação ocorre antes de envelope, append e exposição. Foram exercitados
Authorization/Bearer, chaves, URLs, estruturas aninhadas, arrays, payloads de
eventos desconhecidos e texto excessivo. Os testes confirmam que a fixture de
segredo não reaparece nos artefatos emitidos.

## Regressão executada

```text
uv run pytest tests/test_bridge.py tests/test_cycle21.py tests/test_cycle22.py \
  tests/test_cycle23.py tests/test_cycle24.py tests/test_cycle25.py \
  tests/test_cycle26.py tests/test_cycle28.py tests/test_cycle29.py \
  tests/test_cycle30.py tests/test_cycle30_1.py tests/test_cycle30_2.py -q
107 passed
```

Status FAB: **PASSED**. A homologação de provider externo permanece separada e
`NOT_RUN`.
