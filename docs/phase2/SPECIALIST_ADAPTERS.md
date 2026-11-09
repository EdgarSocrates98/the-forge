# Phase 2 — Specialist Adapters

| Forge | Saída | Política |
|---|---|---|
| Spark Forge AWS | `ObsidianNoteRef/v1` para diagnóstico Spark | fixtures/receipts; sem cloud no E2E |
| Spark Forge Azure | `ObsidianNoteRef/v1` com freshness | ausência de data não vira `fresh` |
| API Forge | referências de endpoint/contrato | preserva API IR e change-control |
| Platform Forge | incident/runbook/review | não executa recursos do vault |

Integrações complementares:

- Code Atlas cria relações documentais `MENTIONS`/`REFERENCES_FILE`, sem falsos
  símbolos de código;
- Agent Bridge aplica allowlist, workspace, principal, sessão e reautorização;
- Forge Lens recebe receipts/traces sanitizados;
- Forge Portal apresenta captura, preview, import, export revisado, conflitos,
  histórico, rollback e deep link guardado para Obsidian.

O catálogo federado do Product Forge publica, com implementação CLI/MCP
correspondente, os workflows `obsidian.preview`, `obsidian.import`,
`obsidian.sync.plan`, `obsidian.sync.apply`, `knowledge.evidence.list` e
`knowledge.context.project`. O Portal projeta esses workflows separadamente de
capabilities nativas, evitando declarar como capability algo que o resolver do
The Forge não consegue executar.

O runner `scripts/phase2_federated_obsidian_e2e.py` confirmou quatro notas
exportadas e round-trippadas, uma relação Atlas, um span Lens e autorização do
Bridge, sempre com `cloud_access=false`.
