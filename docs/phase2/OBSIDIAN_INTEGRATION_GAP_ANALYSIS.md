# Obsidian Integration — Gap Analysis

## O que já existe

Product Forge oferece o adapter mais completo encontrado: leitura Markdown,
validação de Canvas/Bases, UTF-8/size limits, path traversal e recusa de
symlink/reparse points. O Forge Portal possui UI e clientes API reutilizáveis.
Os especialistas possuem receipts, conhecimento e adapters de portal/MCP em
graus diferentes.

## Gaps P0/P1

1. **Escrita destrutiva:** `export_vault_document` escreve diretamente no destino
   e não verifica baseline, conflito, snapshot ou hash pós-escrita.
2. **Round-trip:** não há parser/protocolo comum para frontmatter, wikilinks,
   embeds, callouts, tags, aliases, block references e Markdown desconhecido.
3. **Identidade:** falta um `NoteRef` estável independente de título/path, com
   workspace/vault/classification/provenance.
4. **Sync:** falta planner explícito com `unchanged/created/updated/skipped/
   conflict/denied/failed/rolled_back` e receipt versionado.
5. **Autorização:** o hash `ctx://` ainda não deve ser tratado como prova de
   leitura; a fronteira precisa receber principal, sessão, escopo e revogação.
6. **Freshness/applicability:** Platform e Azure ainda expõem estados implícitos
   que podem promover conhecimento inadequado.
7. **Portal:** faltam fluxos de configuração de vault, preview, export/import,
   conflitos e histórico, usando as páginas existentes.
8. **Observabilidade:** Lens precisa registrar operação e resultado sem corpo de
   nota; Portal precisa apresentar proveniência e estado de revisão.
9. **Federation:** Code Atlas/Agent Bridge/The Forge precisam compartilhar
   referências autorizadas, não conteúdo duplicado ou engines duplicados.

## Sequência de implementação

1. Remediação AWS claims, Platform gateway/applicability e Azure freshness.
2. Contratos neutros + core de vault com escrita atômica e sync planner.
3. Adapters dos quatro especialistas e receipts/proveniência.
4. Agent Bridge/Code Atlas/Lens integration points.
5. Portal flows capture/query/export/history/review.
6. Round-trip/security/recovery/performance/homologation.

## Critério de honestidade

Fixtures e testes locais serão reportados como fixtures. Nenhum relatório desta
fase converterá laboratório ou documentação em prova de execução AWS/Azure real.

