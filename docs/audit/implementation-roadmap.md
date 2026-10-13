# Implementation roadmap — Agentic Ecosystem Control Plane

Ordem de cycles conforme §22, mapeada para o que já existe.

## Cycle A — The Forge Core (esta branch)

1. `src/theforge/lifecycle/` — `forge/SpecialistLifecycleState/v1`:
   17 estados + transições válidas + guardas. Reutiliza
   InstallationManifest/registry para estado persistido.
2. `src/theforge/discovery.py` — sinais de projeto (arquivos → sinais →
   candidatos) com `evidence` e `confidence_basis` declarado (sem scores
   inventados: `detected`/`not-detected`/`ambiguous`).
3. `src/theforge/host_detect.py` — `HostDetectionResult`: env markers +
   binário no PATH + config dirs; campos `evidence`/`limitations`.
4. `src/theforge/activation.py` — `HostActivationPlan`/`Receipt` +
   outcome ACTIVE_NOW/RESTART_REQUIRED/UNSUPPORTED.
5. `src/theforge/delegation.py` — `SpecialistDelegationRequest/Result/v1`
   + stage tracking (PREPARED…COMPLETED/BLOCKED); execução = argv real.
6. CLI: `specialists list|status|doctor`, `hosts list|status|activate`,
   `task plan|run|explain` — reusando registry/capabilities/install.

## Cycle B — Spark Forge AWS

`forge.agentic.json` manifest (workflows, coordinators, skills, mcp,
delegation entry points reais) + `manifest` verb opcional; verificação.

## Cycle C — API Forge

Idem + activation-plan vs activated honesto.

## Cycle D — Integration E2E

Cenário A (devin+aws) e B (claude+api) com evidência real do que o
ambiente permite; resto UNVERIFIED honesto.

## Cycles E–G — azure / platform / doctors

Manifests equivalentes; doctors mantêm fronteira read-only.

## Cycle H — Full E2E + relatório

Matriz final §23 por repo; UNVERIFIED onde não executado.

## Não-objetivos

- Não reinstalar o que já existe (install auto, registry, contracts).
- Não fingir ativação de host sem evidência.
- Não transformar skill em capability.
