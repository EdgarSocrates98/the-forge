# Ecosystem 2.0 — capability matrix

| Componente | Identidade/install | Descoberta runtime | Forge Protocol adapter | Evidência de health real | Estado |
|---|---:|---:|---:|---:|---|
| The Forge | sim | sim | core | sim | READY |
| Data Sentinel | sim | sim | não | local independente | PARTIAL |
| Code Atlas | sim | sim | não | local independente | PARTIAL |
| Forge Lens | sim | sim | não | local independente | PARTIAL |
| Product Forge | sim | sim | não | local independente | PARTIAL |
| Agent Bridge | sim | sim | não | host/auth dependente | PARTIAL |
| Adapters existentes | sim | sim | sim | testes locais | READY |

Regra: metadata bootstrap nunca promove uma superfície a `verified`; somente `describe`/`health` do processo instalado pode fazê-lo.

