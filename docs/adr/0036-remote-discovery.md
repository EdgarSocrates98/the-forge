# ADR 0036 — Remote discovery: requirement-driven, fit honesto, sem instalação

- Status: aceito (2026-10-07)
- Cycle 4, Wave E — phases 22–26, 92

## Contexto

Com fontes configuráveis (Wave C) e cliente http read-only (Wave D), falta a
peça que responde "ninguém instalado satisfaz o requirement — quem lá fora
declara que satisfaz?". O risco a evitar: transformar descoberta em canal de
instalação implícita, ou reportar claims remotos com a mesma força de fit
verificado localmente.

## Decisão

1. **`RemoteProviderCandidate/v1`** como contrato próprio — proveniência
   (`source`, `registry`, `freshness`, `retrieved_at`), claims (`publisher`,
   `distribution`, `signature_state`, `manifest_sha256`) e fit (`fit`,
   `matched`, `missing`, `unknowns`, `limitations`). Não é `RegistryRecord` e
   nunca vira um sem a Wave F.

2. **Fit remoto limitado a `declared`/`partial`.** Uma entry de registry
   declara ids de capability, runtime e plataformas — nada de actions,
   evidência, features ou surface. Toda dimensão exigida que a metadata não
   pode provar vira `unknowns` (e derruba o fit para `partial`). FULL remoto
   não existe: FULL exige manifest verificado, que exige instalação.

3. **Contradições duras excluem; ausência apenas marca.** `requires_network`
   declarado vs `offline_required`/`network_allowed=false`,
   `requires_credentials` vs `credentials_allowed=false`, platforms sem
   interseção → `entries_excluded` com a razão. Campos não-declarados nunca
   eliminam — viram `unknowns` (a mesma disciplina do engine local: ausência ≠
   negação).

4. **Local primeiro, sempre.** `discover` negocia os instalados antes de ler
   qualquer fonte; `FULL` local pula a rede (`--remote` para forçar). Fontes
   disabled/stale/inválidas são reportadas em `sources_skipped`/`limitations`,
   nunca escondidas.

5. **Discovery é um beco sem saída por design.** O comando imprime candidatos
   e termina com "No action was taken." — invariante `action_taken: false`.
   Não há flag de instalação, não há follow-up automático; a ponte para a
   Wave F é o usuário escolher um candidato e pedir um plano.

## Consequências

- Gate da wave: nada é instalado — a camada inteira produz só
  `RemoteProviderCandidate` + `DiscoveryReport`.
- A UX de missing-capability do §26 existe verbatim no renderer.
- Ordenação determinística sem métricas de marketplace — `declared > partial`,
   provider, versão desc, registry.
- Wave F consome um candidato por vez para montar `InstallationPlan/v2`.
