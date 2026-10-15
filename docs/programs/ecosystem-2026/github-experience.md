# GitHub Experience — checklist §10.7 (cyc10-02)

Auditoria 2026-10-15 nos 9 repos. ✓ = presente e canônico.

## Arquivos (verificável offline)

| Item | the-forge | forge-cli | forge-portal | api-forge | platform | spark-aws | spark-azure | doctor-data | doctor-api |
|---|---|---|---|---|---|---|---|---|---|
| README | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| README PT+EN | EN | EN | EN | EN+PT | EN+PT | EN | EN | EN | EN |
| LICENSE | ✓ MIT | ✓ MIT | ✓ MIT | ✓ MIT | ✓ MIT | ✓ MIT | ✓ MIT | ✓ MIT | ✓ MIT |
| CONTRIBUTING | ✓* | ✓ | ✓* | ✓* | ✓ | ✓ | ✓ | ✓ | ✓ |
| CODE_OF_CONDUCT | ✓* | ✓* | ✓* | ✓* | ✓ | ✓* | ✓* | ✓* | ✓* |
| SECURITY | ✓* | ✓* | ✓* | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| SUPPORT | ✓* | ✓* | ✓* | ✓* | ✓* | ✓* | ✓* | ✓* | ✓* |
| Issue templates | ✓* | ✓* | ✓* | ✓* | ✓ | ✓* | ✓* | ✓* | ✓* |
| PR template | ✓* | ✓* | ✓* | ✓* | ✓ | ✓* | ✓* | ✓* | ✓* |
| CHANGELOG | ✓ | ✓ | ✓ | ✓* | ✓ | ✓* | ✓* | ✓ | ✓ |

`*` = criado por cyc10-02 (2026-10-15). CONTRIBUTING padronizado exige
**DCO `Signed-off-by`** (decisão D3). CoC = Contributor Covenant 2.1 com
canal de reporte via GitHub.

## Settings do GitHub (requerem `gh`/UI do dono)

| Item | Estado | Ação do dono |
|---|---|---|
| About | não auditável offline | `gh repo edit EdgarSocrates98/<repo> --description "<uma linha do domínio>"` |
| Topics | idem | sugerido: `forge`, `agentic`, `deterministic`, `mcp` + domínio (`api`, `spark`, `platform`) |
| Release notes | sem releases públicas | D5: só com sign-off por repo |
| Roadmap público | docs/portal + PROGRAM-ecosystem-2026 | linkar do README quando público |
| Compat. de versões | `ecosystem-compatibility.json` + compatibility-matrix.md | ✓ publicado |
| Política de suporte | `SUPPORT.md` por repo | ✓ |

## Badges

Auditado: apenas badges de CI real (workflow badge do próprio repo) e
licença/versão — nenhum badge de qualidade sem medição (§10.7 respeitado).
