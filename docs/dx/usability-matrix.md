# Usability matrix — personas × tarefas (Phase 13)

Status por célula: **EXECUTED** (rodado nesta sessão, com evidência) /
**PENDING** (não executado — marcado, nunca alegado).

| # | Persona | Tarefa | Status | Evidência |
|---|---|---|---|---|
| 1 | iniciante absoluto | clone → setup → primeiro comando | EXECUTED (the-forge, real bootstrap) | `./setup.sh` → launcher → `theforge` bare summary |
| 2 | iniciante | descobrir o que o CLI faz | EXECUTED (7 repos) | bare invocation mostra resumo + top comandos; `help <verbo>` |
| 3 | iniciante | erro de digitação no verbo | EXECUTED (argparse×4, typer nativo×2) | `instll`→`install`; `analise`→`analyze` |
| 4 | dev integrando uma forja | install → doctor → uninstall | EXECUTED (84+ testes de install no the-forge; suites por repo) | receipts, drift, repair, rollback |
| 5 | dev instalando noutro projeto | escopo project num repo qualquer | EXECUTED | `install auto` + delegação + registry |
| 6 | usuário de host | usar skills via Claude/Devin/Codex | PENDING | estrutura instalada; consumo real pelo host não executado |
| 7 | usuário MCP | handshake → tools/list → call | EXECUTED (forge-doctor-data, real) | 13 tools + invoke PASS; aws FAIL honesto (SDK ausente) |
| 8 | avançado multi-forge | install workspace + fan-out | EXECUTED | `install auto --scope workspace --member` com manifest |
| 9 | troubleshooting | instalação parcial/stale lock | EXECUTED | stale-lock recovery + rollback transacional testados |
| 10 | leitor de docs | links e exemplos válidos | EXECUTED | check_docs: 0 problemas em ~2800 arquivos md |
| 11 | multi-OS | mesmas flows em Linux/macOS | PENDING | só Windows executado; scripts .sh/.ps1 existem |
| 12 | fora de PATH | CLI após novo terminal | EXECUTED | bootstrap publica launcher; testado em shell nova |

## Achados registrados (viraram correção nesta wave)

- `theforge` bare saía com `error: the following arguments are required`
  → agora mostra resumo de produto (tarefa 2).
- `apiforge` bare saía silencioso com exit 0 → resumo adicionado.
- Docs de instalação citavam `theforge repair`/`status` bare — verbos
  vivem sob `install`/`distribution` → corrigido pela divergência do
  inventário + check_docs.
- Em-dash `—` quebrava consoles cp1252 → ASCII nos repos sem utf8-reconfigure.
