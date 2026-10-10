# Learning Hub — avaliação de tecnologia (Wave 4)

Decisão registrada para o §7 do programa. Critérios do prompt:

| Critério | MkDocs Material | Docusaurus | VitePress | Astro Starlight |
|---|---|---|---|---|
| Local-first/offline | ✅ search client-side (lunr), zero runtime | ⚠️ SPA pesada, search via plugin | ✅ search local (minisearch) | ✅ Pagefind local |
| Search | ✅ built-in | ⚠️ algolia/local-search plugin | ✅ built-in | ✅ built-in |
| Navegação rápida | ✅ | ✅ | ✅ | ✅ |
| Markdown nativo | ✅ | ✅ | ✅ | ✅ |
| Versionamento | ✅ `mike` | ✅ built-in | ⚠️ manual | ⚠️ manual |
| i18n potencial | ✅ plugin | ✅ built-in | ✅ built-in | ✅ built-in |
| Acessibilidade | ✅ auditada upstream | ✅ | ✅ | ✅ |
| Baixo custo | ✅ pip dev-only | ❌ node toolchain pesada | ⚠️ node toolchain | ⚠️ node toolchain |
| Git integration | ✅ | ✅ | ✅ | ✅ |
| Deploy opcional | ✅ estático | ✅ | ✅ | ✅ |
| Builds reproduzíveis | ✅ lock pip | ⚠️ npm | ⚠️ npm | ⚠️ npm |
| Fit com ecossistema | ✅ Python/stdlib ethos | ❌ node | ⚠️ node | ⚠️ node |

## Decisão

**Hub markdown-first + MkDocs Material opcional.**

- O hub vive em `docs/hub/` como Markdown navegável — funciona hoje, no repo,
  sem build nenhum (local-first real, zero custo).
- `docs/hub/mkdocs.hub.yml` é a config **opcional** de site
  (`pip install mkdocs-material` dev-only, `mkdocs build -f docs/hub/mkdocs.hub.yml`)
  — deploy é decisão do owner, não do programa.
- "Which Forge Should I Use?" é **gerado** de `forge-knowledge/*.json`
  (ForgeKnowledge/v1 — appropriate_for/inappropriate_for/intents reais)
  por `scripts/docs/gen_hub.py` — determinístico, sem LLM, nunca desatualizado
  porque deriva do contrato.

## O que o hub NÃO é

- Não duplica manuais — cada página é camada de descoberta que linka a fonte
  canônica por forja (`../learn/`, `../installation/`, `../reference/`).
- Não substitui a doc operacional de cada forja — o índice canônico de cada
  repo é `docs/INDEX.md` gerado.

## Limitações declaradas

- Build do site não foi executado nesta wave (dev-only, requer
  `mkdocs-material`); a navegação Markdown é a entrega verificada.
- i18n: estrutura pronta (páginas por arquivo), tradução não produzida.
- Versionamento via `mike` disponível na config; não configurado (sem deploy).
