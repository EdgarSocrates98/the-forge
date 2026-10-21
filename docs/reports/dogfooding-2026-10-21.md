# Dogfooding — 2026-10-21: observação de compatibilidade (lf-0027)

Sessão conforme [`docs/dogfooding.md`](../dogfooding.md). Esta entrada não é
uma observação de problema novo — registra a decisão de escopo que permitiu
trabalho dentro do Feature Freeze.

## Observação (taxonomia de dogfooding.md §72)

### O1 — compatibilidade de ecossistema sancionada: descoberta universal de especialistas

```text
type: compatibility drift
context: spec lf-0027 (forge-cli factory/specs/active) — Forges irmãos
         precisam de um contrato estável de capability + uma camada de
         descoberta que funcione sem import de sibling, sem checkout git
         e sem execução arbitrária
expected: the-forge já detém lifecycle, registry, routing, delegação e
          transporte governado; a descoberta deveria reutilizá-los
observed: o gap era real — não existia SpecialistCapability/v1, não havia
          distinção DISCOVERED/VERIFIED e nenhuma leitura de
          manifestos/metadados de pacote de siblings
evidence: forge-cli docs/integration/confirmed-gaps.md + existing-contracts.md
          + audit-core.md; implementação em src/theforge/discovery.py +
          contracts/specialist_capability.py
severity: note
```

O trabalho entra no freeze como **compatibilidade com surfaces de
especialistas** (feature-freeze.md permite: bugfix, security,
compatibilidade, performance, docs, testes). Não adiciona subsistema novo:
reusa `Registry`/`SubprocessTransport`/`check_health`, receituários de
`_installkit`/`specialists`, `redact` para persistência e o padrão de
contratos dataclass + schema gerado.

Delimitação registrada para o freeze: `SpecialistDelegation/v1` (fase 3 da
spec) e `EvidenceHandoff/v1` (fase 10) ficam **deferidos** — o lf-0027 cobre
o contrato de capability e a descoberta; delegação cross-especialista e
ciclo-prevenção são trabalho posterior explícito.
