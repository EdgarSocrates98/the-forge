# Phase 2 — Remaining Risks

1. **CI remoto global:** The Forge e Product Forge já possuem runs verdes
   (`42557439135`, `42557064576`); ainda falta uma matriz consolidada de runs
   verdes para todos os branches especialistas e para os repositórios sem
   workflow publicado nesse branch.
2. **Matriz instalada:** 12/12 wheels Python passaram em venvs isolados no
   Windows e os dois projetos Node passaram build/pack; falta executar a mesma
   matriz Python em Linux, além de verificar project/workspace/user em
   instalações limpas e o Portal instalável fora do checkout.
3. **Falhas de infraestrutura:** disk full e permission denied possuem fault
   injection estruturado, mas ainda não foram ensaiados em filesystem real;
   process kill possui cobertura determinística local, sem substituir o ensaio
   operacional.
4. **Multiusuário:** provisioning e revogação por principal/workspace agora
   existem no Product Forge e no Portal, com raiz autorizada, tokens escopados,
   resposta sem caminho físico e revogação que não apaga arquivos. Falta ensaio
   com identidade OIDC e operação concorrente em ambiente produtivo.
5. **Portal federado:** o Portal opera os fluxos de conhecimento, mas ainda não
   dispara o runner federado de fixtures como uma operação runtime.
6. **Parser Obsidian:** Canvas/Bases são validações/projeções estruturais; não
   há promessa de reproduzir todo o runtime do aplicativo ou fórmulas.
7. **Observabilidade de escala:** memória, scan, busca, reindexação e token
   budget ainda precisam de baseline quantitativo completo.

Até que esses riscos sejam fechados, a recomendação é manter sync revisado,
fixtures-only nos E2E e confirmação humana para toda mutação.
