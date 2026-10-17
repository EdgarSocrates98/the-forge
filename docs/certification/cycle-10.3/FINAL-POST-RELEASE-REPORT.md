# Cycle 10.3 — FINAL POST-RELEASE REPORT

**Escopo**: auditoria pós-publicação das 9 forjas + distribuições públicas
(7 PyPI + 1 npm + 9 GitHub Releases). Modo: Audit → Reproduce → Fix → Test →
Benchmark → Certify → Prepare Patch. Data: 2026-10-19.

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
| #74 | the-forge | metadata + link PyPI | 13✓ (1 pend) |
| #81 | api-forge | rename apiforge-af + metadata | 11✓ |
| #60 | forge-doctor-api | urls/classifiers | 5✓ |
| #48 | forge-doctor-data | urls + classifier Alpha | 13✓ |
| #61 | forge-doctor-api | lab emitter skip→skipped | rodando |

**Bug real**: lab emitter reportava `skipped` como `fail` — install mínimo
parecia quebrado. Causa raiz dupla documentada em 07-forge-lab.md.

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

Problemas de doc reais: READMEs do PyPI não ensinam `pip install` (G-DOCS-1),
logo relativo quebrado (G-DOCS-2), npm não referenciado (G-DOCS-3),
refs antigas `apiforge` corrigidas no #81.

## Residual risks

- G-MATRIX-1: usuário em Python 3.10 instala código não testado (3 pacotes).
- G-LAB-1: extras nunca exercitam no lab federado (design).
- G-E2E-1: eficácia de agents por host = declarado, não testado.
- G-SEC-1: token PyPI exposto → rotacionar (ação humana pendente).
- G-REG-1/2: divergências de proveniência/asset auditáveis, sem conteúdo
  incorreto detectado.

## Patch recommendations

4 patches justificados (mudança distribuível): `theforge-core 0.5.1`,
`apiforge-af 0.1.1`, `forge-doctor-data 1.0.1`, `forge-doctor-api 0.2.1`.
Detalhes e checklist em `10-patch-release-plan.md`. Os outros 5 projetos
**não** precisam de versão nova.

## Adoption-readiness decision

**CONDITIONALLY READY — GO condicionado aos 4 patches.**

Justificativa honesta: a trilha central (achar → instalar → executar →
findings → portal → remover) funciona de ponta a ponta em artefatos
públicos. O que falta é polish de descoberta (um usuário PyPI não aprende o
caminho pip) e o alinhamento do contrato Python. Nada disso quebra o
produto — mas para "sem depender do autor" ser literalmente verdade, o
README precisa ensinar o caminho que existe. Depois dos 4 patches + merge
dos 5 PRs, a recomendação vira `READY` sem ressalvas de documentação;
G-CLI-1 e G-E2E-1 ficam como roadmap explícito.

---
*Gerado por auditoria executável — cada afirmação tem comando, arquivo ou
saída de ferramenta correspondente em `test-evidence.md`.*
