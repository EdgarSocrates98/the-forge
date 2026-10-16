---
id: cyc101-04
title: portal-multiforge-e2e
status: active
created: 2026-10-15
owner: forge-portal
scope: forge-portal+the-forge
cycle: "10.1"
wave: 3
priority: p0
risk: high
agent: devin
source: prompt_evo_cycle10.1.md §4 (GAP 02), §11 Wave 3
verification:
  - npm test && npm run typecheck && npx playwright test
---

# Portal cross-forge E2E real + testes visuais + segurança

## Escopo

- §4.1: Portal via interface oficialmente suportada (adapter real do the-forge,
  não mock como evidência principal), Linux.
- §4.2 catálogo: instalada / ausente / incompatível / parcialmente configurada /
  erro de init / desatualizada.
- §4.3 capabilities reais: disponibilidade, versões, componentes, hosts
  compatíveis, limitações — nada não suportado exibido como disponível.
- §4.4 operações: install preview → plan → review → confirm → execute → verify →
  receipt → status → repair → update → uninstall (apenas ambiente descartável).
- §4.5 observabilidade: run ids, histórico, findings, evidence, receipts, erros,
  status de ferramentas, métricas.
- §4.6 `/lab`: receipts reais, sete laboratórios, histórico, UNVERIFIED, sem dados,
  exportação; comparação baseline vs Forge-enabled se dados/contratos bastarem.
- §4.7 Playwright: Chromium + Firefox/WebKit quando disponíveis; desktop + mobile;
  loading/erro/navegação/acessibilidade; screenshots sem dados sensíveis.
- §4.8 segurança: loopback default, sessão, CSRF, CORS/Origin, path traversal,
  command injection, validação de payload, sanitização de logs, confirmação em
  ações mutáveis.

## Aceite

- `docs/certification/cycle-10.1/portal-e2e.md` com fluxo completo e evidências
  reproduzíveis (run ids, receipts, screenshots).
- Suite visual commitada no repo e verde localmente.
