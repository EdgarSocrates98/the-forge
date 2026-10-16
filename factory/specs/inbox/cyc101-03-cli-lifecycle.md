---
id: cyc101-03
title: cli-lifecycle-matrix
status: inbox
created: 2026-10-15
owner: forge-cli
scope: forge-cli
cycle: "10.1"
wave: 2
priority: p0
risk: high
agent: devin
source: prompt_evo_cycle10.1.md §5 (GAP 03), §11 Wave 2
verification:
  - npm test && npm run typecheck
---

# Forge CLI: homologar lifecycle completo (install→update→rollback→uninstall)

## Escopo

- Executar a matriz §5.1 em Linux real, ambiente descartável (`FORGE_HOME` isolado):
  fresh install, reinstall (idempotente), update check, compatibility check,
  update plan/confirm/verify, receipt, failure→recovery/rollback, uninstall.
- Cenários §5.2: fresh install, reinstall, update, downgrade suportado, rollback,
  repair (só assets gerenciados), drift detection, uninstall (só recursos
  gerenciados), partial failure multi-forge, version mismatch provider×contrato.
- Regras §5.3: nunca sobrescrever silenciosamente `.env`, host configs, skills/
  agents personalizados, arquivos de projeto, entradas manuais do registry.
  Manifests + ownership ledger + receipts como prova.
- Versionamento §5.4: integrar `forge/EcosystemCompatibility/v1`; testar stable,
  RC, previous-compatible, incompatible, missing, corrupted metadata.
- Reexecutar testes antes bloqueados por ausência de Linux real (§5.5).

## Aceite

- `docs/certification/cycle-10.1/cli-lifecycle.md` com cada cenário, comando,
  resultado e evidência (receipt/diff de filesystem).
- Testes automatizados novos permanecem no repo e no CI.
