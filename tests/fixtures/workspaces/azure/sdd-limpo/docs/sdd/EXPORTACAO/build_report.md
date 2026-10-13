---
sdd: 1
feature: EXPORTACAO
phase: build_report
profile: dev
status: done
upstream:
  path: docs/sdd/EXPORTACAO/plan.md
  sha256: 9cf1ac67395aa8e433ee4b182e71c329e4f678e8a05d267b7456693e698ce6c2
tasks:
  - id: T1
    status: done
    red:
      command: pytest tests/test_exportacao.py::test_exporta
      exit: 1
    green:
      command: pytest tests/test_exportacao.py::test_exporta
      exit: 0
claims:
  - text: feature concluida conforme o plan
    evidence_ref: tests/
---

# Build report
