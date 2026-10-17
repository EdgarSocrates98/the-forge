# Cycle 11.2 — Hosts/skills/agents E2E real (P2-003)

Escopo: tentativa REAL nesta máquina (2026-10-17 ~16:30 -03) — detecção
de hosts, doctor, validate/plan, sem nenhum registro falso.

## Ambiente real

- `forge-cli` no PATH via npm global: `forge-cli@npm:theforge-cli@0.2.0
  -> ./Documentos/projetos/forjas/forge-cli` — **link ao checkout local**
  (dev build em feat/c11-2-bc), não o tarball publicado. Versão
  reportada 0.2.0.
- Dirs de host presentes: `~/.claude`, `~/.codex`, `~/.devin`,
  `~/.config/devin`, `~/.copilot`, `~/.cursor` (implícito pela detecção),
  `~/.claude.json`, `~/.codex/config.toml`.
- `~/.forge-cli/` existe; único conteúdo: `cache/pypi/apiforge-af.json`
  de 06:27 (sessão anterior) — **nenhuma escrita nova durante estas
  consultas** (`find -newermt '1 hour'` vazio).

## Comandos executados — saídas reais

```text
$ forge-cli hosts list
claude — integração presente · 2.1.295 · autenticação não verificada
codex — integração presente · 0.159.0 · autenticado
devin — configurado · 3000.11.92 · autenticação não verificada
cursor — integração presente · 3.24.18 · autenticação não verificada
copilot — integração presente · Runs the GitHub Copilot CLI. · autenticação não verificada
```

```text
$ forge-cli doctor --json   (forge/DoctorReport/v1, score 88, 25 checks)
pass       hosts.codex.detected     — codex detectado e autenticado (auth=verified)
unverified hosts.claude.detected   — auth não verificável (state=integrated, no auth probe)
unverified hosts.copilot.detected  — idem (mcp-config.json + ~/.config/gh)
unverified hosts.cursor.detected   — idem (~/.cursor/mcp.json)
unverified hosts.devin.detected    — state=configured (~/.devin + ~/.config/devin)
fail       system.workspace.access  — /tmp não é workspace forge
fail       installation.forge-dir.absent — nada instalado (verdadeiro)
```

```text
$ forge-cli hosts validate claude the-forge --json
{"ok": false, "checks": [{"id":"config-file","result":"pass",
 "detail":"/home/edgar/.claude.json"},
 {"id":"mcp-key","result":"fail","detail":"the-forge"}]}

$ forge-cli hosts plan claude the-forge --json
{"host":"claude","forge_id":"the-forge","plan":null,
 "detail":"host sem integração documentada"}

$ forge-cli registry     → 7 dists catalogadas, todas "—" (não instaladas)
$ forge-cli mcp          → "nenhuma Forja instalada/encontrada para MCP"
```

## Interpretação honesta

- **Detecção funciona de verdade**: 5 hosts detectados com evidência de
  config real; auth só é marcada `verified` onde existe probe documentado
  (codex) — os demais ficam `unverified`, nunca inferidos. Versão do
  copilot reporta o nome do pacote (`Runs the GitHub Copilot CLI.`) —
  evidência real do que o probe retornou, não inventado.
- **Nada foi registrado**: nenhum `hosts register --yes` foi executado —
  plan/validate são read-only e mostraram corretamente "não registrado"
  (mcp-key fail). the-forge sem integração documentada → `plan:null`
  honesto em vez de um plano inventado.
- **Nenhuma Forja instalada via registry** nesta máquina → o caminho
  MCP-via-venv (`{binDir}/apiforge-mcp` etc.) não pôde ser exercitado
  E2E; `mcp` reporta o vazio honestamente.

## Não exercitado (segue OPEN)

- `hosts register` real + validação pós-escrita + rollback real num host
  de verdade (requer consentimento — escreve `~/.claude.json` etc.).
- Instalação registry real de uma Forja + `mcp --verify` contra o server
  real dela + tool allowlisted (depende de SAFE_TOOL_CALLED em main).
- Skills/agents publicados nos hosts (`.claude/agents`, `.codex/agents`)
  não foram verificados contra um host rodando — só a config estática.

## Veredito

IN_PROGRESS — detecção/doctor/validate/plan exercitados de verdade com
resultados honestos; registro real, MCP vivo e skills/agents nos hosts
seguem sem prova E2E.

## Risco residual

Baixo: detecção é read-only e provou evidência real; o que falta provar é
a escrita — que por desenho exige `--yes` explícito do operador.
