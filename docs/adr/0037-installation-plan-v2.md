# ADR 0037 — InstallationPlan v2: plano determinístico, aprovação explícita, execução fora do escopo

- Status: aceito (2026-10-07)
- Cycle 4, Wave F — phases 27–30

## Contexto

Discovery (Wave E) produz candidatos; o passo seguinte natural — "instale-o" —
é exatamente onde supply-chain vira exploitável. O spec manda evoluir o
InstallationPlan com cuidado: plano primeiro, sem `pip install` arbitrário,
versão pinned ou referência imutável, fluxo de aprovação completo.

`InstallationPlan/v1` já existe, mas é outro artefato: o diagnóstico de "o que
falta para rodar este plano" persistido nos runs. Reusar o nome para a nova
semântica seria confundir diagnóstico com provisão.

## Decisão

1. **`theforge/InstallationPlan/v2` como contrato separado** (classe
   `InstallationPlanV2`). v1 permanece o artefato de diagnóstico de runs;
   v2 é o plano de provisão de candidato remoto. Mesma família de schema,
   versões distintas — a semântica nova não carrega a bagagem do v1.

2. **`planning_only=True` literal no schema.** O contrato rejeita qualquer
   outro valor — a impossibilidade de executar é tipada, não convencional.

3. **`latest` rejeitado no `__post_init__`.** Versão precisa ser SemVer
   pinned; `pip-package` exige `package`+`version`. Distribuições sem
   referência imutável nem chegam a virar plano.

4. **Stages governados e ordenados** (`INSTALL_STAGES`): plan → approval →
   download → verify → isolated-install → provider-check →
   surface-fingerprint → health. O contrato valida ordem e unicidade; todos
   nascem `pending`.

5. **Aprovação registrada, não implicada.** `--approve` grava
   `granted_by`/`granted_at` no documento. `approval.required=false` sem
   `granted=true` é ContractError — um plano não pode pular o próprio gate.

6. **Rollback como dados.** `restore-previous` quando já existe install
   (captura versão + manifest sha + surface fingerprint anteriores), senão
   `remove-new` — o ambiente alvo (`venv:providers/<id>-<ver>`) é descartável
   por construção.

7. **Resolução estrita.** `install plan` busca `provider@version` exato na
   fonte; ausente → erro listando versões disponíveis. Fonte stale →
   limitation explícita no plano.

## Consequências

- O gate da wave vale: nenhum efeito colateral — download/verify/install são
   descrições de stage, não código de efeito.
- Quando a execução chegar (milestone futuro), ela herda: pins, hashes,
   ambiente isolado, checks e rollback — o desenho já está no contrato.
- Dependências não-pinned e ausência total de hashes viram `limitations` —
   aprovação informada, não bloqueio silencioso nem permissividade.
