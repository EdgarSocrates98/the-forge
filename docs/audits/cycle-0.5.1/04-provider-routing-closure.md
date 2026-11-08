# Provider routing closure

O The Forge já possuía registry, manifests, health, scoring determinístico,
delegation router e persistência de receipts. A revalidação confirmou que
discovery isolado não é tratado como `ROUTABLE`: elegibilidade, capability,
versão e disponibilidade precisam ser satisfeitas.

O caminho governado de repair permanece:

```text
detect → plan → review → confirm → repair → verify → receipt
```

O lab federado executou os participantes locais através do router e preservou
proveniência. Falhas, providers ausentes e capabilities não elegíveis continuam
classificados sem corromper o registry.

## Regressão

```text
uv run pytest tests/test_conformance.py tests/test_router.py \
  tests/test_router_adversarial.py tests/test_delegation_router.py \
  tests/test_federation_conformance.py tests/test_federation_adversarial.py \
  tests/test_federated_trace.py tests/test_provider_sync.py \
  tests/test_registry.py tests/test_specialist_capability.py -q
35 passed, 1 skipped
```

Status: **PASSED** para routing local determinístico; execução de provider de IA
externo: **NOT_RUN**.
