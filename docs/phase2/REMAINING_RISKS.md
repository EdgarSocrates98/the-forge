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
6. **Parser Obsidian:** Canvas continua sendo validação/projeção estrutural e
   não há promessa de reproduzir o runtime do Canvas. Bases agora têm geração,
   serialização e validação do YAML oficial; filtros/fórmulas continuam sem
   avaliador próprio e dependem do runtime do Obsidian.
7. **Observabilidade de escala:** baseline local agora cobre scan, importação,
   resolução de wikilinks, exportação atômica, reindexação/busca SQLite/FTS e
   pico de alocação Python, orçamento estimado do contexto de recuperação e
   qualidade de citações fixture (precision/recall/completude) e o registro de
   tokens no gateway com provider controlado em 100/1.000/10.000 notas. Token
   usage real de provider continua `NOT_RUN`, pois exige provider governado;
   `tracemalloc` não substitui RSS. O wall-clock
   de 10.000 arquivos recém-criados teve uma amostra Windows de 16,90 s,
   enquanto a importação direta em árvore quente ficou em ~6–8 s; ambos ficam
   no recibo para tendência, sem transformar uma meta arbitrária em gate.
8. **Distribuição técnica neutra:** `forge_obsidian` já está extraído, testado,
   construído como wheel/sdist `forge-obsidian` e incluído no wheel do Product
  Forge. O Product Forge agora também contém a pipeline standalone
  `.github/workflows/publish-forge-obsidian.yml`, com build único, checksum,
  Trusted Publishing/OIDC e instalação limpa de verificação. Ainda não foi
  executado um dispatch remoto nem consumido com versão fixada pelos quatro
  adapters. Até esse gate, os especialistas permanecem corretamente limitados
  a projeções read-only `ObsidianNoteRef/v1`.

Até que esses riscos sejam fechados, a recomendação é manter sync revisado,
fixtures-only nos E2E e confirmação humana para toda mutação.
