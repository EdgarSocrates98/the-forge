# Release 1 — Plano de versões, nomes e RCs (Wave 1)

## Versões propostas (sujeitas a aprovação)

Princípio: "Release 1" é o lançamento público coordenado, **não** um bump
em bloco para 1.0. Versões honestas por estado real de interface.

| Repo | Versão atual | Versão Release 1 | Tag proposta | Justificativa |
|---|---|---|---|---|
| the-forge | 0.5.0 | **0.5.0** | `v0.5.0` | superfície `stable candidate`, pré-1.0 honesto |
| forge-cli | 0.1.0 | **0.1.0** | `v0.1.0` | primeira distribuição pública |
| forge-portal | 0.1.0 | **0.1.0** | `v0.1.0` | distribuído vendored no wheel do the-forge |
| api-forge | 0.1.0 | **0.1.0** | `v0.1.0` | contracts v1, superfície experimental |
| platform-forge | 0.1.0 | **0.1.0** | `v0.1.0` | freeze manifest ativo, experimental |
| spark-forge-aws | 0.5.0 | **0.5.0** | `v0.5.0` | maduro, ainda pré-1.0 |
| spark-forge-azure | 0.1.0 | **0.1.0** | `v0.1.0` | primeira distribuição pública |
| forge-doctor-data | 1.0.0rc1 | **1.0.0** | `v1.0.0` | graduação da janela RC — **decisão do mantenedor** |
| forge-doctor-api | 0.2.0 | **0.2.0** | `v0.2.0` | disciplina RC, pré-1.0 |

## Nomes de distribuição (P0 — conflitos reais verificados 2026-10-16)

| Componente | Nome desejado | Status | Nome aplicado |
|---|---|---|---|
| the-forge | `theforge` | **OCUPADO no PyPI** (produto alheio "TheForge SDK") | **`the-forge`** |
| forge-cli | `forge-cli` | **OCUPADO no npm** (pacote alheio 0.2.1) | **`theforge-cli`** |
| api-forge | `apiforge` | livre (404) | `apiforge` |
| platform-forge | `platformforge` | livre | `platformforge` |
| spark-forge-aws | `sparkforge-aws` | livre | `sparkforge-aws` |
| spark-forge-azure | `sparkforge-azure` | livre | `sparkforge-azure` |
| forge-doctor-data | `forge-doctor-data` | livre | `forge-doctor-data` |
| forge-doctor-api | `forge-doctor-api` | livre | `forge-doctor-api` |
| 6 adapters the-forge | `theforge-*-adapter` | todos livres (404) | inalterados |

Alternativas documentadas: `theforge-core` (alinhado à família de adapters
`theforge-*`), `@theforge/cli` (scoped npm). Escolha final é decisão do
mantenedor no checklist de aprovação.

O que mudou nesta branch (the-forge): `pyproject.name → the-forge`,
`install/service.py distribution → the-forge`, globs de artefato
`the_forge-*` em testes e `release-gates.yml`, 2 refs de docs
`pip install the-forge`. Import `theforge`, CLI `theforge`/`forge` e
`ForgeSpec.package` inalterados. Verificado: `the_forge-0.5.0`
sdist+wheel buildam e `pytest tests/test_packaging.py` 11/11.

forge-cli: `package.json name → theforge-cli`, `planSelfUpdate` pkgName,
teste correspondente, README. Bin `forge-cli` inalterado.
Verificado: 622/622 testes.

## Release candidates

Sem tags públicas sem aprovação. RCs lógicos = commits de release
identificados acima + evidências deste diretório. `forge-doctor-data`
precisa de bump `1.0.0rc1 → 1.0.0` na sua branch de release se aprovado.

## Freeze

Freeze lógico ativo a partir de 2026-10-16: só P0/P1, packaging,
segurança, compat, docs, CI, distribuição.

**GATE 1: PASS** — versões identificadas, conflitos de nome resolvidos,
compatibilidade registrada em `compatibility.md` / `ecosystem-release.yaml`.
