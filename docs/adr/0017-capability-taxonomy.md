# ADR 0017 — Taxonomia de capabilities

- Status: aceito (2026-10-04)

## Contexto
Com os adapters reais, o catálogo passa a ter capabilities de dois Forges especialistas: 15 do Spark Forge e 2 do API Forge, de uma superfície nativa com dezenas de tools e registros. Sem regras, o catálogo cresce de dois jeitos ruins. Um é uma capability por tool nativa, que repete sinais, deixa o routing ambíguo e explode o catálogo. O outro são capabilities genéricas (`spark.tools`, `misc.all`), que o routing não consegue distinguir. Renomear ou mudar uma capability também quebraria pedidos explícitos sem aviso. O core não pode resolver isso com conhecimento de domínio (CLAUDE.md): as regras que ele aplica precisam ser de formato.

## Decisão
- ID no formato `namespace.subject[.qualifier]` (2 a 3 segmentos). O namespace é a tecnologia, plataforma ou domínio do objeto analisado, nunca o nome do provider. O subject diz o que a capability faz. O qualifier separa variantes, nunca versões.
- Regras mecânicas aplicadas pelo core em `contracts/taxonomy.py` (`validate_taxonomy`), junto dos limites de manifest: segmentos e tamanhos (segmento ≤ 32, ID ≤ 64), namespaces reservados `forge` e `theforge`, lista fechada de segmentos genéricos proibidos, formato de ação `^[a-z][a-z0-9-]{0,31}$`, aliases com as regras de ID e `replaced_by` com o formato de ID. Uma violação gera `FORGE-MANIFEST-TAXONOMY`: a capability é excluída com aviso, e o provider fica `invalid` só se nenhuma capability restar. A lista de segmentos genéricos tem só palavras genéricas, nunca termos de domínio.
- Granularidade: uma capability por tipo de trabalho distinguível pelos sinais. Ferramentas nativas sobre o mesmo objeto viram ações. Uma ação só é declarada se é read-only, offline e preenchível com arquivos do workspace. Tudo o que não é exposto vai para `limitations` com o motivo.
- Sobreposição entre providers é permitida para a mesma semântica e resolvida pelo routing existente (nota `capability-overlap`). Não há peso novo nem regra de domínio.
- Evolução: uma capability publicada não muda de significado. Mudança incompatível vira capability nova, e a antiga recebe `deprecated` e, quando houver, `replaced_by`. Renomeação usa `aliases`, resolvidos para o ID canônico de forma determinística. Um alias com canônicos diferentes entre providers vira `ambiguous`. Um alias que colide no mesmo manifest deixa o provider `invalid`.
- Regras completas, tabela mecânica e catálogo inicial (com a origem nativa de cada capability e o motivo de cada exclusão) estão em [capabilities.md](../capabilities.md). `tests/test_capability_catalog_doc.py` mantém esse catálogo igual ao describe em replay dos dois adapters.

## Alternativas
- **Uma capability por tool nativa:** é fiel à superfície, mas tem sinais repetidos, routing ambíguo e um catálogo que muda a cada tool nova do especialista.
- **Uma capability por Forge:** o routing não consegue escolher entre trabalhos diferentes e precisaria de um glob catch-all, que é rejeitado.
- **Versão no ID (`.v2`):** mistura versão com variante e gasta o qualifier. Capability nova com depreciação e aliases expressa a mesma coisa sem regra extra.
- **Validar namespace contra uma lista de domínios no core:** põe conhecimento de domínio no control plane.

## Consequências
- Providers externos recebem um aviso acionável por capability fora do formato, sem perder as demais.
- A escolha de namespace, a granularidade e a sobreposição continuam dependendo de revisão: o código só garante o formato.
- Mudar o catálogo de um adapter exige atualizar `docs/capabilities.md` no mesmo commit (o teste falha caso contrário).
