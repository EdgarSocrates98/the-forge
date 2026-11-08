# Phase 1 revalidation — 2026-11-08

## Escopo e método

Revalidação read-only dos seis repositórios da Fase 1 no Windows 11, com
working trees locais preservados. O código foi confrontado com os contratos,
testes, instaladores e evidências já existentes; nenhuma capacidade foi
marcada como concluída apenas por existir em documentação.

| Repositório | `main` revalidado | Estado local | Evidência principal |
|---|---|---|---|
| The Forge | `4d132ed` | IMPLEMENTED_AND_TESTED | CI do PR #183 verde; matriz profunda de ajuda `1101/1101` |
| Code Atlas Forge | `19e703a` | IMPLEMENTED_AND_TESTED | suíte `1663 passed, 21 skipped` |
| Forge Lens | `86bd757` | IMPLEMENTED_AND_TESTED | suíte completa e smoke de escala verdes |
| Forge Agent Bridge | `1c56054` | IMPLEMENTED_AND_TESTED | `128 passed`; Ruff verde |
| Product Forge | `79b3a50` | IMPLEMENTED_AND_TESTED | `225 passed, 1 skipped`; Obsidian/URL/Defuddle cobertos |
| Forge Portal | `4f906af` | IMPLEMENTED_AND_TESTED | build, CLI, instalação, browser e gate visual verdes |

As alterações locais encontradas nos checkouts são artefatos de diagnóstico ou
ambiente; não foram apagadas, resetadas nem incluídas neste checkpoint.

## Ownership confirmado

- The Forge continua sendo control plane, catálogo, discovery, routing,
  instalação, contexto e receipts.
- Code Atlas continua sendo responsável por inteligência estrutural, busca de
  código, context packs e grafo de código.
- Forge Lens continua sendo responsável por traces, métricas e evidências de
  execução.
- Agent Bridge continua sendo responsável por sessões, autorizações, eventos e
  integração com providers.
- Product Forge continua sendo responsável por ingestão, conhecimento de
  produto, FTS, entidades e relações.
- Forge Portal continua sendo a camada visual e não duplica os motores acima.

Não foi identificada duplicação que justifique um novo motor de busca, router,
broker de sessões, persistência de traces ou frontend paralelo.

## Knowledge interoperability

Os contratos `KnowledgeSource/v1`, `KnowledgeDocument/v1`,
`KnowledgeChunk/v1`, `KnowledgeEvidence/v1`, `KnowledgeContextPack/v1`,
`KnowledgeRelation/v1` e `KnowledgeImportReceipt/v1` estão implementados no
The Forge com serialização determinística, validação de campos obrigatórios,
proveniência e estados de autorização. O Product Forge preserva o artefato
original, chunks Markdown, hash e receipt; Code Atlas projeta referências
estruturais; Agent Bridge reautoriza o pacote antes da injeção; Lens registra
proveniência sem copiar corpo documental; Portal exibe os dados por adapters
reais.

## Obsidian e Defuddle — avaliação honesta

| Capacidade de referência | Estado | Decisão |
|---|---|---|
| `obsidian-markdown` | IMPLEMENTED_AND_TESTED | importar/exportar Markdown por adapter stdlib, com limites e proteção de paths |
| `obsidian-bases` | PARTIALLY_IMPLEMENTED | validação estrutural versionada; execução de fórmulas/filtros não é alegada |
| `json-canvas` | PARTIALLY_IMPLEMENTED | validação estrutural de nós/arestas; editor/renderização semântica não é alegada |
| `obsidian-cli` | DEFERRED | não é dependência; o caminho stdlib funciona com o aplicativo fechado |
| `defuddle` | IMPLEMENTED_AND_TESTED | adapter opcional, bounded, fail-closed; fallback stdlib permanece padrão |
| `knap` | DEFERRED | não há contrato de host estável nem necessidade comprovada para o fluxo atual; não copiar templates sem caso de uso e testes |

O mecanismo de instalação existente já trata skills/agentes/MCP como
componentes opcionais por host e escopo, preserva arquivos do usuário e
retorna receipts. A integração Obsidian permanece opt-in por
`FORGE_OBSIDIAN_VAULT`; não foi criada uma instalação global concorrente nem
uma dependência obrigatória de Obsidian, Node ou banco vetorial.

As referências externas foram consultadas em 2026-11-08: `obsidian-skills`
(MIT, `main`), `defuddle` (MIT, `main`), `obsidian-importer` (MIT, `master`),
`obsidian-help` (licença não declarada no metadata do GitHub, `master`),
`obsidian-clipper` (MIT, `main`) e `knap` (MIT, `main`). Nenhum código externo
foi copiado; a ausência de uma licença declarada no `obsidian-help` mantém esse
repositório como referência documental, não como dependência distribuída.

## Gates executados

- `npm run build` no Portal: PASS.
- `npm run test:cli` e `npm run test:install` no Portal: PASS (`3/3`, `2/2`).
- `python -m pytest e2e -q` no Portal: PASS (`45 passed, 3 skipped`).
- `visual_probe.py`: PASS, sem axe `serious`/`critical`, sem foco sem anel e
  sem clipping sem `title`.
- `visual_audit.py`: PASS, 214 capturas e zero overflow horizontal.
- Matriz de instalação: PASS (`14/14`).
- Runtime smoke de `--version`/`--help`: PASS (`28/28`).
- PTY Windows com cancelamento pré-mutação: PASS (`14/14`).
- Matriz profunda de `--help`: PASS (`1101/1101`, zero falhas).

## Limitações e próximos incrementos

Os pontos abaixo permanecem honestamente classificados como `DEFERRED` ou
`BLOCKED`, não como falhas escondidas:

1. Paridade ampla Defuddle, renderização Portal em escala e qualidade semântica
   de ranking ainda precisam de benchmarks maiores.
2. Bases/Canvas semânticos e `knap` dependem de contratos de uso que ainda não
   foram demonstrados.
3. Sessão de provider externo e execução cloud permanecem dependentes de
   credenciais/ambiente autorizados.
4. A Fase 2 deve auditar os quatro especialistas sem modificar seus checkouts
   durante esta Fase 1.

O estado correto do checkpoint é `IMPLEMENTED_AND_VERIFIED` para os fluxos
locais cobertos, `PARTIALLY_IMPLEMENTED` para Bases/Canvas e
`DEFERRED`/`BLOCKED` para as dependências externas acima.
