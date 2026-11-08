# Phase 2 — Baseline

Data da leitura: 2026-11-08. Esta auditoria foi feita contra os checkouts locais e
os últimos runs públicos do GitHub Actions; não presume que os relatórios da Phase
1.1 ainda sejam atuais.

## Estado dos checkouts

| Repositório | Branch/HEAD observado | Worktree | CI mais recente observado |
|---|---|---|---|
| spark-forge-aws | `docs/live-lab-rerun-20261108` / `0270a1e` | limpo | `main` falhou no gate de claims; branch atual passou |
| spark-forge-azure | `main` / `dd9a82f` | limpo | sucesso |
| api-forge | `fix/control-plane-windows-concurrency-20261108` / `b6b592e` | `.codebase-memory/` não rastreado | sucesso em `main` |
| platform-forge | `main` / `0ee7534` | `uv.lock` modificado | sucesso em `main` |
| the-forge | `main` / `fad8122` | artefatos de auditoria não rastreados | MCP nativo mesclado no PR 190; matriz Python 3.11–3.14 em Ubuntu/Windows passou |
| product-forge | `fix/bridge-embedded-parity-20261108` / `8404a05` | `.coverage` não rastreado | sucesso |
| forge-portal | `feat/api-operations-contract-surface-20261108` / `e68dd8e` | capturas/auditorias modificadas | sucesso em `main` |
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

