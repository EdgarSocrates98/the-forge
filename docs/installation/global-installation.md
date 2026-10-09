# Instalação global (escopo user) — the-forge

Instala uma vez para todos os projetos do usuário:

```bash
theforge --scope user
```

Escreve em `~/.claude/`, `~/.agents/`, `~/.config/<host>/` e config MCP
global. Combinável com instalações de projeto: o nível mais específico
(`project`) sempre prevalece.
