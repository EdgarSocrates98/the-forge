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
| CI obrigatório verde | PENDENTE | matrizes anteriores e os CIs Azure `42737901068`, API `42736176051`/`42736175647` e Platform `42738344886` estão verdes; no AWS `42737900885` do SHA antigo `02db7ec`, Python 3.11–3.14, wheels e auditoria passaram, mas Python 3.10 terminou `cancelled` no limite; o novo run `42750089008` do SHA `4ada2b7` está `pending`, com matriz 3.10–3.14 e timeout de 180 minutos. O run AWS anterior `42714263493` continua como evidência histórica (`15122 passed/20 skipped`), não como substituto do SHA atual; pacote `forge-obsidian` construído e instalado isoladamente |
| recuperação completa | PARTIAL; ACL de permissão real e disk-full em tmpfs controlado foram validados sem artefato parcial; disk-full em host/vault produtivo e recuperação operacional completa ainda pendentes |

O bloqueio é deliberado: não se transforma fixture, teste ignorado ou execução
local em prova de produção. O próximo aceite requer fechar as pendências de
`REMAINING_RISKS.md`, em especial a homologação produtiva do handoff para
Product Forge, a sincronização revisada no vault, ensaios reais de falha e
homologação remota.
