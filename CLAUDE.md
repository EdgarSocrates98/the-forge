# The Forge — guia para agentes

The Forge = control plane (WHO/WHEN/HOW). Forges especialistas = WHAT.

<!-- theforge:invariants:begin -->
## Invariantes
- Core (`src/theforge`): runtime stdlib-only, Python >= 3.11, dependências só em `[dev]`. Providers só via Forge Protocol (subprocess + JSON); nunca `import sparkforge`/`apiforge`. Nenhum conhecimento de domínio (Spark, API, …): ele vem dos sinais declarados pelos providers.
- Adapters (`adapters/`): distribuições à parte, stdlib-only, instaladas no interpretador de cada especialista (Python >= 3.10). Únicos que importam `sparkforge`/`apiforge`; nunca importam `theforge`.
- Routing determinístico, sem LLM no core: ambiguidade vira `ambiguous`, nunca um chute.
- Nenhum caminho reporta sucesso sem um `ExecutionResult` válido.
- Tudo que o core persiste passa por `security.redact`, exceto `.forge/runs/<id>/work/` (escrito pelo provider). Credenciais nunca chegam ao env dos providers.
- Contratos `theforge/<Name>/v1`; mudou um contrato, regenere `schemas/`: `python -m theforge.contracts.schema schemas`.
- Setup: `python -m pip install -e .[dev] -e ./adapters/sparkforge -e ./adapters/apiforge`. Testes: `python -m pytest` (offline); gate: `python -m pytest -m slow`. Lint/tipos: `ruff check .` · `mypy`.
<!-- theforge:invariants:end -->

## Regras persistentes
- Idioma: pense em inglês, responda em português; Markdown de spec no idioma de `spec.json.language`.
- Workflow Kiro: skills em `.claude/skills/kiro-*/SKILL.md` (`/kiro-<nome>`); specs em `.kiro/specs/`, steering em `.kiro/steering/` (locais, fora do git). Revisão humana em cada fase; `-y` só para fast-track intencional.
- Mudou skill ou instrução de host: edite os três hosts e rode `python scripts/agentic/audit_assets.py`.

## Mais contexto
`docs/agentic.md` (workflow Kiro, hosts, mirrors), `docs/architecture.md`, `docs/protocol.md`, `docs/real-providers.md` (adapters; `_shell.py` idêntico nos dois), `docs/adr/`; spec do ciclo 1 em `docs/superpowers/specs/`.
