# Loop Factory

Loop Factory transforma "peça a um agente para construir" numa linha de montagem
visível. Cada tarefa é um **spec** em Markdown e a pasta onde ele mora *é* o
estado dele. Agentes implementam e verificam; **nunca decidem o que construir**
([ADR 0057](adr/0057-loop-factory.md)).

```
inbox/            active/              archive/
não iniciado  →   agente construindo → revisto + aceito
               ↑   (só review aceito   ↑
                   move adiante)
```

A regra que governa tudo: **automatize implementação e verificação, não decisões
de produto.** Se um spec não tem uma decisão, a pergunta fica registrada como
aberta — ninguém inventa direção.

## Setup neste repo

O CLI é uma ferramenta de desenvolvimento (não é dependência de runtime — o core
continua stdlib-only). Instalado uma vez a partir do checkout vizinho:

```bash
python -m pip install -e ../Loop-Factory   # ou o clone equivalente
.venv/Scripts/loop-factory doctor          # saúde: git + CLIs de agente + specs
```

No Windows o binário mora na venv: `.venv/Scripts/loop-factory <cmd>`.

## Layout

```
factory/
  specs/{inbox,active,archive}/   ← o estado é a pasta (versionado)
  templates/{spec,review}.md      ← pontos de partida
  prompts/  runs/  reviews/  logs/ ← artefatos gerados (gitignored)
```

`factory/specs/` é fonte de verdade e entra no git. `prompts/`, `runs/`,
`reviews/` e `logs/` são trilha de auditoria gerada — leia-os, mas não os trate
como autoridade.

## O loop

1. **`scan`** — inspeciona inbox + active.
2. **Grill gate** — specs novos são interrogados *uma pergunta por vez* antes do
   dispatch (dono da decisão, fora de escopo, risco, versão mínima). Respostas
   gravadas na seção `# Grill Gate` do spec; `doctor` marca specs sem gate.
3. **`dispatch --agent <codex|claude> --stage`** — escreve o prompt em
   `factory/prompts/`, grava o run record `planned` e move o spec para
   `active/`. `--execute` só quando o usuário pedir execução ao vivo e o CLI do
   agente existir.
4. **Implementar** — só os critérios de aceitação, no estilo do código.
5. **Verificar** — rodar *todos* os comandos do frontmatter `verification:` e
   guardar a saída como evidência. Falha → spec fica em `active/` com nota em
   `factory/runs/`; nunca se enfraquece critério para passar.
6. **`review <id> --agent <...>`** — prompt de revisão contra o diff.
7. **`archive <id> --accepted`** — só depois de review aceito. `--accepted` é
   obrigatório de propósito: nada sai de `active/` sem passe confirmado —
   decisão humana, como o gate de aprovação do Forge.
8. **`backprop --agent <...>`** — se implementar mudou como o sistema funciona,
   sincroniza specs/docs sem mudar intenção de produto.

## Modo autônomo

Um passe sem humano: scan → filtra specs `grill: completed` (os demais ficam
"needs grilling" — nunca se gilla sozinho) → stage → implementa → verifica →
**para no review** (não arquiva) → reporta built/skipped/failed-verification.

## Como compõe com The Forge

- O grill gate do spec é a fronteira de decisão humana — o mesmo papel que
  `--approve` e os trust gates têm na execução.
- `verification:` deve apontar para os gates reais do repo
  (`pytest`, `ruff`, `mypy`, `scripts/agentic/audit_assets.py`) — verificação
  independente, evidência capturada.
- Implementações de specs seguem as invariantes do core (AGENTS.md): agentes do
  loop não têm autoridade extra — mesma autoridade fechada de
  [agents.md](agents.md).
- Não confundir com o workflow Kiro (`.kiro/specs/`, spec-driven com 3 fases de
  aprovação): Loop Factory é a fila operacional de tarefas pequenas e
  verificáveis; Kiro segue para features com spec completa.
