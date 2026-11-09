# Phase 2 — Remaining Risks

1. **CI remoto:** branches de trabalho ainda precisam de runs verdes dos
   workflows obrigatórios.
2. **Sistema instalado:** a composição instalada do Product Forge é uma lane
   opt-in e está explicitamente skipped.
3. **Falhas de infraestrutura:** disk full, permission denied real e processo
   encerrado durante escrita ainda não foram ensaiados no ambiente alvo.
4. **Concorrência multiprocessos:** há lock por documento e teste de threads;
   falta um teste subprocesso real em Windows e Linux.
5. **Multiusuário:** o vault é configuração do serviço, com raiz autorizada e
   escopo de workspace; provisioning/revogação de vault por usuário não existe.
6. **Portal federado:** o Portal opera os fluxos de conhecimento, mas ainda não
   dispara o runner federado de fixtures como uma operação runtime.
7. **Parser Obsidian:** Canvas/Bases são validações/projeções estruturais; não
   há promessa de reproduzir todo o runtime do aplicativo ou fórmulas.
8. **Observabilidade de escala:** memória, scan, busca, reindexação e token
   budget ainda precisam de baseline quantitativo completo.

Até que esses riscos sejam fechados, a recomendação é manter sync revisado,
fixtures-only nos E2E e confirmação humana para toda mutação.
