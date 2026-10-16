# Release 1 — Painel de aprovação (Wave 10)

## Gates

| Gate | Condição | Estado |
|---|---|---|
| CI | checks obrigatórios nos SHAs exatos | ✅ (`ci-matrix.md`) |
| Security | sem bloqueadores críticos | ✅ (`supply-chain.md`) |
| Build | artefatos válidos (7/7 + npm) | ✅ (`packaging.md`) |
| Compatibility | contratos verificados | ✅ (`compatibility.md`) |
| Packaging | wheels/sdists/npm testados | ✅ |
| E2E | fluxos obrigatórios aprovados | ✅ (`hosts-mcp.md`) |
| Hosts | claims = evidências | ✅ (Copilot=experimental) |
| Portal | build + serve da wheel | ✅ (`portal.md`) |
| Docs | inventário + gaps mapeados | ✅ (`documentation.md`) |
| License | MIT 9/9 | ✅ (`community.md`) |
| Release Notes | rascunhos preparados | ✅ |
| **Owner Approval** | confirmação explícita | ⏳ **PENDENTE** |

## Decisões necessárias do mantenedor

1. **Nomes de distribuição** (bloqueante — `theforge`/`forge-cli`
   ocupados):
   - [ ] PyPI: `the-forge` (aplicado) — alternativa `theforge-core`
   - [ ] npm: `theforge-cli` (aplicado) — alternativa `@theforge/cli`
2. **Versões** (`version-plan.md`):
   - [ ] Aprovar conjunto (7× 0.x + doctor-data 1.0.0)
   - [ ] `forge-doctor-data 1.0.0rc1 → 1.0.0` — promover ou manter RC?
3. **Publicação**:
   - [ ] Configurar Trusted Publishing PyPI/npm (ação manual do owner)
   - [ ] Autorizar criação de tags públicas
   - [ ] Autorizar GitHub Releases
   - [ ] Autorizar `publish` PyPI / `npm publish`
   - [ ] TestPyPI dry-run primeiro? (recomendado)
4. **Limitações aceitas**:
   - [ ] README links relativos quebram no PyPI (F-R1-3)
   - [ ] Copilot = experimental/não verificado
   - [ ] macOS sem runner CI (declarado, não testado)
