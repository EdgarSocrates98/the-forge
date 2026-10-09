# The Forge — instruções para Codex e Devin

The Forge = control plane (WHO/WHEN/HOW). Forges especialistas = WHAT. Este arquivo é lido pelo Codex e pelo Devin Local / CLI; o Claude Code lê `CLAUDE.md`, com o mesmo bloco de invariantes.

<!-- theforge:invariants:begin -->
## Invariantes
- Core (`src/theforge`): runtime stdlib-only, Python >= 3.11, dependências só em `[dev]`. Providers só via Forge Protocol (subprocess + JSON); nunca `import sparkforge_aws`/`apiforge`. Nenhum conhecimento de domínio (Spark, API, …): ele vem dos sinais declarados pelos providers.
- Adapters (`adapters/`): distribuições à parte, stdlib-only, instaladas no interpretador de cada especialista (Python >= 3.10). Únicos que importam `sparkforge_aws`/`sparkforge_azure`/`apiforge`/`platformforge`/`forge_doctor_data`/`forge_doctor_api`; nunca importam `theforge`.
- Routing determinístico, sem LLM no core: ambiguidade vira `ambiguous`, nunca um chute.
- Nenhum caminho reporta sucesso sem um `ExecutionResult` válido.
- Tudo que o core persiste passa por `security.redact`, exceto `.forge/runs/<id>/work/` (escrito pelo provider). Credenciais nunca chegam ao env dos providers.
- Contratos `theforge/<Name>/v1`; mudou um contrato, regenere `schemas/`: `python -m theforge.contracts.schema schemas`.
- Setup: `python -m pip install -e .[dev] -e ./adapters/sparkforge_aws -e ./adapters/sparkforge_azure -e ./adapters/apiforge -e ./adapters/platformforge -e ./adapters/doctordata -e ./adapters/doctorapi`. Testes: `python -m pytest` (offline); gate: `python -m pytest -m slow`. Lint/tipos: `ruff check .` · `mypy`. Gates locais num comando: `python scripts/check_gates.py` (`--pytest` inclui a suíte).
<!-- theforge:invariants:end -->

## Comum aos dois hosts
- Idioma: pense em inglês, responda em português. Todo Markdown escrito em arquivos de spec (`requirements.md`, `design.md`, `tasks.md`, `research.md`, relatórios de validação) usa o idioma de `spec.json.language`.
- Workflow Kiro (spec-driven): specs em `.kiro/specs/`, steering em `.kiro/steering/` (locais, fora do git). Aprovação em 3 fases (Requirements → Design → Tasks → Implementation) com revisão humana em cada fase; `-y` só para fast-track intencional. Fases, comandos, delegação e manutenção dos mirrors: `docs/agentic.md`.
- Fase atual: **Feature Freeze + DOGFOODING** (`docs/feature-freeze.md`). Permitido: bugfix, security, compatibilidade com surfaces dos especialistas, performance, docs, testes, pequenas correções de CLI/UX. Proibido sem ADR: novos subsistemas, transporte remoto, marketplace, runtime distribuído, backend de memória novo, quebra de contrato `stable candidate`. Problemas observados viram observações (`docs/dogfooding.md`), nunca feature silenciosa.
- Siga as instruções do usuário com precisão e, nesse escopo, conclua o trabalho de ponta a ponta; pergunte só quando faltar informação essencial.
- Use as skills pedidas e as relevantes ao domínio da tarefa; protocolos comuns: `kiro-review` (revisão adversarial), `kiro-debug` (causa raiz), `kiro-verify-completion` (evidência fresca antes de declarar conclusão).
- Mudou skill ou instrução de host: edite os três hosts (`.claude/`, `.agents/`, `.devin/`) e rode `python scripts/agentic/audit_assets.py`.
- Mais contexto: `docs/architecture.md`, `docs/protocol.md`, `docs/real-providers.md`, `docs/adr/`.

## Codex
- Skills em `.agents/skills/kiro-*/SKILL.md`; invoque com `$kiro-<nome>` (ex.: `$kiro-spec-status <feature>`); `/skills` lista as disponíveis.
- Subagentes vêm habilitados por padrão. Dê a cada implementador e revisor independente um contexto novo com as entradas da tarefa. Sem delegação, siga o fallback inline da skill e identifique a revisão como inline; descobrir uma skill não prova revisão independente.

## Devin Local / CLI
- Skills em `.devin/skills/kiro-*/SKILL.md`; invoque com `/kiro-<nome>`. Os controladores de workflow rodam na conversa principal (Devin Cloud não é configurado).
- Delegue com `run_subagent`/`read_subagent`: `subagent_general` para implementar, revisar com testes e depurar; `subagent_explore` é só leitura. Contexto novo por worker, com checkout e caminhos absolutos; espere o resultado antes da revisão.
- Mantenha sequenciais os workers que escrevem no repositório. Sem subagentes disponíveis, siga o fallback inline e reporte a revisão como inline, não como independente.
