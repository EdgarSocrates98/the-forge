# ADR 0007 — ContextPack por referência

- Status: aceito (2026-10-02)

## Decisão
O ContextPack lista paths, sha256, bytes e o motivo da seleção, sem conteúdo. O provider lê só os paths permitidos. Há budget por perfil (64 KB / 256 KB / 1 MB) e exclusões registradas.

## Motivo
Economia de contexto, verificabilidade (o hash prova o que foi entregue) e nenhum conteúdo de workspace persistido nos runs.
