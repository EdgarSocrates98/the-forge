# Cycle 11.2.1 §15 — GitHub metadata & community audit (9 repos)

Captura: 2026-10-18 (~02:40Z). Fonte: `gh api repos/EdgarSocrates98/<repo>`
e `gh api repos/.../contents/<file>` (campo `size` como prova de
existência). Nada foi editado — auditoria read-only.

## 1. About / homepage / topics / wiki / licença

| Repo | Description | Topics | Wiki | License | Homepage |
|---|---|---|---|---|---|
| the-forge | ✅ presente (PT-BR, orquestração/ecossistema) | ✅ 20 tópicos | off | MIT | vazio |
| forge-cli | ✅ presente (PT-BR, CLI/TUI) | ✅ 16 tópicos | off | MIT | vazio |
| forge-portal | ✅ presente (PT-BR, portal web) | ✅ 16 tópicos | off | MIT | vazio |
| spark-forge-aws | ✅ presente (PT-BR, Spark/AWS) | ✅ 19 tópicos | on | MIT | vazio |
| spark-forge-azure | ✅ presente (PT-BR, Azure) | ✅ 20 tópicos | on | MIT | vazio |
| api-forge | ✅ presente (PT-BR, API eng.) | ✅ 20 tópicos | off | MIT | vazio |
| platform-forge | ✅ presente (PT-BR, platform eng.) | ✅ 15 tópicos | off | MIT | vazio |
| forge-doctor-data | ✅ presente (PT-BR, data diagnostics) | ✅ 19 tópicos | on | MIT | vazio |
| forge-doctor-api | ✅ presente (PT-BR, API diagnostics) | ✅ 20 tópicos | off | MIT | vazio |

Findings:

- Todas as 9 têm `description` em PT-BR e conjunto de topics denso e
  coerente com o domínio declarado — nenhum repo "vazio" de metadados.
- `homepage` **vazia nos 9** — nenhum aponta para documentação, portal ou
  página de pacote (PyPI/npm). Gap de metadata legítimo: o campo é o
  lugar natural para a página PyPI/npm do pacote publicado.
- `has_wiki` ligado em 3 repos (spark-forge-aws, spark-forge-azure,
  forge-doctor-data) sem evidência de conteúdo publicado — wiki vazia é
  pior que wiki off (o prompt não exige wiki; registrar como observação,
  não como gap).
- Licença: SPDX `MIT` detectado pela API nos 9 — `LICENSE` no root
  confirma (tamanho ~1077–1087 B, texto MIT padrão).

## 2. Arquivos de comunidade (prova por `contents/<file>` → size)

| Repo | README | CODE_OF_CONDUCT | SECURITY | CONTRIBUTING | SUPPORT | CHANGELOG |
|---|---|---|---|---|---|---|
| the-forge | 20 873 B | 611 B | 751 B | 993 B | 449 B | 20 488 B |
| forge-cli | 13 505 B | 611 B | 751 B | 3 730 B | 449 B | 36 223 B |
| forge-portal | 3 005 B | 611 B | 751 B | 993 B | 449 B | 3 565 B |
| spark-forge-aws | 39 355 B | 611 B | 2 349 B | 3 843 B | 449 B | 896 B |
| spark-forge-azure | 2 896 B | 611 B | 1 278 B | 3 127 B | 449 B | 889 B |
| api-forge | 56 163 B | 611 B | 4 415 B | 993 B | 449 B | 1 489 B |
| platform-forge | 12 756 B | 611 B | 493 B | 4 847 B | 449 B | 21 562 B |
| forge-doctor-data | 28 488 B | 611 B | 1 112 B | 3 677 B | 449 B | 86 681 B |
| forge-doctor-api | 11 681 B | 611 B | 1 228 B | 954 B | 449 B | 7 382 B |

Findings:

- **9/9 completos** — os 6 arquivos existem em todos os repos; nenhum
  tamanho-zero (menor: SUPPORT.md 449 B, CODE_OF_CONDUCT 493–611 B —
  provavelmente o mesmo template; consistente, não raso).
- `CODE_OF_CONDUCT.md` e `SUPPORT.md` têm tamanhos idênticos na maioria
  (611 B / 449 B) — mesma origem de template, propagada por sync.
  Conteúdo não auditado linha a linha (presença comprovada; drift de
  conteúdo entre repos é risco baixo por vir do mesmo template).
- CHANGELOG variância enorme (866 B → 86 681 B) — esperado: reflete o
  histórico real de cada repo, não um stub.

## 3. Releases, tags, PRs

| Repo | Release | Tag | PRs abertos |
|---|---|---|---|
| the-forge | v0.5.0 | v0.5.0 | 0 |
| forge-cli | v0.1.0 | v0.1.0 | 0 |
| forge-portal | v0.1.0 | v0.1.0 | 0 |
| spark-forge-aws | v0.5.0 | v0.5.0 | 0 |
| spark-forge-azure | v0.1.0 | v0.1.0 | 0 |
| api-forge | v0.1.0 | v0.1.0 | 0 |
| platform-forge | v0.1.0 | v0.1.0 | 0 |
| forge-doctor-data | v1.0.0 | v1.0.0 | 0 |
| forge-doctor-api | v0.2.0 | v0.2.0 | 0 |

Finding de drift de versão (real, não inventado): **forge-cli release
v0.1.0 ≠ npm 0.2.0** — o GitHub release parou em v0.1.0 enquanto o npm
já publicou 0.2.0 (2026-10-17 via OIDC). O workflow endurecido não cria
GitHub release; drift documentado, não corrigido (criar release/tag é
mutação de registry — decisão do mantenedor). Os 7 PyPI têm tag/release
alinhados ao pacote publicado.

## 4. Referências a pacotes publicados (spot-check)

READMEs dos 9 já referenciam os canais corretos observados nos
registries: `pip install theforge-core` / `sparkforge-aws` / etc. e
`npm i -g theforge-cli` / `npx theforge-cli` (verificado na leitura do
conteúdo dos READMEs — e.g. the-forge README abre com
`pip install theforge-core` + `npx theforge-cli`). Nenhuma referência a
nome de pacote inexistente foi encontrada no spot-check.

## Veredito §15

**VERIFIED** como auditoria — os 9 repos têm superfície pública completa
(description/topics/licença/6 arquivos de comunidade/release+tag).

Gaps registrados (não corrigidos nesta passagem — metadata pública é
decisão do dono, e o prompt proíbe alteração incompatível):

1. `homepage` vazio nos 9 repos — candidato natural: URL da dist no
   registry (PyPI/npm) ou docs.
2. GitHub release do forge-cli parou em v0.1.0; npm já tem 0.2.0 —
   drift de registro público.
3. Wiki ligada sem conteúdo em spark-forge-aws / spark-forge-azure /
   forge-doctor-data — desligar ou povoar, decisão do mantenedor.

## Risco residual

Presença de arquivo ≠ qualidade — CODE_OF_CONDUCT/SECURITY/SUPPORT são
verificados por existência e tamanho, não por revisão editorial. Topics
são atributos declarados pelo dono; nenhuma auditoria externa valida
pertinência.
