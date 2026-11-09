# Phase 2 — Remaining Risks

1. **CI remoto global:** The Forge e Product Forge já possuem runs verdes
   (`42564466899`, `42564466922`); ainda falta uma matriz consolidada de runs
   verdes para todos os branches especialistas e para os repositórios sem
   workflow publicado nesse branch.
2. **Matriz instalada:** 12/12 wheels Python passaram em venvs isolados no
   Windows e Linux WSL2; a matriz limpa do wheel The Forge passou
   project/workspace/user com apply/uninstall; o Portal também foi instalado
   fora do checkout e respondeu por CLI/TUI/status/start estático. O risco de
   distribuição restante é operacional (OIDC/CI global), não o caminho local.
3. **Falhas de infraestrutura:** disk full e permission denied possuem fault
   injection estruturado, mas ainda não foram ensaiados em filesystem real;
   process kill possui cobertura determinística local, sem substituir o ensaio
   operacional.
4. **Multiusuário:** provisioning e revogação por principal/workspace agora
   existem no Product Forge e no Portal, com raiz autorizada, tokens escopados,
   resposta sem caminho físico e revogação que não apaga arquivos. Falta ensaio
   com identidade OIDC e operação concorrente em ambiente produtivo.
5. **Entrega entre superfícies:** o Portal executa a investigação governada em
   runtime e oferece um handoff explícito, autenticado e auditável do recibo
   concluído para um documento indexado no Product Forge. A materialização no
   Obsidian continua deliberadamente separada: exige o fluxo revisado de
   preview/plan/confirm/sync, evitando escrita automática no vault. O runner
   federado de fixtures permanece uma evidência independente e deliberadamente
   local.
6. **Parser Obsidian:** Canvas/Bases são validações/projeções estruturais; não
   há promessa de reproduzir todo o runtime do aplicativo ou fórmulas.
7. **Observabilidade de escala:** memória, scan, busca, reindexação e token
   budget ainda precisam de baseline quantitativo completo.

Até que esses riscos sejam fechados, a recomendação é manter sync revisado,
fixtures-only nos E2E e confirmação humana para toda mutação.
