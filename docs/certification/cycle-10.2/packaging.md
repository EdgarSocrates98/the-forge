# Cycle 10.2 — F-RC-1 CLOSED (real fix, not wheel-only)

## Problema
`sdist` excluía `/.agents` inteiro; o wheel force-inclui `.agents/skills` (ADR-0058)
→ wheel-from-sdist impossível.

## Correção
`pyproject.toml`: exclusão do sdist estreitada — `/.agents` removido do exclude
(o diretório contém apenas `skills/`, bytes já distribuídos em todo wheel;
nada extra é exposto). Mantidos excluídos: `/adapters` (distribuições separadas),
`/.claude /.devin /.codex /.kiro /.tokensave /CLAUDE.md /AGENTS.md` (estado local
/ mirrors de host — ADR-0020 preservado no espírito: estado local não empacota).

## Evidência (executada em 2026-10-16, Linux)
- `python -m build --sdist` → sdist contém `.agents/skills` (33 skills).
- Extração + `python -m build --wheel` do sdist → wheel OK.
- Payload do wheel direto == payload do wheel do sdist: **298 arquivos idênticos**.
- Install em venv limpa + `theforge --version` + `theforge doctor` → healthy.
- Sem caminhos absolutos locais; sem secrets; runtime não depende do checkout.

## Regressão permanente
`.github/workflows/release-gates.yml` job `gate/build` agora faz
sdist → extract → wheel-from-sdist → comparação de payload (excl. dist-info).
Falha vira CI vermelho.
