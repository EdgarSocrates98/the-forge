# Advanced Reference

## Contratos versionados

| Contrato | Onde |
|---|---|
| `theforge/<Name>/v1` | `schemas/` no the-forge (regen: `python -m theforge.contracts.schema schemas`) |
| `forge/CommandInventory/v1`, `forge/DocDivergence/v1`, `forge/DocManifest/v1` | `docs/reference/*.generated.json`, `docs/knowledge-program/` |
| `ForgeKnowledge/v1` | `forge-knowledge/*.json` |
| `AgentSpec/v1` | `agentic/agents/*.toml` |
| `ForgeGraphView/v1` | `graphview.py` adapters |
| `forge/SpecialistDelegationResult/v1` | saída de `task run` |

## ADRs

`docs/adr/` do the-forge — incluindo 0054 (agent authority), 0056 (host
adaptation), 0057 (Loop Factory), 0058 (installkit).

## Docs-as-code

- `scripts/docs/doc_inventory.py` — comandos do parser real (nunca regex)
- `scripts/docs/check_docs.py` — gate de drift documentado↔real
- `scripts/docs/doc_manifest.py` — inventário de docs + link check
- `scripts/docs/doc_index.py` — `docs/INDEX.md` gerado (IA de 7 seções)
- `scripts/docs/gen_hub.py` — esta hub, seção Which Forge (determinística)

## Gates de qualidade por repo

- `tests/test_doc_manifest.py` — zero links quebrados em docs ativos
- `check_docs` — zero divergência comando↔doc
- suites + `ruff` + gates específicos (`lab run-all`, `evals run`,
  `sync_skills`, `audit_assets`, parity checks)

## Fontes primárias

`docs/dx/standard-v1.md` (Forge Documentation & CLI Experience Standard),
`docs/knowledge-program/` por repo (inventários e relatórios).
