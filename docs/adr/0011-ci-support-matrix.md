# ADR 0011 — Matriz de suporte de CI: macOS e Python 3.14

- Status: aceito (2026-10-03)

## Contexto
O ciclo 1 não tinha CI. O core é stdlib-only e suporta Python >= 3.11, mas tem código específico de plataforma (kill de árvore via Job Object no Windows, grupo de processos no POSIX). Runners macOS custam mais que Linux e Windows.

## Decisão
- `ci.yml` (gate de PR; `pull_request` e `push` em `main`): `ubuntu-latest` e `windows-latest` × Python 3.11, 3.12, 3.13 e 3.14, com `fail-fast: false`. Roda ruff, mypy, paridade de schemas e a suíte offline. O job `package` constrói sdist e wheel, checa zero dependências e instala o wheel em venv novo.
- 3.14 entra no gate porque está em GA. 3.15 fica fora até o GA.
- macOS fica fora do gate de PR por custo. `compat.yml` roda `macos-latest` × 3.11 e 3.14 semanalmente e por `workflow_dispatch`.
- `real-providers.yml` (semanal e `workflow_dispatch`, sem trigger de PR, `continue-on-error`) faz checkout dos repositórios irmãos em `siblings/spark-forge-aws` e `siblings/api-forge` e roda `pytest -m real_provider`. Na Wave A não há testes, então a seleção vazia passa.
- Segredo: `SIBLING_REPOS_TOKEN` (com fallback para `github.token`) aparece só no `with.token` dos dois steps de checkout dos irmãos, com `persist-credentials: false`. Nunca chega a `env` nem a `run`. Todos os workflows usam `permissions: contents: read`.

## Alternativas
- **macOS no gate de PR:** cobre o POSIX de novo, já coberto pelo Linux, com custo maior por PR.
- **Só 3.11 e a versão mais nova:** perde regressões intermediárias a custo baixo.

## Consequências
Uma regressão só de macOS pode chegar à `main` e aparecer na execução semanal. O contrato de ambiente dos providers reais (variáveis, caminhos) é definido na Wave B.

## Reavaliar quando
3.15 entrar em GA, ou um defeito só de macOS escapar do gate.
