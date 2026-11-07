# Repository capability matrix

| capability | owner | consumers | estado |
|---|---|---|---|
| bootstrap knowledge | The Forge | Portal, adapters | existente e preservado |
| code retrieval/context | Code Atlas | Agent Bridge, Portal | existente; projeção KnowledgeContextPack adicionada |
| trace/evidence | Forge Lens | Agent Bridge, Portal | existente; metadata de pack adicionada |
| session authorization | Agent Bridge | Product Forge, providers | existente; autorização de pack adicionada |
| product documents/FTS | Product Forge | Portal, agents | existente; Markdown-aware chunks e receipt de import adicionados |
| visual operation | Forge Portal | usuário técnico | existente; Nova investigação e accessibility gates validados |
| knowledge interop smoke | The Forge orchestration | Product Forge → Code Atlas → Agent Bridge → Forge Lens | PASS; envelope `theforge/KnowledgeContextPack/v1`, reautorização e telemetry redacted |
| embedded Bridge parity | Product Forge + Agent Bridge | pacote Product Forge | gate de fontes Python e manifestos JSON; PR de endurecimento em revisão |

Nenhum novo motor de busca, grafo, broker de sessão ou trace foi criado.
