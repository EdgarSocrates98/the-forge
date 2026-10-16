# Release 1 — Documentação & first-run

## Inventário existente (the-forge `docs/`)

Já cobre o portal de docs exigido: `docs/installation/` (quickstart PT+EN,
por host: claude-code/codex-cli/devin-cli/copilot-cli, global/workspace/
account/portable, mcp, troubleshooting, uninstall, update-and-repair),
`architecture.md`, `capabilities.md`, `agents.md`, `skills.md`,
`security.md`, `protocol.md`, `real-providers.md`, `adr/`, `tutorials/`,
`versioning.md`, `release-checklist.md`.

## Gaps de documentação pública

| Gap | Ação | Onde |
|---|---|---|
| READMEs com links relativos (346 nos 7 pacotes) quebram no PyPI | aceitar como limitação conhecida OU hook de build | `packaging.md` F-R1-3 |
| Golden paths por persona (API Engineer, Data Engineer AWS/Azure, Platform Engineer, Multi-Forge) | verificar existência/validade | `golden paths` abaixo |
| Release notes por repo | rascunhos neste diretório | `publishing-plan.md` |
| Texto de lançamento / FAQ | rascunho | `community.md` |

## Golden paths — estado

Guias existentes sob `docs/installation/` + `docs/tutorials/` + READMEs
dos especialistas. Execução real nesta baseline:

- **Multi-Forge Workspace** ✅ executado: `forge-cli install
  forge-doctor-data forge-doctor-api --yes` → 2/2 OK (33.7s).
- **API Engineer** ✅ handoff real `api.analyze` (cycle-10.2).
- **Data Engineer AWS** ✅ `pyspark.static-analysis` → SF-PY-002 real.
- **Data Engineer Azure** — adapter instalado; handoff não re-executado
  nesta baseline (declarado).
- **Platform Engineer** — idem (declarado).

## Primeira experiência (medida, não inventada)

Instalação de 2 Forjas pelo CLI publicável: **33.7s**, 4 passos após
`npx` (selecionar → confirmar → instalar → verify). Mensagens claras,
logs em `.forge-cli/logs/`, `.env` modelo criado com aviso explícito.

## Idiomas

PT-BR + EN já existem (quickstart.md / quickstart.en.md,
troubleshooting PT+EN). Release notes: PT-BR + EN.
