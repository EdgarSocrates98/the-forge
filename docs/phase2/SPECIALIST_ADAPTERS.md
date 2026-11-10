# Phase 2 — Specialist Adapters

| Forge | Saída | Política |
|---|---|---|
| Spark Forge AWS | `ObsidianNoteRef/v1` para diagnóstico Spark | fixtures/receipts; sem cloud no E2E |
| Spark Forge Azure | `ObsidianNoteRef/v1` com freshness | ausência de data não vira `fresh` |
| API Forge | referências de endpoint/contrato | preserva API IR e change-control |
| Platform Forge | incident/runbook/review | não executa recursos do vault |

Os quatro adapters foram revalidados em 2026-11-10 com seus testes de projeção
e lint: AWS (`02db7ec`, 2 passed), Azure (`27dd3f4`, 2 passed), API
(`58a6117`, 2 passed) e Platform (`cc938d3`, 2 passed). Além dos campos
estruturados, `title` e `summary` agora passam pela mesma redaction antes de
serem escritos no Markdown; os testes confirmam que tokens, passwords e
segredos de fixture não aparecem no corpo das notas.
Eles são deliberadamente read-only e não declaram `obsidian.import`,
`obsidian.export` ou `obsidian.sync`; esses fluxos continuam pertencendo ao
   Product Forge por meio da distribuição técnica `forge-obsidian`; exigem a
   publicação/pin dessa distribuição antes de consumo direto pelos adapters.

Integrações complementares:

- Code Atlas cria relações documentais `MENTIONS`/`REFERENCES_FILE`, sem falsos
  símbolos de código;
- Agent Bridge aplica allowlist, workspace, principal, sessão e reautorização;
- Forge Lens recebe receipts/traces sanitizados;
- Forge Portal apresenta captura, preview, import, export revisado, conflitos,
  histórico, rollback e deep link guardado para Obsidian.

O catálogo federado do Product Forge publica, com implementação CLI/MCP
correspondente, os workflows `obsidian.preview`, `obsidian.import`,
`obsidian.export`, `obsidian.sync.plan`, `obsidian.sync.apply`, `knowledge.evidence.list` e
`knowledge.context.project`. O Portal projeta esses workflows separadamente de
capabilities nativas, evitando declarar como capability algo que o resolver do
The Forge não consegue executar.

O runner `scripts/phase2_federated_obsidian_e2e.py` confirmou quatro notas
exportadas e round-trippadas, uma relação Atlas, um span Lens e autorização do
Bridge, sempre com `cloud_access=false`.
