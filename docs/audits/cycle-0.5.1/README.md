# Cycle 0.5.1 — federated closure

Este diretório registra a revalidação do ecossistema FORGE contra o Prompt Mestre
`FORGE_CYCLE_0.5.1`. Os estados usados neste relatório são `PASSED`, `FAILED`,
`BLOCKED`, `NOT_RUN` e `NOT_APPLICABLE`.

O ciclo fechou a parte determinística local: Agent Bridge, roteamento do The
Forge, laboratório federado e a superfície API Operations do Portal. A prova de
provider externo/cloud permanece explicitamente fora da homologação porque não
havia credenciais/autenticação disponíveis no ambiente.

## Entregáveis

- [Resumo executivo](00-executive-summary.md)
- [Baseline](01-main-baseline.md)
- [Achados revalidados](02-revalidated-findings.md)
- [Agent Bridge](03-agent-bridge-remediation.md)
- [Roteamento](04-provider-routing-closure.md)
- [Conformance](05-contract-conformance.md)
- [Laboratório](06-e2e-laboratory.md)
- [Portal](07-portal-api-operations.md)
- [Segurança](08-security-assessment.md)
- [Instalação](09-installation-and-portability.md)
- [Testes](10-test-results.md)
- [Compatibilidade](11-compatibility-matrix.md)
- [Riscos](12-remaining-risks.md)
- [API Sentinel readiness](13-api-sentinel-readiness.md)
- [Homologação final](14-final-homologation.md)

As evidências JSON sem segredos ficam em `evidence/`.
