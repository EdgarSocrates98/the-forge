# Installation Orchestration

O caminho governado de "preciso de um especialista que não está instalado".

## Pipeline

```text
no_route ──► forge-knowledge ──► InstallationPlanV2 ──► aprovação ──► execução ──► verificação independente
(bootstrap   (como instalar)   (estágios pending)     (humano)      (bootstrap-   (verify_install +
 metadata)                                                     installation)    discover ao vivo)
```

1. **Reconhecer** — `route()` devolve `no_route`; `forge-knowledge` diz o que
   instalar (`intents`, `appropriate_for`).
2. **Planejar** — `plan_installation(entry)` produz `InstallationPlanV2`:
   fetch → verify sha256 → install → verify_install → discover → register,
   tudo `pending`. Entrada sem `distribution` verificável é recusada;
   `version = "latest"` nem chega — o `ForgeRegistryEntry` rejeita não-SemVer.
3. **Aprovar** — `plan.approval.required`: gate humano/policy. Nenhum agente
   aprova ([ADR 0054](adr/0054-agent-authority-model.md)).
4. **Executar** — `bootstrap-installation` (`execute-approved`) coordena os
   estágios; sem evidência de aprovação ele só planeja.
5. **Verificar** — quem instala tem `verify` forbidden: `verify_install` +
   `discover` rodam o binário real; o `HealthReport` vem do especialista.

## Estados

`NOT_INSTALLED` → `INSTALLED`/`INSTALLED_BROKEN`/`INCOMPATIBLE` — descoberta
(`forge-discovery`, autoridade `classify`) rotula; broken/incompatible volta
ao pipeline com novo plano, nunca chute.

## Sem auto-upgrade

`tested_version` é medição, não alvo (§58): versão nova = plano novo +
aprovação nova. Surface drift (`tested_surface` ≠ medido) marca un-fresh nas
três camadas — pacote, skill, registry.

Detalhes da decisão: [ADR 0055](adr/0055-specialist-bootstrap.md).
