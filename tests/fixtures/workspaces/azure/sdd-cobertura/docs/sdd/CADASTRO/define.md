---
sdd: 1
feature: CADASTRO
phase: define
profile: dev
status: done
hypothesis:
  claim: a feature melhora o fluxo declarado
  prediction: o criterio de aceite passa no gate
  experiment: rodar o criterio verificado
acceptance:
  - id: AC1
    statement: cadastra o cliente
    verified_by:
      kind: command
      ref: cadastro check --id
  - id: AC2
    statement: rejeita duplicado
    verified_by:
      kind: command
      ref: cadastro check --dup
success:
  - id: SC1
    metric: criterio verificado pelo gate
    source: relatorio do `check` desta fixture
out_of_scope: []
change_kinds: []
---

# Define
