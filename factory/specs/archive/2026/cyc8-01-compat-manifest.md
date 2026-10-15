---
id: cyc8-01
title: versioning-policy-compat-manifest
status: done
created: 2026-10-15
owner: the-forge
scope: ecosystem
cycle: 8
wave: 1
priority: p0
risk: high
agent: codex
source: prompt_evo_cycles.md §8.3, §8.4
verification:
  - python scripts/check_gates.py --pytest
---

# Política de versões + Compatibility Manifest

## Outcome

Política explícita de versionamento por projeto e manifesto versionado `forge/EcosystemCompatibility/v1` reutilizando contratos existentes — a release integrada como matriz de compatibilidade certificada, não monólito de versão única.

## Grill gate

- Problema observado: nove projetos com ciclos de vida independentes e sem manifesto declarando quais combinações de versões são certificadas.
- Usuário afetado: quem instala/atualiza Forjas (CLI, Portal, host) e quem certifica releases.
- Falha concreta: update pode combinar versões incompatíveis sem aviso; não há fonte de verdade de compatibilidade.
- Decisão: versionamento SemVer quando apropriado, versões separadas (Forja, contratos, instalador, assets de host, Portal, interfaces MCP) e manifesto com ranges suportados.
- Fora de escopo: bump automático de todos os repos para mesma versão; schema novo quando já houver mecanismo equivalente.
- Critério de parada: manifesto validável por contrato, com versões reais, consumível por CLI/Portal.

## Acceptance

- Política de versões documentada por projeto (SemVer onde apropriado).
- Manifesto versionado incluindo os 9 componentes (engines, Doctors, CLI, Portal) conforme seus mecanismos de versionamento.
- `contracts` declara ranges suportados (`specialist_manifest`, `install_receipt`, `portal_api`, MCP quando aplicável).
- Reuso dos contratos `theforge/<Name>/v1` existentes; nenhum schema duplicado.
- Zero versões fictícias em manifesto publicado.
- Testes de validação do manifesto no repo.

## Constraints

- Contratos mudaram → regenerar `schemas/` via `python -m theforge.contracts.schema schemas`.
- Não adicionar dependências obrigatórias de CLI/Portal aos especialistas.

## Rejected

- Versão única obrigatória do ecossistema.
- Atualização automática de todos os repos em bloco.

## Pending

- ⚠ Formato final do manifesto: confirmar se estende `specialist_manifest`/`install_receipt` ou cria `EcosystemCompatibility/v1` (decisão de produto no grill).
- ⚠ Onde o manifesto vive (the-forge? pacote próprio? artefato de release?).
