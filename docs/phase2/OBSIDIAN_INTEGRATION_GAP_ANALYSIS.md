# Obsidian Integration — Gap Analysis

## O que já existe

Product Forge oferece a implementação de referência: leitura Markdown sem
reescrita, projeção de frontmatter/wikilinks/embeds/tags/callouts/code blocks,
validação e geração estrutural de Canvas/Bases, limites UTF-8/tamanho, path
traversal, symlink/reparse/hardlink, plano de sync, backup, escrita atômica,
receipts e histórico body-free. O The Forge é dono dos contratos versionados e
o Portal expõe captura, preview, import, export revisado, baseline/conflict e
histórico.

## Gaps P0/P1

1. **Extração neutra:** a implementação ainda reside no Product Forge; a
   superfície de protocolos está definida, mas não há pacote independente
   instalável pelos quatro especialistas.
2. **Round-trip semântico:** frontmatter, wikilinks, embeds, tags, callouts,
   blocos de código, aliases, block references, links relativos e anexos agora
   são projetados sem reescrita; a resolução contra arquivos reais do vault e
   rename/delete ainda precisam de testes dedicados.
3. **Estados de sync:** `created`, `unchanged`, `updated`, `conflict` e
   `rolled_back` estão implementados no Product Forge; `denied` e `failed`
   agora são expostos nos erros API/Portal como `details.sync_state`. `skipped`
   ainda não tem uma API pública de receipt/recovery equivalente.
4. **Portal vault configuration:** a integração usa `FORGE_OBSIDIAN_VAULT` e,
   opcionalmente, `FORGE_OBSIDIAN_ALLOWED_ROOT`; o Portal já expõe um descritor
   seguro com capacidades e recusa vault fora da raiz autorizada. Ainda falta
   uma tela administrativa para provisionamento/revogação multiusuário; essa
   configuração permanece deliberadamente no serviço, não em input web.
5. **Observabilidade/federation:** Code Atlas já projeta relações body-free,
   Forge Lens já transforma receipts em traces sanitizados e o Agent Bridge já
   exige allowlist explícita. O runner local `scripts/phase2_federated_obsidian_e2e.py`
   comprova a cadeia com fixtures; ainda falta o Portal disparar essa execução
   em runtime.
6. **Homologação:** benchmark local 100/1.000/10.000 passou com importação em
   lote; ainda faltam concorrência/rename/delete completos, teste de disco
   cheio/permissão e ensaio instalável pelo Portal.

## Sequência de implementação

1. Remediação AWS claims, Platform gateway/applicability e Azure freshness.
2. Contratos neutros + core de vault com escrita atômica e sync planner.
3. Adapters dos quatro especialistas e receipts/proveniência.
4. Agent Bridge/Code Atlas/Lens integration points e E2E federado com fixtures.
5. Portal flows capture/query/export/history/review.
6. Round-trip/security/recovery/performance/homologation.

## Critério de honestidade

Fixtures e testes locais serão reportados como fixtures. Nenhum relatório desta
fase converterá laboratório ou documentação em prova de execução AWS/Azure real.

