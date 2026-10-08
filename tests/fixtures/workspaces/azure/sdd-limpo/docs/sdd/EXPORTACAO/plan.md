---
sdd: 1
feature: EXPORTACAO
phase: plan
profile: dev
status: done
upstream:
  path: docs/sdd/EXPORTACAO/design.md
  sha256: e8dfd6056a39e3aeb361ebd7b9233075b29c1ecfa042ced9bf3d2ca55440a8c5
tasks:
  - id: T1
    files: [src/exportador.py]
    covers: [AC1]
    test:
      path: tests/test_exportacao.py
      name: test_exporta
---

# Plan
