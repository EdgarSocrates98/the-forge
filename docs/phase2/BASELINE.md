# Phase 2 — Baseline

Data da leitura: 2026-11-09. Esta auditoria foi revalidada contra os checkouts locais e
os últimos runs públicos do GitHub Actions; não presume que os relatórios da Phase
1.1 ainda sejam atuais.

## Estado dos checkouts

| Repositório | Branch/HEAD observado | Worktree | CI mais recente observado |
|---|---|---|---|
| spark-forge-aws | `phase2/remediate-claims-20261108` / `a86cfa4` | limpo | suíte completa local: 15128 passed/14 skipped; adapter Obsidian, compatibilidade Python 3.10 e smoke S3 controlado verdes; CI remoto `42714263493` verde no mesmo SHA, com 15122 passed/20 skipped nas versões Python 3.10–3.14, wheels, auditoria e claims |
| spark-forge-azure | `phase2/knowledge-freshness-20261108` / `df9f2e6` | limpo | suíte completa local: 3190 passed/9 skipped; freshness, adapter Obsidian e compatibilidade Python 3.10 verdes; CI remoto `42693963092` verde |
| api-forge | `fix/control-plane-windows-concurrency-20261108` / `a24bb3b` | `.codebase-memory/` não rastreado | suíte completa local: 2028 passed/4 skipped; persistência atômica Windows endurecida, Path flavor preservado em fault injection Linux e adapter Obsidian verde; CI remoto `42694647843` verde |
| platform-forge | `phase2/context-integrity-applicability-20261108` / `7e2057f` | `uv.lock` modificado | suíte completa local terminou sem falhas; adapter Obsidian, compatibilidade Python 3.10 e receipt de economia resealado; CI remoto `42692546513` verde |
| the-forge | `cycle-10-apisentinel` / `6ca5ffd` | artefatos de auditoria não rastreados | schemas/contratos, ciclo de vida governado do conhecimento, metadados comuns dos seis contratos Obsidian, runner federado local usando `forge_obsidian`, contratos `ObsidianNoteRef` validados no E2E, matriz instalada Windows/Linux, smoke TTY/cancelamento 14/14 com default cold-start de 6 s; CI remoto `42688316906` verde em pacote Linux/Windows e Python 3.11–3.14; Portal projeta workflows federados e executa investigação governada |
| product-forge | `fix/bridge-embedded-parity-20261108` / `77dde99` | limpo | 291 passed/1 skipped; `-m not benchmark`: 287 passed/1 skipped/3 deselected; Ruff limpo com classificação explícita de `forge_obsidian`; CI remoto `42729793620` verde; ensaio real em tmpfs de 256 KiB converteu ENOSPC no lock em `OBSIDIAN-LOCK-FAILED`/`sync_state=failed` sem nota, receipt ou temporário parcial; benchmark de escala 100/1.000/10.000 passou com pico RSS observado e 10.000/10.000 wikilinks resolvidos; gateway com provider controlado registrando `17/29` tokens no ledger; distribuição `forge-obsidian` construída a partir da fonte canônica e embutida no Product Forge, ciclo de vida captured→validated com evidência, scan bounded até 10.000 e baseline observável com orçamento de contexto/citações fixture, capacidades Obsidian/knowledge publicadas com IDs normativos, export workflow, índice seguro de paths, MCP read-only com 17 tools, Canvas determinístico e `.base` oficial com validação/serialização, catálogo `dashboard_id → YAML`, importação governada de investigações e teste estrutural da pipeline standalone; Actions pinadas por SHA |
| forge-portal | `feat/api-operations-contract-surface-20261108` / `1e85c28` | capturas/auditorias modificadas | build verde, 603 testes de baseline + 21 testes direcionados, Portal de conexão/revogação de vault, descoberta body-free de paths, ciclo de vida de conhecimento no explorador, deep link Obsidian, handoff explícito de investigação para Product Forge, gate visual local, pacote npm sem artefatos e instalação externa com start estático verdes |
| code-atlas-forge | `main` / `e959639` | `.codebase-memory/` e `uv.lock` não rastreados | suíte completa local: 1667 passed/21 skipped; relações documentais body-free verdes; Actions pinadas por SHA |
| forge-agent-bridge | `fix/phase1.1-fast-provider-catalog-20261108` / `5d96989` | `uv.lock` modificado | suíte completa local: 130 passed; reautorização Obsidian verde; CI remoto `42687526019` verde; Actions pinadas por SHA |
| forge-lens | `main` / `2dba4a5` | limpo | suíte completa local terminou sem falhas; adapter sanitizado verde; Actions pinadas por SHA |

Artefatos existentes não foram limpos, resetados ou incluídos em mudanças desta
fase.

## Inventário técnico

| Repositório | Python | Arquivos de teste/host | Arquivos de schema/contrato | Workflows |
|---|---:|---:|---:|---:|
| spark-forge-aws | 1262 | 514 | 101 | 4 |
| spark-forge-azure | 809 | 300 | 40 | 3 |
| api-forge | 1099 | 441 | 103 | 4 |
| platform-forge | 426 | 113 | 30 | 2 |
| product-forge | 169 | 37 | 6 | 2 |
| the-forge | 535 | 221 | 172 | 7 |
| forge-portal | — | 24 | — | 1 |
| code-atlas-forge | 398 | 242 | 23 | 3 |
| forge-agent-bridge | 63 | 20 | 3 | 3 |
| forge-lens | 150 | 63 | 29 | 3 |

