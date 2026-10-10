# AI Hosts

## Hosts suportados

| Host | Arquivos de integração | Formato |
|---|---|---|
| Claude Code | `.claude/agents/`, `.claude/skills/` | mirror renderizado |
| Devin | `.devin/skills/`, `AGENTS.md` | mirror renderizado |
| Codex | `.agents/skills/`, `.codex/agents/*.toml` | mirror renderizado |
| GitHub | `.github/agents/`, `.github/skills/` | mirror renderizado |

## Contrato de mirrors

Fontes canônicas editáveis: `agents/*.md`, `skills/<nome>/SKILL.md`
(e `agentic/agents/*.toml` no the-forge). Mirrors são **saída de render**
— nunca edite um mirror. Sincronização:

- api-forge: `apiforge agents sync` (+ `lint`/`check`/`references`/`audit`)
- spark-forge-aws: `python scripts/sync_skills.py`
- the-forge: `python scripts/agentic/render_skills.py` + `audit_assets.py`

Regra dos AGENTS.md: "mudou skill/instrução de host → edite os hosts e rode
o audit de assets".

## Ativação

`forge hosts` detecta/ativa; `forge install apply` escreve a integração
com plano→aprovação. Verificação: `install mcp-verify` (handshake real).

## Fontes

`docs/agentic.md` e `docs/AGENTS.md` do the-forge; `AGENTS.md` por forja.
