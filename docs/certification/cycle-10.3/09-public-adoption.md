# Cycle 10.3 — Wave 9: Community & Public Adoption Surfaces

Auditoria via GitHub API (`/community/profile`, `/repos/*`), 2026-10-17.

## 9.1 Community health — 9/9 em 100%

Todos os nove repos têm o conjunto completo que o GitHub pontua:

`readme` · `license` (MIT) · `code_of_conduct` · `contributing` ·
`issue_template` (2 por repo) · `pull_request_template`

`SECURITY.md` presente nos 9 (verificado individualmente — não entra no
score do GitHub mas está lá).

## 9.2 Discoverability

| Superfície | Estado |
|---|---|
| Description | 9/9 preenchida (PT) |
| Topics | 9/9 — conjuntos ricos e específicos (ex.: the-forge 20, spark-forge-aws 20) |
| License detectada | 9/9 MIT |
| Issues habilitadas | 9/9 |
| Releases públicas | 9/9 com tag + artifacts + SHA256SUMS |

## 9.3 Gaps observados (não-bloqueantes)

- **`homepage` vazio nos 9** — campo GitHub sem URL. Candidato: apontar para
  a página PyPI/npm de cada pacote ou um docs hub. Melhoria barata de
  descoberta (edição de settings, não precisa de release).
- **Discussions desabilitadas nos 9** — decisão legítima para um ecossistema
  novo (canal sem moderação vira rádio-silêncio visível), mas é a resposta
  honesta: não há canal de comunidade. Registrar como escolha, não defeito.
- **`has_wiki` ligado em 3 repos** (spark-forge-aws, spark-forge-azure,
  forge-doctor-data) — wiki vazia é pior que desabilitada; verificar se há
  conteúdo ou desligar.
- **homepage do package metadata** — os `[project.urls]` corrigidos em Wave 2
  (PRs abertos) resolvem isso no PyPI; o campo `homepage` do GitHub é
  separado e segue vazio.

## 9.4 Assets de comunicação

O prompt §11.4 pedia texto de lançamento. Estado honesto: release notes dos
GitHub Releases existem (gerados na publicação); assets editoriais
(post/LinkedIn/FAQ) **não foram produzidos** neste ciclo — não invento o que
não existe. Se a decisão for produzir, é trabalho de conteúdo separado do
hardening técnico.

## 9.5 Veredito Wave 9

`VERIFIED` — a superfície comunitária está materialmente completa (score
100%, topics ricos, SECURITY em todos). Os gaps são de alcance (homepage
vazio, sem Discussions), não de conformidade.
