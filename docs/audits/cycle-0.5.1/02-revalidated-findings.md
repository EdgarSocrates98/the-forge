# Revalidated findings

| finding from Cycle 0.5 | current result | evidence boundary |
|---|---|---|
| Bridge classified unknown native events as errors | PASSED | `runtime.unknown` regression tests |
| retention/replay could duplicate or hide truncation | PASSED | event/byte retention, marker and cursor tests |
| secret data could cross event boundaries | PASSED | nested/adversarial redaction tests |
| discovered specialists were not uniformly routable | PASSED | router, conformance and federation tests |
| provider registry could contain stale paths | PASSED | sync/health/repair flow and registry tests |
| federated execution lacked a reproducible local receipt | PASSED | 8-scenario The Forge lab |
| Portal lacked a real API Operations entry point | PASSED | merged Portal PR #88 |
| cloud/external AI proof was absent | BLOCKED | no credentials/session in environment |

Não foram encontrados gaps novos que justificassem refatoração dos especialistas
já corretos. A abordagem permaneceu aditiva: adapters finos, contratos existentes
e Portal como experiência unificada.
