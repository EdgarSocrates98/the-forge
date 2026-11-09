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
| Portal prático para fluxos implementados | PASS local; Nova investigação tem seleção de evidências, plano assinado, execução governada, histórico, recibo exportável e handoff explícito para Product Forge; conhecimento tem vault escopado, descoberta body-free de paths, preview, import/export, conflitos, histórico e deep link Obsidian |
| Obsidian opcional e funcional | PASS por design/testes locais; sem Obsidian o restante do ecossistema continua operacional |
| Bases/Canvas compatíveis com sintaxe declarada | PASS de contrato: Canvas estrutural; Bases YAML oficial com serializer/validador, sem execução de fórmulas |
| E2E federado reproduzível | PASS fixture-only; 4 notas round-tripped, Atlas/Lens/Bridge e conflito manual |
| instalação simples | PASS local; 12/12 wheels Python no Windows e Linux WSL2, matriz limpa project/workspace/user, Portal instalado fora do checkout com start estático, Product Forge, TTY/TUI 14/14 e MCP real passaram |
| CI obrigatório verde | PASS local para as matrizes completas disponíveis: AWS `15128 passed/14 skipped`, Azure `3190/9`, API `2028/4`, Platform sem falhas, Code Atlas `1667/21`, Bridge `130`, The Forge `42688316906` (pacote Linux/Windows e Python 3.11–3.14) e Product Forge `e68555f` (`290 passed/1 skipped`); CI remoto de API Sentinel, Code Atlas, Data Sentinel, Forge Lens, Agent Bridge, The Forge e Product Forge verde; pacote `forge-obsidian` construído e instalado isoladamente; runs remotos das matrizes especialistas de AWS/Azure/API/Platform ainda não consolidados |
| recuperação completa | PARTIAL; faults reais pendentes |

O bloqueio é deliberado: não se transforma fixture, teste ignorado ou execução
local em prova de produção. O próximo aceite requer fechar as pendências de
`REMAINING_RISKS.md`, em especial a homologação produtiva do handoff para
Product Forge, a sincronização revisada no vault, ensaios reais de falha e
homologação remota.
