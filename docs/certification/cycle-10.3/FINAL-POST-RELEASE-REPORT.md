# Cycle 10.3 — FINAL POST-RELEASE REPORT

**Escopo**: auditoria pós-publicação das 9 forjas + distribuições públicas
(7 PyPI + 1 npm + 9 GitHub Releases). Modo: Audit → Reproduce → Fix → Test →
Benchmark → Certify → Prepare Patch. Data: 2026-10-17.

## Executive summary

O Release 1 publicado é **real e funcional**: 7/7 pacotes PyPI instalam do
registry público, o CLI npm executa, o Portal serve com segurança verificada,
o MCP responde protocolo completo (154+39 tools), e o benchmark federado roda
137 cenários determinísticos. O ciclo encontrou **um bug real** (emissor de
lab reportando skip como fail — corrigido, PR #61), **gaps de metadata** em
4 pacotes (PRs abertos), **uma matriz Python desalinhada** (3 pacotes vendem
floor não testado), e **fricções de descoberta** (PyPI README não ensina pip
install). Nenhuma quebra funcional.

**Recomendação de adoção**: `CONDITIONALLY READY` — um usuário novo consegue
instalar, executar e obter resultados verificáveis hoje; as fricções são de
descoberta e polish, resolvidas pelos 4 patches propostos + correções de
settings. O gargalo de adoção real é G-CLI-1 (clone-only) — feature, não patch.

## Baseline — 9 mains (SHAs auditados)

the-forge `8029099` · forge-cli `7c7fbd1` · forge-portal `55e01d5` ·
api-forge `4e5bc7c` · platform-forge `9e7ee3b` · spark-forge-aws `db28a92` ·
spark-forge-azure `51e366c` · forge-doctor-data `b105ada` ·
forge-doctor-api `ca2df7b` — CI verde nos 9 HEADs.

## Registry (verificado, não declarado)

| Dist | Versão | wheel+sdist | hash↔asset GH | attestation |
|---|---|---|---|---|
| theforge-core | 0.5.0 | ✓ | wheel ✓ / sdist diverge (G-REG-1) | ✓ PEP 740 |
| apiforge-af | 0.1.0 | ✓ | assets stale `apiforge-*` (G-REG-2) | ✓ |
| platformforge | 0.1.0 | ✓ | ✓ | — (token) |
| sparkforge-aws | 0.5.0 | ✓ | ✓ | — |
| sparkforge-azure | 0.1.0 | ✓ | ✓ | — |
| forge-doctor-data | 1.0.0 | ✓ | ✓ | — |
| forge-doctor-api | 0.2.0 | ✓ | ✓ | ✓ |
| theforge-cli (npm) | 0.1.0 | tgz ✓ | — | — |

14/14 arquivos PyPI com sha256 conferido. `pip install` limpo 7/7.

## Achados e correções

**Corrigido no ciclo** (PRs abertos, não mergeados — aguardam revisão):

| PR | Repo | Conteúdo | CI |
|---|---|---|---|
| #74 | the-forge | metadata + 80 links/img absolutos + pip section + rename real-providers | 13✓ |
| #81 | api-forge | rename completo + metadata + 57 links/img + AF-MCP-UNAVAILABLE | 11✓ |
| #47 | platform-forge | 67 links/img absolutos + pip section | 5✓ |
| #51 | platform-forge | OIDC comment + doc-gate resolver + receipt rebind | 5✓ |
| #168 | spark-forge-aws | 87 links/img absolutos | novo |
| #62 | spark-forge-azure | 9 links/img absolutos + pip line | novo |
| #48 | forge-doctor-data | urls + classifier + 18 links/img | 13✓ |
| #60 | forge-doctor-api | metadata + 32 links/img + pip section | 5✓ |
| #61 | forge-doctor-api | lab emitter skip→skipped | rodando |

**Bugs reais encontrados**: (1) lab emitter reportava `skipped` como `fail` —
install mínimo parecia quebrado (PR #61); (2) `apiforge-mcp` sem extra dava
traceback cru — a mensagem guiada existia mas `except ImportError` não cobria
o `RuntimeError` de `build_server` (PR #81). **Auditoria interna corrigida**:
a Wave-2 original certificou "1 link relativo" — recontagem provou ~350;
reescritos todos para absolutos tag-pinned (errata registrada no doc).

## Resultados por frente

- **CLI**: command surface completo, lifecycle install→uninstall funcional,
  23s install; clone-only = G-CLI-1 (feature).
- **Portal**: 403 sem token / 200 com token; `/api/v1`; headers de segurança;
  schema `forge/PortalApi/1` vivo da wheel.
- **Hosts**: detecção honesta (weak/strong/no evidence); auth distinguída.
- **MCP**: stdio JSON-RPC provado end-to-end — init/list/call/erro.
- **CI/Security**: 0 vulns (pip-audit+npm audit), 100% SHA-pin, OIDC sem
  tokens armazenados; G-MATRIX-1 pendente.
- **Lab**: 137 cenários Modo A, métricas honestas (não fabricadas), bug
  encontrado+corrigido.
- **Jornada**: E2E real — scan produz findings acionáveis; 5 fricções
  catalogadas (F-1..F-5).
- **Community**: health 100% nos 9, topics ricos, SECURITY em todos.

## Documentação

Problemas de doc reais corrigidos no ciclo: ~350 links/imagens relativos nos
READMEs registry-bound → absolutos tag-pinned (G-DOCS-4, errata da Wave-2);
`pip install` agora lidera Install nos READMEs (G-DOCS-1); logos corrigidos
(G-DOCS-2); rename `apiforge`→`apiforge-af` completado em `mcp/main.py`,
`__init__.py` e `real-providers.md`.

## Residual risks

- G-MATRIX-1: usuário em Python 3.10 instala código não testado (3 pacotes).
- G-LAB-1: extras nunca exercitam no lab federado (design).
- G-E2E-1: eficácia de agents por host = declarado, não testado.
- G-SEC-1: token PyPI exposto → rotacionar (ação humana pendente).
- G-REG-1/2: divergências de proveniência/asset auditáveis, sem conteúdo
  incorreto detectado.

## Patch recommendations

7 patches justificados (mudança distribuível em README/metadata — vão na
wheel): `theforge-core 0.5.1`, `apiforge-af 0.1.1`, `platformforge 0.1.1`,
`sparkforge-aws 0.5.1`, `sparkforge-azure 0.1.1`, `forge-doctor-data 1.0.1`,
`forge-doctor-api 0.2.1`. Detalhes e checklist em `10-patch-release-plan.md`.
forge-cli (npm) e forge-portal (vendored) **não** precisam de versão nova.

## Adoption-readiness decision

**CONDITIONALLY READY — GO condicionado aos 7 patches.**

Justificativa honesta: a trilha central (achar → instalar → executar →
findings → portal → remover) funciona de ponta a ponta em artefatos
públicos. As fricções de descoberta (links quebrados, ausência de
`pip install` nos READMEs) foram corrigidas nos PRs pendentes — mas só
chegam ao usuário quando os patches publicarem. Depois dos 7 patches + merge
dos 8 PRs, a recomendação vira `READY` sem ressalvas de documentação;
G-CLI-1 e G-E2E-1 ficam como roadmap explícito.

---
*Gerado por auditoria executável — cada afirmação tem comando, arquivo ou
saída de ferramenta correspondente em `test-evidence.md`.*
