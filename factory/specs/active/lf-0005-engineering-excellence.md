---
id: lf-0005
title: engineering-excellence-grill
status: active
created: 2026-10-12
owner: the-forge
scope: ecosystem
priority: p0
---

# Engineering Excellence Grill

## Outcome

Entregar controle federado, determinístico, econômico e legível para evolução de oito Forjas. Usuário vê capacidade existente, gap, risco, evidência e próximo passo sem caçar comando.

## Grill gate

- Problema observado: capacidades existem em várias Forjas, mas paridade, evidência e estado federado ficam dispersos.
- Usuário afetado: pessoa instalando Forjas, agente roteando demanda, mantenedor aprovando release.
- Falha concreta: diagnóstico manual mistura estado, docs e testes; comparação entre Forjas exige leitura de repositórios.
- Decisão: criar auditoria determinística reutilizando contratos, registries, docs e testes existentes.
- Fora de escopo: reescrever arquitetura, substituir registries, criar agente genérico, obrigar hospedagem comum.
- Critério de parada: nenhuma fase aceita sem teste, evidência, docs atualizados e comando reproduzível.

## Waves

### Wave 0 — baseline e contrato

- Mapear oito repositórios, capacidades, gaps e dependências.
- Publicar matriz de paridade, análise de gaps, roadmap e decisão.
- Registrar referências externas e limites de uso.

### Wave 1 — auditoria determinística

- Expor `theforge excellence audit`.
- Emitir texto humano e JSON estável.
- Verificar identidade, branch, commit, docs, testes, capability registry, instalação, MCP e portal.
- Retornar códigos previsíveis: sucesso, gaps encontrados, entrada inválida, indisponível.

### Wave 2 — contrato federado

- Adicionar descriptors de capability sem duplicar registry local.
- Separar invocação humana de seleção agentic.
- Negociar suporte, confiança, custo, modo terminal e referências.

### Wave 3 — contexto e plano

- Conectar glossary, bounded context, context pointers e task graph existentes.
- Gerar plano proporcional a risco, complexidade e orçamento.

### Wave 4 — qualidade operacional

- Integrar TDD, execution frontier, revisão independente, diagnóstico e architecture fitness.
- Preservar autonomia local de cada Forja.

### Wave 5 — benchmark, UX e release

- Publicar benchmark de capability, retro federada, compatibilidade de hosts e onboarding.
- Validar CLI, TUI, Rui e Portal em telas/terminais disponíveis.

## Acceptance

- Oito repositórios aparecem em matriz única.
- Auditoria sem rede e sem credencial produz evidência reproduzível.
- Falhas não escondem gap nem inventam capability.
- Saída terminal adapta modo TTY/non-TTY, largura e JSON.
- Docs apontam comando, contrato, limitações e próximos passos.
- Cada wave tem commit, testes e revisão independente.

## Evidence contract

Cada resultado contém `repo`, `capability`, `state`, `evidence`, `confidence`, `cost`, `next_action`. Evidência aponta para caminho relativo, teste, comando ou commit. Estado sem evidência vira `unknown`.

## Rejected

- Monorepo artificial.
- Registry federal substituindo registries locais.
- Auto-modificação de arquitetura a partir de retro.
- Dependência obrigatória em navegador, MCP ou agente específico.

## Pending

- Validar contratos reais de cada adapter.
- Definir benchmark mínimo por domínio após auditoria.
- Rodar experiência visual em terminais Windows/Linux/macOS e Portal após mudanças.