## Capacidades existentes relevantes

- The Forge agora possui MCP nativo opcional, instalação project/workspace/user,
  tools estruturadas, confirmação para mutações e `install mcp-verify`.
- Spark Forge AWS já possui MCP, tools especializadas, case store, laboratório,
  claims lock, receipts e instalação. O caminho AWS real deve ser preservado.
- Spark Forge Azure já possui MCP, portal adapter, contratos de decisão, graph,
  installkit, conhecimento de fontes e `mcp-verify`.
- Platform Forge já possui context capsule/ref, economy gateway e knowledge packs;
  o risco P0 é a ordem de redação/hash/persistência e a seleção de applicability.
- API Forge já possui contracts/knowledge, retrieval e gateway/change-control;
  deve receber adapters e projeções, não um segundo motor de busca.
- Product Forge contém a implementação Obsidian mais explícita encontrada:
  validação de Canvas/Bases, import/export Markdown, limites de tamanho/path,
  escrita atômica, baseline/conflict e rollback condicionado por hash.
- Forge Portal já possui páginas de federation, versions, tasks, graph,
  installation e operações plan→apply. A integração de vault deve reutilizar a
  API e o design system existentes.
- Code Atlas já possui grafo/federation e relações `MENTIONS`/`REFERENCES_FILE`;
  notas devem ser relações documentais, não símbolos falsos.
- Forge Agent Bridge possui controles de sessão/contexto e deve continuar sendo
  a fronteira de autorização para contexto externo.
- Forge Lens possui trace store/OTLP e deve receber eventos sanitizados de vault,
  sem persistir corpos de notas por padrão.

## Estado verificável da Phase 2

- The Forge: seis contratos Obsidian fechados, schemas gerados e seeds do fuzz
  universal registrados; o MCP nativo continua limitado às operações realmente
  implementadas.
- Product Forge: parser Markdown aditivo (incluindo aliases, referências de
  bloco, links relativos e anexos), import/export bounded, leitura em lote
  paralela com gate 100/1.000/10.000, plano de sync, baseline/conflict, backup,
  escrita atômica, rollback condicionado por hash, receipt, histórico
  body-free, templates determinísticos e projeções Canvas/Bases estruturais.
- AWS, Azure, API e Platform: adapters read-only com `NoteRef` versionado,
  proveniência, confiança/estado de freshness e redaction de chaves e texto
  sensível; nenhum adapter acessa o vault ou altera cloud.
- Portal: captura/preview/import, export plan→confirm, baseline de atualização,
  conflito explícito, histórico de receipts, restauração protegida por backup e
  gerenciamento visual de conexão/revogação de vault; gate visual de conhecimento
  passou em 8 combinações com axe=0, overflow=0 e foco sem anel=0.
- Portal/The Forge: a jornada Nova investigação agora usa
  `POST /investigations/plan` → aprovação por token →
  `POST /investigations/run`; o run chama a orquestração governada real,
  persiste `OrchestrationReport` redigido e expõe histórico em
  `GET /investigations`. O padrão é `LOCAL_READ`, com riscos adicionais
  explicitamente assinados no plano.

Code Atlas agora possui projeção body-free de relações Obsidian e Forge Lens
possui adapter de receipts sanitizados. O runner local
`scripts/phase2_federated_obsidian_e2e.py` comprova a cadeia com quatro
adapters, Product Forge, Code Atlas, Lens e Agent Bridge; o resultado está em
`docs/phase2/FEDERATED_E2E_EVIDENCE.md`.

O que ainda não está comprovado: geração automática de artefatos em vault real
autorizado a partir do recibo da investigação, falhas reais de disco/permissão e
homologação de entrega em produção. O Portal agora oferece handoff explícito
e auditável do recibo concluído para um documento indexado no Product Forge;
isso não grava automaticamente no Obsidian. A execução da
investigação federada agora é disparada pelo Portal e chama o orquestrador
governado real; o runner Obsidian continua explicitamente fixture-only. O
provisionamento/revogação multiusuário agora
possui jornada local real, com escopo por principal/workspace e revogação sem
exclusão de arquivos; falta validar identidade OIDC e operação em produção.
Rename/delete,
revalidação final, lock concorrente entre processos e benchmark de 10.000 notas
têm cobertura local explícita no Product Forge, mas não são prova de operação em
produção.

## Evidência de CI reproduzida

O run `42515249600` do Spark Forge AWS falhou em `scripts/check_vnext_claims.py`
somente por duas claims numéricas defasadas: `VNX-822` esperava 1371 e a prova
retornou 1374; `VNX-827` esperava 409872 e a prova retornou 410210. As provas
foram executadas localmente contra os arquivos versionados. Os valores foram
atualizados no branch atual, sem remover o gate ou transformar a falha em warning.

## Restrições para a implementação

Não há autorização para cloud real. Fixtures, laboratórios e providers fake são
obrigatórios para testes locais. Vaults reais não serão alterados sem uma raiz
explicitamente autorizada e uma operação plan→confirm→apply.

