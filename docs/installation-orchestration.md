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

## Caminho zero-touch para Forges locais

`install auto --yes` é o caminho recomendado após instalar uma ou mais Forges.
Ele lê os manifests de `~/.forge/installations/`, propaga escopo, host, profile e
componentes para cada CLI da família e, ao final, sincroniza os adapters locais no
`providers.toml` do usuário. O sync é idempotente: altera apenas o bloco marcado
como gerenciado, preserva providers escritos pelo usuário e faz refresh live para
que somente entries `ready` e trusted entrem no routing.

Para instalações existentes, sem repetir instalação:

```bash
theforge providers sync --dry-run   # revisão do plano
theforge providers sync --yes       # aprovação e refresh
theforge providers health
```

Precedência de runtime: variável de ambiente de conta persistida no manifesto,
`python.executable`/`cli.shim` do manifesto e, por fim, o venv registrado. Isso
permite manter checkouts, venvs, skills, knowledge e evals fora do workspace do
usuário sem depender de PATH global.

Registro de provider e configuração MCP são etapas separadas. O sync registra o
adapter Forge Protocol para routing; a configuração MCP de cada host permanece
responsabilidade da CLI especialista durante `install auto --components mcp`.

## Estados

`NOT_INSTALLED` → `INSTALLED`/`INSTALLED_BROKEN`/`INCOMPATIBLE` — descoberta
(`forge-discovery`, autoridade `classify`) rotula; broken/incompatible volta
ao pipeline com novo plano, nunca chute.

## Sem auto-upgrade

`tested_version` é medição, não alvo (§58): versão nova = plano novo +
aprovação nova. Surface drift (`tested_surface` ≠ medido) marca un-fresh nas
três camadas — pacote, skill, registry.

Detalhes da decisão: [ADR 0055](adr/0055-specialist-bootstrap.md).
