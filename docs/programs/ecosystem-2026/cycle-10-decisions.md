# Cycle 10 — decisões de produto pendentes (memo para o dono)

Data: 2026-10-15 · Autor: preparado por Devin a pedido do dono.
Regra: nada abaixo é implementado sem escolha registrada — este memo apenas
mapeia opções com trade-offs. Decisões ficam neste arquivo uma vez escolhidas.

---

## D1 — Licença dos 3 repos sem `LICENSE`

**Estado real (verificado 2026-10-15):** MIT em `forge-cli`, `api-forge`,
`platform-forge`, `spark-forge-aws`, `spark-forge-azure`, `forge-doctor-data`.
`the-forge` declara `license = { text = "MIT" }` no pyproject mas **não tem
arquivo `LICENSE`**. `forge-portal` e `forge-doctor-api` não declaram nada.

| Opção | Trade-off |
|---|---|
| **A. MIT nos 3 restantes** (recomendada) | Uniforme com os 6 existentes e com o pyproject do the-forge; mínima fricção para adoção corporativa; sem grant de patentes (irrelevante neste domínio) |
| B. Apache-2.0 uniforme | Grant de patentes explícito; exigiria re-licenciar 6 repos (churn, precisa de consentimento de contribuidores — hoje só o dono) |
| C. MIT código + CC-BY-4.0 docs | Mais correto juridicamente para docs; complexidade de explicar por-repo |

**Desbloqueia:** cyc10-02 (checklist §10.7 padroniza LICENSE por repo),
G-21, metade de cyc10-03 (contribuição exige licença clara).

## D2 — Canal de distribuição prioritário (cyc10-03 ⚠)

| Opção | Trade-off |
|---|---|
| **A. PyPI + diretórios MCP primeiro** (recomendada) | 7 dos 9 produtos são Python; `pip install theforge` é o golden path já documentável; diretório MCP é onde usuários de host realmente procuram. npm fica para forge-cli/forge-portal depois |
| B. GitHub Releases only | Zero risco de registry (sem token, sem nome squatting); mas instalação vira `pip install git+https://...` — onboarding mais frágil |
| C. Tudo de uma vez (PyPI+npm+MCP+marketplaces) | Máximo alcance; mais superfície de supply-chain antes da homologação madura |

**Nota:** publicação efetiva fica **fora de escopo** das specs (§9 — só
preparação). A escolha define *para qual canal preparamos metadados*.

## D3 — Termo de contribuição: DCO vs CLA vs nada (cyc10-03 ⚠)

| Opção | Trade-off |
|---|---|
| **A. DCO (`Signed-off-by`)** (recomendada) | Padrão Linux/CNCF; zero burocracia — um `git commit -s`; CONTRIBUTING.md explica; verificável em CI |
| B. CLA (CLAssistant/bot) | Cobertura jurídica mais forte para relicensing futuro; exige serviço externo + atrito na primeira contribuição |
| C. inbound=outbound apenas | GitHub ToS já dá isso; explícito de graça no CONTRIBUTING; mais fraco que DCO para proveniência |

## D4 — Onde vive o portal de docs unificado (cyc10-02 ⚠)

| Opção | Trade-off |
|---|---|
| **A. `the-forge/docs/portal/` + GitHub Pages** (recomendada) | Versionado com o código, zero infra nova, markdown já existente; links inter-repo por URL absoluta do GitHub |
| B. Repo próprio `forge-docs` | Separação limpa; mais um repo para manter/re-vendor |
| C. Portal Angular embutido | UX rica; duplica build/deploy; docs deixam de ser greppable offline |

## D5 — Janela de release pública

RC windows ativas: `forge-doctor-data` 1.0.0rc1, `forge-doctor-api` 0.2.0
(`rc-discipline.md` proíbe mudança de surface/contrato sem exceção registrada).

| Opção | Trade-off |
|---|---|
| **A. Preparar tudo, publicar só com sign-off explícito por repo** (recomendada) | Respeita RC discipline e §9; specs entregam material pronto |
| B. Release público imediato dos estáveis | Risco de publicar sobre claims não homologados; contraria "evidence, not assertion" |

---


## Decisões registradas (2026-10-15, dono)

| # | Escolha |
|---|---|
| D1 | **MIT** nos 3 repos — LICENSE adicionado em the-forge, forge-portal, forge-doctor-api |
| D2 | **PyPI + diretórios MCP** como canais prioritários de preparação |
| D3 | **DCO (`Signed-off-by`)** como termo de contribuição |
| D4 | **`the-forge/docs/` + GitHub Pages** para o portal de docs |
| D5 | **Preparar tudo; publicar só com sign-off explícito por repo** (default das constraints §9) |

## Ordem sugerida de implementação pós-decisão

1. **cyc10-01** — independente de todas as decisões (docs + golden paths +
   validação reproduzível). Pode começar imediatamente.
2. **cyc10-02** — após D1 + D4.
3. **cyc10-03** — após D1 + D2 + D3 + D5.
