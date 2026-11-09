# Phase 2 — Final Acceptance

Estado global: **BLOCKED para aceite final**.

## Critérios

| Critério | Estado |
|---|---|
| comportamento existente preservado | PASS local |
| contratos, adapters e proveniência | PASS local |
| conteúdo recuperável e sem overwrite silencioso | PASS local |
| classificação/autorização/contexto válido | PASS local |
| histórico auditável e outputs body-free | PASS local |
| Portal prático para fluxos implementados | PASS local; Nova investigação agora tem seleção de evidências, plano assinado, execução governada e recibo exportável |
| sem Obsidian ainda funcional | PASS por design/testes locais |
| Bases/Canvas compatíveis com sintaxe declarada | PASS estrutural |
| E2E federado reproduzível | PASS fixture-only |
| instalação simples | PASS local; 12/12 wheels Python no Windows e Linux WSL2, matriz limpa project/workspace/user, Portal instalado fora do checkout com start estático, Product Forge, TTY/TUI 14/14 e MCP real passaram |
| CI obrigatório verde | PASS para The Forge (`42564466899`, `42564466922`); Product Forge validado localmente em `6d74dbd`; não consolidado para todos os branches especialistas |
| recuperação completa | PARTIAL; faults reais pendentes |

O bloqueio é deliberado: não se transforma fixture, teste ignorado ou execução
local em prova de produção. O próximo aceite requer fechar as pendências de
`REMAINING_RISKS.md` e repetir os gates.
