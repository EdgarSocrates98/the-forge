---
sdd: 1
feature: EXPORTACAO
phase: design
profile: dev
status: done
upstream:
  path: docs/sdd/EXPORTACAO/define.md
  sha256: f71c61b9c00df3da1f06c04339ad348ea496f6da16607b5275f553f53572dd25
files:
  - path: src/modulo.py
    action: create
    reason: novo modulo
decisions:
  - id: D1
    choice: implementacao direta
    rejected: []
    rollback: remover o modulo criado
covers:
  - part: exportador
    acceptance: [AC1]
---

# Design
