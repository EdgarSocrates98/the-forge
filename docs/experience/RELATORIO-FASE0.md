# FASE 0 — Auditoria e fundação (concluída)

> Base do programa `prompt_evo_foco1.md`. Tudo nesta fase é **observado**:
> audit gerado do filesystem, hosts detectados via CLI real, contratos
> congelados como schemas validados. Nada foi presumido.

## Entregáveis

| § | Entregável | Artefato |
|---|---|---|
| 0.1–0.2 | Auditoria das 7 Forjas (CLI, TUI, MCP, install, graph, agents, skills, espelhos, testes) | `scripts/experience/audit_surfaces.py` → `docs/experience/audit-fase0.json` |
| 4.1 | Host Capability Matrix real (versões, launch, MCP, skills, agents, limitações) | `docs/experience/host-capability-matrix.json` |
| 0.3 | Contratos congelados de experiência (7 schemas Draft 2020-12) | `contracts/experience/*.schema.json` + `README.md` |
| 0.5 | Matriz de aceite preenchida com o baseline observado | `scripts/experience/gen_acceptance_matrix.py` → `docs/experience/matriz-aceite.md` |
| 0.6 | Design system baseline (voz, superfícies, saída, TUI, agentes, instalação, docs, economia) | `docs/experience/design-system.md` |

## Inventário observado (audit)

| Forja | Versão | Scripts | TUI | MCP | Install | Graph | Agents | Skills | Espelhos | Testes |
|---|---|---|---|---|---|---|---|---|---|---|
| the-forge | 0.5.0 | 2 | ✓ | — | ✓ | ✓ | 8 (AgentSpec/v1) | 33 | 108 | 157 |
| api-forge | 0.1.0 | 3 | ✓ | ✓ | ✓ | ✓ | 31 | 14 (`.github/skills`) | 136 | 348 |
| spark-forge-aws | 0.5.0 | 2 | ✓ | 145 tools | ✓ | ✓ | 19 | 60 | 190 | 492 |
| spark-forge-azure | 0.1.0 | 1 | ✓ | ✓ | ✓ | ✓ | 40 | 22 | 85 | 273 |
| platform-forge | 0.1.0 | 2 | ✓ | ✓ | ✓ | ✓ | 41 | 12 (`.devin/skills`) | 176 | 103 |
| forge-doctor-data | 1.0.0rc1 | 1 | ✓ | ✓ | ✓ | ✓ | 0 | 0 | 0 | 198 |
| forge-doctor-api | 0.2.0 | 1 | ✓ | ✓ | — | ✓ | 0 | 0 | 1 | 86 |

Fontes canônicas de skill **diferem por repo** (declaradas explicitamente
em `audit_surfaces.py::SKILL_SOURCE` — não há convenção única no
ecossistema): the-forge espelha 3 hosts iguais; api-forge em
`.github/skills`; AWS/Azure em `skills/`; platform em `.devin/skills`;
doctors sem skills hoje.

## Hosts detectados (capability matrix)

| Host | Versão | Launch | MCP | Skills | Agents | Subagents |
|---|---|---|---|---|---|---|
| Devin CLI | 3000.11.3 | interativo/`--`/desktop/acp | `devin mcp add\|list\|login` (4 servers configurados) | `SKILL.md` em `~/.agents/skills`, `.devin/skills`, `.agents/skills` | `.devin/agents` + perfis `run_subagent` | nativo |
| Claude Code | 2.1.295 | interativo/`-p`/`--agent` | `claude mcp add` (health-check em `mcp list`) | `.claude/skills` + plugins | `.claude/agents` + `--agents` | nativo |
| Codex CLI | 0.160.0 | `codex exec`/`mcp`/`sandbox` | `codex mcp` | `.agents/skills` (`$skill`) | `.codex/agents/*.toml` | nativo |
| Copilot CLI | — | **não detectado** | — | — | — | — |

`HOT_RELOAD`, `RESTART_REQUIRED`, `REAL_EXECUTION_TEST` ficam
`UNVERIFIED` até as jornadas da FASE 8 — a matrix marca isso em cada
host, não presume.

## Contratos congelados (§0.3)

Seis schemas novos em `contracts/experience/` + um reutilizado
(`ForgeGraphView/v1` do spark-forge-aws; `forge/InstallReceipt/v1` já
emitido pelos instaladores). Regras congeladas no README do diretório:

- estado só sobe com evidência (`ACTIVE`, `EXECUTION_VERIFIED`,
  `SEMANTICALLY_REVIEWED` exigem campo de evidência);
- `UNVERIFIED`/`BLOCKED`/`NOT_APPLICABLE` são estados de verdade;
- mecanismos de host não são forçados idênticos (§Primeira do operador);
- recusa sempre carrega `unlock`; ambiguidade é `ambiguous`;
- mudança = bump `/v2`, nunca edição in-place.

Os 7 schemas passam `jsonschema.Draft202012Validator.check_schema`.

## Gaps honestos que a FASE 0 deixa explícitos

1. **Doctors têm zero superfície agentic** (sem agents, skills ou
   espelhos) — decisão de produto para FASEs 5–6, não gap acidental.
2. **forge-doctor-api não tem verbo install** — instalação portátil por
   design (`docs/installation/portable-installation.md`); o programa
   avalia se a jornada "install anywhere" pede um lifecycle real.
3. **MCP tools fora do AWS são UNVERIFIED** — os módulos existem, mas só
   o AWS tem lock de superfície contado (145). Handshakes reais: FASE 8.
4. **the-forge não expõe MCP** — é o control plane via Forge Protocol;
   FASE 7 decide se e como publica superfície para hosts.
5. **the-forge `skills_canonical`=33 são skills de workflow** (kiro-*,
   graphify…), não skills de domínio — o catálogo §11 vai distinguir.
6. **Copilot CLI ausente** na máquina do operador — jornadas Copilot
   ficam `NOT_DETECTED`/`NOT_APPLICABLE` até haver host real.

## Verificação

- `pytest tests/test_docs_consistency.py tests/test_doc_drift.py
  tests/test_doc_manifest.py` — verde.
- `docs/INDEX.md` regerado (285 entradas; `docs/experience/` indexado,
  `.kiro/` fora por ADR 0020).
- `ruff check scripts/experience/` — limpo.
- Suíte completa do repo: verde em `main` (4.835 passed na wave de
  remediação, merge #41).

## Próxima fase

**FASE 1 — spark-forge-aws**: gate A (descoberta + jornada de
instalação), gate B (host experience com os mecanismos reais de cada
host), skills/agents catálogo §11, TUI premium, Graph Studio consumível,
docs PT-BR semântica, E2E. Os artefatos da FASE 0 são a base de
verificação: audit antes/depois, contratos congelados, matriz de aceite.
