# Phase 2 — Architecture Decisions

## AD-01 — The Forge é dono dos contratos

Os contratos `theforge/Obsidian*` são versionados no The Forge. Especialistas
produzem adapters finos e mantêm seus motores de domínio; nenhum adapter cria um
segundo motor de busca, sync ou autorização.

## AD-02 — `forge_obsidian` é o núcleo técnico do vault

O Product Forge mantém a implementação canônica em `forge_obsidian`, um
namespace técnico extraído do módulo legado e sem dependência do runtime
Product Forge. Ele implementa parser/projeção Markdown, validação de
Canvas/Bases, planos, escrita atômica, receipts e rollback. O import path
`product_forge.knowledge.obsidian` é uma fachada compatível. A publicação como
distribuição separada e a conformidade dos quatro adapters são gates seguintes;
não são alegadas como concluídas.

Evidência: Product Forge commit `4cdf153`, 276 testes aprovados e 1 skip esperado, lint verde,
wheel Product Forge e wheel/sdist `forge-obsidian` construídos pelo fluxo
wheel-from-sdist, com importação validada em ambientes isolados.

## AD-03 — Mutação sempre é explícita

O modo padrão é leitura/preview ou export-only. Sync bidirecional exige baseline,
hash, plano, confirmação, snapshot, verificação pós-escrita e receipt. Conflito
não usa last-write-wins.

## AD-04 — Estado de integração é body-free

Code Atlas recebe relações documentais, Forge Lens recebe traces sanitizados e
Agent Bridge trata o conteúdo do vault como não confiável. Bodies de notas não
são persistidos nesses outputs por padrão.

## AD-05 — Segurança precede conveniência

O vault deve estar configurado pelo serviço e, quando usado, dentro de
`FORGE_OBSIDIAN_ALLOWED_ROOT`. O Portal não aceita um caminho físico arbitrário
para escrever. `.forge`, locks, backups e receipts recusam symlink/reparse.

## AD-06 — Fixtures não são cloud

Todo E2E atual é local/fixture-only. Nenhuma autorização de AWS, Azure ou vault
pessoal foi introduzida para fazer os testes passarem.
