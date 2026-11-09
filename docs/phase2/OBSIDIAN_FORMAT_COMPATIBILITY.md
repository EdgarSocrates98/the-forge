# Phase 2 — Obsidian Format Compatibility

| Formato/recurso | Estado | Observação |
|---|---|---|
| Markdown UTF-8 | PASS local | limite de 1 MiB; conteúdo original preservado |
| Frontmatter | PASS local | projeção aditiva; YAML desconhecido permanece no corpo |
| Wikilinks/embeds | PASS local | extração estrutural; resolução completa do vault ainda limitada |
| Tags/aliases | PASS local | projeção body-free |
| Callouts/code blocks | PASS local | extração sem reescrita |
| Block references/links relativos/anexos | PASS local | referências preservadas e projetadas |
| Tabelas/Unicode/arquivo vazio | PASS local | coberto pelo parser e fixtures |
| Canvas | PASS estrutural | IDs determinísticos e validação; não é runtime completo do Canvas |
| Bases | PASS de contrato | YAML oficial determinístico, validação das seções `filters`/`formulas`/`properties`/`summaries`/`views` e serializer `.base`; sem avaliador próprio de fórmulas |
| Links quebrados | PASS diagnóstico | são reportados como referência; não são executados |

Nenhum Markdown, YAML, link, HTML ou comando do vault é tratado como instrução
de sistema ou executado pelo adapter.
