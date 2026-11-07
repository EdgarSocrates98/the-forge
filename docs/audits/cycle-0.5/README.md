# Cycle 0.5 — compatibilidade cross-repository

Este diretório contém a auditoria executável de compatibilidade, hardening e
preparação E2E dos oito repositórios do ecossistema FORGE.

## Regras da auditoria

- A referência funcional é o `origin/main` observado em 2026-11-07; o The
  Forge usa uma branch de implementação cujo HEAD é o mesmo commit de
  `origin/main` até que uma correção seja proposta.
- Worktrees sujos foram preservados. Arquivos gerados por auditorias e locks
  locais não fazem parte desta mudança.
- A auditoria é local-first, read-only contra serviços externos e não cria o
  repositório `api-sentinel-forge`.
- Um manifest, um help de CLI ou uma classe não são prova de integração. A
  classificação usada nos relatórios é `IMPLEMENTED_AND_TESTED`,
  `IMPLEMENTED_NOT_TESTED`, `DECLARED_ONLY`, `PARTIAL`, `UNAVAILABLE`,
  `BROKEN`, `DEPRECATED` ou `UNKNOWN`.
- “UNADAPTED” e “SURFACE_ONLY” são estados de laboratório para componentes que
  possuem superfície própria, mas ainda não possuem adaptador comprovado pelo
  contrato do The Forge.

## Ordem dos artefatos

1. `repository-baseline.md` — referência, versões, estado de checkout e
   superfícies públicas.
2. `00-executive-summary.md` — decisão consolidada.
3. `01-architecture-inventory.md` — responsabilidades e dependências reais.
4. `02-capability-ownership.md` — proprietário canônico por capacidade.
5. `03-contract-inventory.md` — contratos, versões e evidências.
6. `04-compatibility-matrix.md` — produtor/consumidor e estado de prova.
7. `05-schema-evolution-policy.md` — política de evolução semântica.
8. `06-findings-and-remediation.md` — achados com reprodução e correção.
9. `07-security-assessment.md` — limites de rede, filesystem, agentes e
   evidências.
10. `08-installation-compatibility.md` — matriz de instalação e CLI.
11. `09-e2e-lab-specification.md` — laboratório local reproduzível.
12. `10-test-results.md` — comandos e resultados efetivamente executados.
13. `11-unresolved-risks.md` — bloqueios e riscos residuais.
14. `12-api-sentinel-readiness.md` — gate formal GO/CONDITIONAL GO/NO-GO.
15. `13-final-homologation.md` — homologação final do ciclo.

Os nomes podem ser publicados progressivamente; nenhum item é considerado
passado enquanto não houver comando, commit e evidência correspondentes.
