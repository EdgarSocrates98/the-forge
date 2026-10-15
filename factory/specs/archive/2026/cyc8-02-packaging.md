---
id: cyc8-02
title: packaging-conformance-matrix
status: done
created: 2026-10-15
owner: the-forge
scope: ecosystem
cycle: 8
wave: 1
priority: p0
risk: high
agent: codex
source: prompt_evo_cycles.md §8.7
verification:
  - python scripts/check_gates.py --pytest
---

# Conformidade de empacotamento dos nove repos

## Outcome

Cada repositório empacotável e instalável via canal adequado — wheels/pipx/uv/venv para projetos Python, npm/npx para Forge CLI, bundle estático verificável para Forge Portal — com artefatos verificáveis e sem Docker obrigatório.

## Grill gate

- Problema observado: instalação hoje depende de checkout/setup.sh; não há artefato verificável por projeto.
- Usuário afetado: desenvolvedor externo instalando uma versão identificável.
- Falha concreta: "instalado" ≠ "instalável como pacote"; caminhos de dev vazam para o usuário.
- Decisão: adotar canais do §8.7 por tipo de projeto; build de artefato + teste de instalação em venv/ambiente limpo.
- Fora de escopo: publicar no PyPI/npm agora; Docker como requisito; binário standalone do CLI salvo justificativa técnica.
- Critério de parada: para cada repo, artefato construído, instalado em ambiente limpo e smoke test passando.

## Acceptance

- Projetos Python (6 engines/doctors + the-forge): wheel buildável, instalável em venv isolado (pipx/uv tool), smoke test do pacote instalado.
- Forge CLI: pacote npm instalável sem privilégios administrativos (npx/local); decisão sobre bundle standalone documentada.
- Forge Portal: bundle estático com verificação de integridade de assets e inicialização pelo backend oficial; compatibilidade bundle↔API testada.
- Checklist de "dependência indevida do checkout" zerado por repo.
- Docker permanece opcional (demo/teste), nunca requisito.

## Constraints

- Respeitar stdlib-only do core the-forge e dos adapters.
- Manter independência: nenhum especialista ganha dependência obrigatória de CLI/Portal/the-forge.

## Rejected

- Publicação real em registries sem autorização.
- Empacotar o que ainda não é distribuível — registrar gap em vez de contornar.

## Pending

- ⚠ Quais repos já têm `pyproject.toml`/`package.json` publicáveis vs. só setup.sh (levantar na baseline cyc0-01).
- ⚠ pipx vs uv tool como canal recomendado — decisão de documentação.
