# Phase 2 — Baseline

Data da leitura: 2026-11-09. Esta auditoria foi revalidada contra os checkouts locais e
os últimos runs públicos do GitHub Actions; não presume que os relatórios da Phase
1.1 ainda sejam atuais.

## Estado dos checkouts

| Repositório | Branch/HEAD observado | Worktree | CI mais recente observado |
|---|---|---|---|
| spark-forge-aws | `phase2/remediate-claims-20261108` / `4e4661f` | limpo | adapter Obsidian local verde; sem workflow publicado para este branch |
| spark-forge-azure | `phase2/knowledge-freshness-20261108` / `55e3859` | limpo | adapter Obsidian local verde; sem workflow publicado para este branch |
| api-forge | `fix/control-plane-windows-concurrency-20261108` / `029b9aa` | `.codebase-memory/` não rastreado | `API Forge CI` e Windows anteriores verdes; novo commit em validação |
| platform-forge | `phase2/context-integrity-applicability-20261108` / `2e38343` | `uv.lock` modificado | adapter Obsidian local verde; sem workflow publicado para este branch |
| the-forge | `phase2/baseline-observability-20261108` / `338864a` | artefatos de auditoria não rastreados | `release-gates` verde: fuzz, build, schemas e smoke |
| product-forge | `fix/bridge-embedded-parity-20261108` / `45c1df5` | `.coverage` não rastreado | CI verde em `45c1df5`; commits posteriores aguardam novo run |
| forge-portal | `feat/api-operations-contract-surface-20261108` / `1d56614` | capturas/auditorias modificadas | build, 595 testes e gate visual local verdes |
| code-atlas-forge | `main` / `19e703a` | `.codebase-memory/` e `uv.lock` não rastreados | sucesso |
| forge-agent-bridge | `fix/phase1.1-fast-provider-catalog-20261108` / `4c58e94` | `uv.lock` modificado | sucesso |
| forge-lens | `main` / `86bd757` | limpo | sucesso |

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
  validação de Canvas/Bases, import/export Markdown e limites de tamanho/path.
  A escrita atual ainda precisa ser atomicamente segura e não sobrescrever
  alterações manuais.
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
  bloco, links relativos e anexos), import/export bounded, plano de sync,
  baseline/conflict, backup, escrita atômica, receipt, histórico body-free,
  templates determinísticos e projeções Canvas/Bases estruturais.
- AWS, Azure, API e Platform: adapters read-only com `NoteRef` versionado,
  proveniência, confiança/estado de freshness e redaction de chaves e texto
  sensível; nenhum adapter acessa o vault ou altera cloud.
- Portal: captura/preview/import, export plan→confirm, baseline de atualização,
  conflito explícito e histórico de receipts; gate visual de conhecimento passou
  em 8 combinações com axe=0, overflow=0 e foco sem anel=0.

Code Atlas agora possui projeção body-free de relações Obsidian e Forge Lens
possui adapter de receipts sanitizados; ambos são pontos de integração reais,
mas ainda não são uma execução cross-Forge automática.

O que ainda não está comprovado: E2E cross-Forge em um ambiente instalável,
execução efetiva Code Atlas/Lens a partir do Portal, geração de artefatos em
vault real autorizado e testes de carga de 100/1.000 notas.

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

