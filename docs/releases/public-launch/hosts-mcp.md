# Release 1 — Hosts & MCP (Waves 5/7) + Forge CLI público (Wave 3)

## Forge CLI — pacote npm (evidência executada 2026-10-16)

| Verificação | Resultado |
|---|---|
| `npm pack` (tsup build) | `theforge-cli-0.1.0.tgz`, 191.2 kB, 8 arquivos |
| Instalação do tarball (`npm install --prefix`) | OK em `/tmp/r1-cli/global-test` |
| Bin `forge-cli` executa pós-instalação | banner + `--help` OK |
| **Gate 3 — instala ≥2 Forjas em workspace descartável** | `forge-cli install forge-doctor-data forge-doctor-api --yes` → **2/2 OK em 33.7s**, cada uma verificada via `--help` |
| Jornada não-interativa | `--all/--only/--yes`, `--profile recommended`, `--scope`, `--host`, `--components`, `--plan`, `doctor` |
| Lifecycle | install/update/repair/rollback/uninstall/pin — coberto por `tests/lifecycle-matrix.test.ts` (8/8) |
| Node | >=20 (engines) |

Comando público pós-publicação: `npx theforge-cli` (ou
`npm i -g theforge-cli`). Renome aplicado nesta baseline — ver
`version-plan.md`.

## Hosts (evidência cycle-10.2, código inalterado)

| Host | Estado | Suporte anunciável |
|---|---|---|
| Claude Code | ✅ handshake real `✔ Connected` (probe via-host) | suportado |
| Codex | ✅ handshake real | suportado |
| Devin | ✅ handshake real | suportado |
| Copilot | ⚠️ NOT_TESTED ao nível do host | **declarar como experimental/não verificado** |

Regra anunciável: só o que tem evidência. Copilot aparece como
"experimental, unverified on host" nas release notes — não como
"supported".

## MCP — matriz (cycle-10.2 `hosts-mcp.md`, 6/6 handshakes)

- `tools/list` + handshake real por especialista via adapter
  `theforge-*-adapter` (instalado no interpretador do especialista).
- Escopo/permissões: providers não confiáveis não executam (boundary
  verificada); mutation verbs exigem aprovação humana.
- Gate 7 sustentado: integrações anunciadas = as evidenciadas.
