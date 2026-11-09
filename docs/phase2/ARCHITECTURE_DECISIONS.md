# Phase 2 — Architecture Decisions

## AD-01 — The Forge é dono dos contratos

Os contratos `theforge/Obsidian*` são versionados no The Forge. Especialistas
produzem adapters finos e mantêm seus motores de domínio; nenhum adapter cria um
segundo motor de busca, sync ou autorização.

## AD-02 — Product Forge é a implementação de referência do vault

O Product Forge implementa parser/projeção Markdown, validação de Canvas/Bases,
planos, escrita atômica, receipts e rollback. A extração para um pacote neutro
continua uma evolução futura, não uma capacidade alegada antes de existir.

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
