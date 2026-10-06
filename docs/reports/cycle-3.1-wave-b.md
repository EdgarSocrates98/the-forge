# Cycle 3.1 — Wave B: identidade de superfície, fingerprints e negociação de features

Escopo: Phases 2, 3, 31, 32, 43 e 77–79 do `prompt_evo_cycle3_1.md`. Premissa: `version`
não é identidade — sparkforge 0.5.0 e apiforge 0.1.0 mudaram de superfície sem mudar de
versão (ver `cycle-3.1-audit.md`).

## O que mudou

- **`theforge/ProviderSurfaceIdentity/v1`** (`contracts/identity.py`): pareia
  `provider_id`/`provider_version`/`adapter_version`/`protocol_version` com dois
  fingerprints determinísticos e o `native_surface_fingerprint` declarado pelo provider.
  `recorded_at` é o instante da observação — nunca entra num fingerprint. Schema publicado
  e fechado (`CLOSED_SCHEMAS`).
- **Fingerprints** (`registry/surface.py`): `capability_fingerprint` cobre o conjunto de
  capabilities (id, actions, default, state, operation class, context tiers, flags de
  handoff/plan/resolve, aliases, depreciação, relations). `surface_fingerprint` adiciona
  ops, protocols, features, execution, `context_revalidation` e domains. Excluídos por
  decisão: `id`/`version`, `description`/`signals`, `limitations`/`unknowns`,
  `adapter_version` e `native_surface_fingerprint` (carregados à parte).
- **`manifest.features`** (Phase 31/32): vocabulário `"<nome>/v<major>"` com os dez ids
  conhecidos (`handoff/v1`, `verify/v1`, `plan-proposal/v1`, `resolve/v1`,
  `semantic-handoff/v1`, `economy-receipt/v1`, `trace-ref/v1`, `resume/v1`, `delta/v1`,
  `graph-refs/v1`). `supports()` resolve declarado ∪ implícito (`accepts_handoff` →
  `handoff/v1`, op `verify` → `verify/v1`, etc.); ausente significa *não negociado* e o
  ponto de uso degrada — nunca quebra. O kit de conformidade falha quando um feature com
  superfície conhecida é declarado sem backing (`verify/v1` sem op `verify`); ids
  bem-formados desconhecidos são ignorados (forward-declaration).
- **Propagação**: `RegistryRecord.surface`, cache `RegistryCache/v2` (ambos os digests,
  conferidos na leitura — adulterado ou inconsistente é descartado e redescrito),
  `providers health`/`doctor` (`surface:<prefix>`), `ReceiptProvider` +
  `ProviderSection` do explain (`surface_fingerprint`, `native_surface_fingerprint`).
- **Histórico por superfície** (Phases 77–79): `ProviderCapabilityPerformance.surface`
  entra na chave `(provider, capability, surface)`; `score()` só responde para o
  fingerprint exato — mudança de superfície começa história nova em vez de herdar a
  anterior silenciosamente; entradas legadas (`surface=None`) nunca casam com um
  fingerprint real. Mesma regra no cache do registry.
- **Replay/resume**: drift de superfície gravada vs. atual é razão explícita de não
  reprodutibilidade ("provider X surface changed (declared surface fingerprint)") e de
  mismatch de identidade no resume ("provider declared surface changed").
- **Bump `0.1.0 → 0.2.0`**: superfície pública nova (campos de manifest, contrato novo,
  receipt/explain ampliados) — minor por SemVer pré-1.0. Adapters ficam em 0.1.0
  (releases independentes, ADR 0014); matriz atualizada.

## Gates (local — GitHub CI fora de cota)

- `pytest -q`: **passa** (suíte completa, incl. 21 testes novos em
  `tests/test_surface_identity.py`: contrato, determinismo, mudança/estabilidade de
  fingerprint, negociação, cache, health, receipt/explain, performance, replay).
- `ruff check .`: limpo. `mypy src`: limpo (116 arquivos).
- `python -m theforge.contracts.schema schemas`: `ProviderSurfaceIdentity.schema.json`
  novo; `ForgeManifest`/`ExecutionReceipt`/`ExplainReport`/`ProviderPerformance`
  regenerados.
- `python -m build`: `theforge-0.2.0` sdist+wheel ok.
- Golden do explain atualizado (mudança aditiva: `surface_fingerprint`,
  `native_surface_fingerprint` na seção provider).

## Decisões

- `surface_fingerprint`/`capability_fingerprint` são **obrigatórios** no contrato de
  identidade (identidade sem fingerprint não é identidade); `native_surface_fingerprint`
  e `adapter_version` opcionais, `recorded_at` default `""` só para compatibilidade de
  parse.
- O fingerprint ignora `signals`: signals orientam routing, não são forma operacional —
  mas um tamper de signals continua coberto pelo `manifest_sha256` + revalidação
  (testado em `test_registry_cache.py`, atualizado para recomputar os fingerprints ao
  simular adulteração consistente).

## Gaps / próximos passos

- Adapters ainda não declaram `native_surface_fingerprint`/`adapter_version` (Wave C).
- `docs/capabilities.md` não precisou de mudança (features são protocolo, não
  capability); semantic-handoff/delta/graph-refs ficam declaráveis sem consumidor até as
  waves E/F/J.
