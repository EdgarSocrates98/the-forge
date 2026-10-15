# Dependency map — ecosystem-2026

## Arquitetura de dependência (invariantes do the-forge)

```text
forge-cli ──────────────────────────────┐
                                        │ opera instalação/lifecycle
forge-portal ─── portal_api contract ──►│
                                        ▼
   host (claude/codex/devin) ──► the-forge (control plane: WHO/WHEN/HOW)
                                        │ Forge Protocol (subprocess + JSON)
                                        ▼
                              adapters/* (instalados no interpretador
                                        │  de cada especialista)
              ┌──────────┬─────────────┼────────────┬──────────┐
              ▼          ▼             ▼            ▼          ▼
        spark-forge  spark-forge   api-forge  platform-forge  forge-doctor-*
           -aws        -azure                                       (indep.)
```

## Regras de dependência (contratos)

- the-forge core **nunca** importa `sparkforge_aws`/`apiforge`/`platformforge`/`forge_doctor_*` — providers só via Forge Protocol.
- Adapters são os únicos que importam especialistas; nunca importam `theforge`.
- Especialistas e Doctors: **independentes** — nenhuma dependência obrigatória de the-forge/CLI/Portal.
- Contratos `theforge/<Name>/v1`; regeneration via `python -m theforge.contracts.schema schemas`.

## Dependências entre specs do programa (ordem)

```text
cyc0-01 (baseline)
  ├─► cyc8-01 manifest ──► cyc8-05 cli-release ──► cyc8-06 portal-release-ui
  ├─► cyc8-02 packaging ──► cyc8-04 ci-rc ──► cyc10-01 onboarding
  ├─► cyc8-03 supply-chain ──► cyc8-04
  ├─► cyc9-01 lab-coordinator + cyc9-02 eval-integrity
  │     └─► cyc9-03 multiforge + cyc9-04..09 cenários + cyc9-10 portal-lab
  └─► cyc10-02 docs/github ──► cyc10-03 adoption-readiness
                                  ▲ (exige Cycle 9 aprovado p/ claims)
```

## Observações de acoplamento (baseline)

- `platform-forge`: 9 arquivos com `/home/edgar` — acoplamento a filesystem de dev (P0).
- `forge-portal` consome `portal_api` — versão do contrato a mapear no manifesto (cyc8-01).
- `forge-cli` gerencia instalação dos 9 — é o ponto único de lifecycle (state.json confirma).
- Doctors publicam `lab` (corpora precision/recall) — reusáveis pelo Forge Lab sem acoplamento.
