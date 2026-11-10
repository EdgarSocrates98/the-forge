# Phase 2 — Remaining Risks

1. **CI remoto global:** todas as matrizes locais dos especialistas e dos
   componentes federados passaram na revalidação atual. The Forge `42688316906`,
   Agent Bridge `42687526019`, Product Forge `42729793620`, Azure `42737901068`,
   API `42736176051`/`42736175647` e Platform `42738344886` possuem runs verdes.
   O novo AWS `42737900885` terminou `cancelled`: Python 3.11–3.14, wheels e
   auditoria passaram, mas Python 3.10 terminou `cancelled` no limite do job.
   O AWS anterior `42714263493` é mantido apenas como evidência histórica.
   Também passaram
   API Sentinel, Code Atlas, Data Sentinel e Forge Lens. O
   AWS remoto fechou 15122 passed/20 skipped em Python 3.10–3.14, incluindo
   claims, locks, bundle offline, evals, wheels e auditoria. Como hardening adicional, a auditoria local de
   supply chain percorreu 15 repositórios, 50 workflows e 335 ações externas:
   todas agora usam SHAs imutáveis; a ação local `./` do Forge Doctor Data é a
   única exceção intencional.
2. **Matriz instalada:** 12/12 wheels Python passaram em venvs isolados no
   Windows e Linux WSL2; a matriz limpa do wheel The Forge passou
   project/workspace/user com apply/uninstall; o Portal também foi instalado
   fora do checkout e respondeu por CLI/TUI/status/start estático. O risco de
   distribuição restante é operacional (OIDC/CI global), não o caminho local;
   o gate AWS do SHA atual permanece pendente até haver um run completo verde.
3. **Falhas de infraestrutura:** permission denied foi ensaiado em Windows com
   ACL real num diretório temporário controlado: o Product Forge recusou antes
   da escrita com `OBSIDIAN-PATH-REFUSED`/`sync_state=denied`, nenhum artefato
   parcial foi criado e o ACL foi restaurado. Disk full também foi ensaiado em
   um tmpfs real de 256 KiB: ENOSPC durante a criação do lock retornou
   `OBSIDIAN-LOCK-FAILED`/`sync_state=failed`, sem nota, receipt ou temporário
   parcial. Ainda falta ensaio em host/vault produtivo e recuperação operacional
   completa; process kill possui cobertura determinística local.
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
   resolução de wikilinks, exportação atômica, reindexação/busca SQLite/FTS,
   pico de alocação Python e RSS residente, orçamento estimado do contexto de
   recuperação e qualidade de citações fixture (precision/recall/completude),
   além do registro de tokens no gateway com provider controlado em
   100/1.000/10.000 notas. No cenário de 10.000, o pico RSS observado foi de
   aproximadamente 131 MiB na importação e 116 MiB no SQLite/FTS. A medição de
   RSS usa amostragem stdlib, portanto picos sub-5 ms podem ser subestimados.
   Token usage real de provider continua `NOT_RUN`, pois exige provider
   governado. O wall-clock de 10.000 arquivos recém-criados teve uma amostra
   Windows de 16,90 s, enquanto a importação direta em árvore quente ficou em
   ~6–8 s; ambos ficam no recibo para tendência, sem transformar uma meta
   arbitrária em gate.
8. **Distribuição técnica neutra:** `forge_obsidian` já está extraído, testado,
   construído como wheel/sdist `forge-obsidian` e incluído no wheel do Product
   Forge. O Product Forge agora também contém a pipeline standalone
   `.github/workflows/publish-forge-obsidian.yml`, com build único, checksum,
   Trusted Publishing/OIDC, instalação limpa de verificação e teste estrutural
   em `1490ff3`. O endpoint público do PyPI ainda responde 404 para
   `forge-obsidian`; os artefatos locais wheel/sdist passaram `twine check` em
   2026-11-10, mas não foi executado dispatch/publicação remota nem consumida
   uma versão fixada pelos quatro adapters. Até esse gate, os
   especialistas permanecem corretamente limitados a projeções read-only
   `ObsidianNoteRef/v1`; essas projeções agora redigem também `title` e
   `summary`, com testes dedicados nos quatro adapters.

Até que esses riscos sejam fechados, a recomendação é manter sync revisado,
fixtures-only nos E2E e confirmação humana para toda mutação.
