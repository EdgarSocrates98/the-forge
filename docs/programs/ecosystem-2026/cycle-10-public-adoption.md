# Cycle 10 — Public Adoption (cyc10-03)

Data de fechamento: 2026-10-15.

## Modelo de contribuição (§10.9)

`docs/contributing/external-forges.md`: contribuições aceitas em 7
categorias; **nenhuma Forja externa é confiável por padrão** — pipeline de
7 etapas (`manifesto → capabilities → permissões → provider check →
mcp-verify → proveniência+DCO → receipt de lab próprio`) com estados
`untrusted/validated/trusted` registrados, nunca implícitos.

## Distribuição (decisão D2)

`distribution-plan.md`: PyPI (7 pacotes Python, build verificado em
`packaging-matrix.md`) + diretórios MCP (oficial, Smithery, registro OSS).
Publicação efetiva **fora de escopo** — só com sign-off por repo (D5).

## Templates (§10.10)

`templates/` — 7 templates: api-apiforge, pyspark-aws, pyspark-azure,
terraform-platform, multi-repo-theforge, mcp-host-config, custom-specialist.
Cada um com README (instalação) + `check.sh` executável.

## Demos (§10.11)

`demos/` — 8 scripts sintéticos (install Linux, 2 forjas, host config,
diagnóstico, orquestração, portal, benchmark, evidências). Sem credenciais,
sem rede — `FORGE_HOME_OVERRIDE` isolado. `demos/04-diagnostic.sh`
executado e verde (evidência neste run note).

## Feedback opt-in (§10.12)

`scripts/feedback_bundle.py` — bundle local `feedback-bundle.json` que o
usuário revisa e anexa numa issue. Zero telemetria, zero envio. Issue
templates (bug/feature) nos 9 repos já padronizam o reporte.

## Claims públicos

Nenhum número publicado sem lastro: benchmarks citam
`docs/programs/ecosystem-2026/benchmarks/` (7/7 labs, 203 cenários,
coletados 2026-10-15); compatibilidade cita `ecosystem-compatibility.json`.
