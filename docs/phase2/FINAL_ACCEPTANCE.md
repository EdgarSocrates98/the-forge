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
| Portal prático para fluxos implementados | PASS local; 624 testes Angular, build de produção e suíte browser completa `10 passed` validaram Nova investigação, federação, Graph Studio, instalação, estados degradados, seleção de evidências, plano assinado, execução governada, histórico, recibo exportável e handoff explícito para Product Forge; conhecimento tem vault escopado, descoberta body-free de paths, preview, import/export, conflitos, histórico e deep link Obsidian |
| Obsidian opcional e funcional | PASS por design/testes locais; sem Obsidian o restante do ecossistema continua operacional |
| Bases/Canvas compatíveis com sintaxe declarada | PASS de contrato: Canvas estrutural; Bases YAML oficial com serializer/validador, sem execução de fórmulas |
| E2E federado reproduzível | PASS fixture-only; 4 notas round-tripped, Atlas/Lens/Bridge e conflito manual |
| instalação simples | PASS local; 12/12 wheels Python no Windows e Linux WSL2, matriz limpa project/workspace/user, Portal instalado fora do checkout com start estático, Product Forge, TTY/TUI 14/14 e MCP real passaram |
| CI obrigatório verde | PASS | CIs Azure `42737901068`, API `42736176051`/`42736175647` e Platform `42738344886` estão verdes; o AWS `42752023082` concluiu `success` no SHA `8006321` com Python 3.10–3.14, wheels Ubuntu/Windows, audit e OTel; o run antigo `42737900885` permanece apenas como histórico cancelado; pacote `forge-obsidian` construído e instalado isoladamente |
| recuperação completa | PARTIAL; ACL de permissão real e disk-full em tmpfs controlado foram validados sem artefato parcial; disk-full em host/vault produtivo e recuperação operacional completa ainda pendentes |

O bloqueio é deliberado: não se transforma fixture, teste ignorado ou execução
local em prova de produção. O CI remoto está fechado; o aceite global ainda
requer fechar as pendências de `REMAINING_RISKS.md`, em especial a
homologação produtiva do handoff para Product Forge, a sincronização revisada
no vault, ensaios reais de falha, OIDC multiusuário e provider governado.
