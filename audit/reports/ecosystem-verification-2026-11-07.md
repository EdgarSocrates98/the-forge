# Verificação do ecossistema Forge — 2026-11-07

## Escopo

Rodada de verificação dos 14 projetos oficiais após a consolidação das
superfícies CLI/TUI/TTY/Wizard, do Portal de conhecimento e dos contratos de
integração. Os comandos foram executados nas branches `main` locais, alinhadas
com `origin/main`.

## Evidência objetiva

| Área | Resultado | Evidência |
| --- | --- | --- |
| CLI/install matrix | PASS — 14/14 | `python scripts/cli_install_matrix.py --check` |
| Runtime smoke | PASS — 28/28 | `python scripts/cli_runtime_smoke.py --timeout 30` |
| The Forge gates | PASS — 11/11 | `python scripts/check_gates.py` |
| Forge CLI | PASS — 1.217 testes, 3 skips | `npm test`; typecheck, lint e build verdes |
| Forge Portal | PASS — 588 testes | `npm test -- --watch=false` |
| Portal visual/axe | PASS — axe 0, overflow 0, foco 0 | `e2e/pf_knowledge_visual_gate.py`, auditoria visual e reflow |
| Product Forge | PASS — 217 testes, 1 skip | suíte Python completa |
| Spark Forge Azure | PASS — 3.180 testes, 9 skips | `uv run python -m pytest -q` |
| Spark Forge AWS | PARTIALLY_IMPLEMENTED — 15.117 pass, 14 skips, 3 fail | suíte completa; falhas de drift descritas abaixo |

As contagens das demais suítes Python foram registradas na rodada de baseline
corretiva; quando uma execução inicial usou um `pytest` global incompatível, os
testes afetados foram repetidos dentro da venv do projeto antes de qualquer
conclusão.

## Falhas e handoff

### Spark Forge AWS

As três falhas são determinísticas e locais ao repositório:

1. `.claude-plugin/plugin.json` declara `0.7.2`, enquanto `pyproject.toml` e
   `sparkforge_aws.__version__` declaram `0.7.4`.
2. `docs/guia/referencia/cli/repair.md` diverge do gerador.
3. `docs/guia/referencia/cli/uninstall.md` diverge do gerador.
4. `docs/guia/referencia/cli/update.md` diverge do gerador.

O código do Spark AWS não foi alterado nesta fase. A correção deve atualizar a
fonte canônica da versão, regenerar a referência e repetir a suíte completa.

### Execução live AWS

Não há declaração de execução live. O perfil `sparkforge` está expirado e o
login remoto aguarda autenticação interativa do operador. Depois de a identidade
ser confirmada por `aws sts get-caller-identity --profile sparkforge`, executar
somente coletores read-only com região, alvo e orçamento registrados.

### Platform Forge

O teste de fechamento de economia continua apontando um receipt versionado com
`validated_sha` antigo. O `uv.lock` local foi gerado pela preparação da venv e
não é mudança funcional. A correção do receipt permanece handoff de fase,
porque este checkpoint não altera o repositório Platform.

## Estado de integração

- Todas as 14 branches `main` locais estão `0/0` em relação a `origin/main`.
- `the-forge` inclui o alinhamento do contrato Portal em `e8576aa`.
- `forge-doctor-data` inclui a compatibilidade MCP em `b124c77`.
- Artefatos visuais gerados em `forge-portal` permanecem fora de commits
  funcionais.

## Próxima etapa segura

1. Confirmar a identidade AWS e executar o golden path Spark read-only.
2. Corrigir o drift AWS e o receipt Platform na auditoria da Fase 2.
3. Reexecutar a homologação distribuída após esses merges.
4. Só então promover o desenvolvimento completo de
   `prompt_evo_forge_ecossystem_obs.md`, usando este arquivo como baseline e
   preservando os estados `PARTIALLY_IMPLEMENTED`, `BLOCKED` e `DEFERRED`.
