# Installation Audit — Forge Experience 3.0

## Pipeline real (verificado)

`forge_bootstrap.py` → venv + launcher → `ui/wizard.py` → installkit:
`plan (dry_run)` → `apply (yes)` → `receipt` → `doctor`. Escopos
project/workspace/user, perfis minimal/recommended/full, componentes
opcionais (skills, agents, mcp, tui, graph-studio), hosts configuráveis,
lock com expiração, backups em `<state>/backups/`, drift/repair.

## Bugs confirmados (a corrigir em Cycle 1.1)

### BUG-A (GAP-002) — components podem sumir silenciosamente

`ui/wizard.py:162`: `if "components" in signature(install_fn).parameters`.
Se `install_fn` é `lambda **kw` (wrapper), `signature` mostra só
`VAR_KEYWORD` → `components` nunca passa → usuário escolhe, instalação
ignora. **Fix**: contrato explícito — `install_fn` DEVE aceitar
`components: tuple[str, ...] | None`; wizard passa sempre; sem inspeção
de assinatura.

### BUG-B (GAP-003) — zero hosts vira "all"

`ui/wizard.py:153-158`: `chosen` vazio → `host_arg=None` →
`host=host_arg or "all"` → `_hosts(None)` retorna TODOS os hosts.
Usuário que desmarca tudo instala em todos. **Fix**: valor `none`
explícito no contrato do service; `_hosts("none") → ()`; wizard passa
`"none"`, nunca `or "all"`.

### Verificação adicional

- `install` sem `--yes` recusa `E_NOTAPPROVED`/`FORGE-INSTALL-PLAN-NOT-APPROVED`
  — governança ok.
- `component_options(profile, components)` mapeia perfil+seleção — ok.
- Reinstalação: plano idempotente com drift detection — ok.

## Install Manager (§2.3) — cobertura atual

install/status/update/repair/uninstall/receipt/doctor existem como
verbos/serviços reais por forja (kit ou scripts). Falta: "review changes"
visual e "check compatibility" explícito na TUI.
