---
sdd: 1
feature: EXPORTACAO
phase: define
profile: dev
status: done
upstream:
  path: docs/sdd/EXPORTACAO/explore.md
  sha256: a0d2ce26d7b9ffce6d98131cdb5030edf863b2fc0f640dadf6e0083d919af6f1
hypothesis:
  claim: a feature melhora o fluxo declarado
  prediction: o criterio de aceite passa no gate
  experiment: rodar o criterio verificado
acceptance:
  - id: AC1
    statement: exporta o relatorio
    verified_by:
      kind: test
      ref: tests/test_exportacao.py::test_exporta
success:
  - id: SC1
    metric: criterio verificado pelo gate
    source: relatorio do `check` desta fixture
out_of_scope: []
change_kinds: []
---

# Define
