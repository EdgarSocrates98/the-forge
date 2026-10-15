---
id: cyc0-01
title: program-baseline-ecosystem-2026
status: done
created: 2026-10-15
owner: the-forge
scope: ecosystem
cycle: 0
wave: 0
priority: p0
risk: medium
agent: codex
source: prompt_evo_cycles.md §5 Wave 0, §8.2, §8
verification:
  - python scripts/check_gates.py --pytest
---

# Baseline do programa ecosystem-2026

## Outcome

Baseline verificada dos nove repositórios em `main` — SHAs, auditoria de distribuição, gaps classificados — publicada em `docs/programs/ecosystem-2026/` como âncora dos Cycles 8–10.

## Grill gate

- Problema observado: entregas de ciclos anteriores foram relatadas, mas sem verificação fresca sobre as `main` atuais.
- Usuário afetado: coordenador do programa e revisor de release.
- Falha concreta: retrabalho sobre funcionalidades já implementadas e bloqueios herdados sem evidência atual.
- Decisão: executar Wave 0 — auditar mains, capturar SHAs, tratar relatórios anteriores como histórico, classificar prioridades.
- Fora de escopo: implementar correções (specs seguintes), publicar releases, criar agentes novos antes de descobrir os existentes.
- Critério de parada: matriz inicial com evidência por repo e gaps P0/P1/P2 classificados.

## Acceptance

- `docs/programs/ecosystem-2026/` criado com `README.md`, `baseline.md`, `dependency-map.md`, `compatibility-matrix.md`, `open-gaps.md`.
- SHAs dos nove repos registrados com data de captura.
- Auditoria de distribuição (§8.2) por repo: build, artefatos, publicação, versionamento, runtime, deps transitivas, arquivos de instalação, update, rollback, teste de instalação de pacote, tags/releases, compatibilidade offline, dependência indevida de checkout, caminhos hardcoded.
- Bloqueios da homologação anterior (§3.4) marcados: resolvido / persiste / nova evidência.
- Nenhuma conclusão sem evidência apontando caminho, comando ou commit.
- Mínimo de documentação duplicada; referenciar docs canônicos existentes.

## Constraints

- Auditoria local, sem rede para verificação estrutural.
- Feature freeze: baseline é auditoria + docs, zero features.
- Não confundir funcionalidade existente com funcionalidade homologada.

## Rejected

- Reconstruir funcionalidades existentes.
- Marcar gap como resolvido sem reexecução.

## Pending

- ⚠ Caminho do relatório de homologação anterior (confirmar antes do dispatch).
- ⚠ `docs/programs/` já existe no the-forge? Confirmar estrutura alvo.
