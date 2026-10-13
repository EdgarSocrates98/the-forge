# ADR 0040 — A2A bridge: adapter de documentos, agente remoto nunca provider local

- Status: aceito (2026-10-07)
- Cycle 4, Wave I — phases 59–67

## Contexto

O ciclo exige interoperabilidade experimental com A2A (agent-to-agent)
sem que o protocolo externo contamine o core. A2A v1.0.x modela Agent
Cards, skills, tasks, messages/parts e artifacts; autenticação é declarada
no card e transportada na camada HTTP — fora dos payloads do protocolo.

## Decisão

1. **`theforge.interop.a2a` é uma ponte de documentos**, não um cliente de
   execução. Converte: `RegistryRecord`→Agent Card, `TaskSpec`→`message/send`
   params, `ExecutionResult`→artifacts/parts, Agent Card→`ForgeRegistryEntry`.
   Nenhuma função abre conexão, executa agente ou aceita credencial.

2. **Core A2A-independente.** Nada fora de `interop/` importa o módulo; a
   única exceção é `registry/remote.py`, que o conecta como `A2ACardSource`
   (subclasse de `HttpRegistrySource` que sobrescreve apenas `_decode`) —
   o mesmo transporte, cache verificado e kill-switch dos `http` sources.

3. **Novo source kind `a2a`.** `registries.toml` ganha `kind = "a2a"` com
   `url` = Agent Card URL. O documento produzido é um `RegistryDocument`
   de uma entrada — logo negotiation e remote discovery consideram o agente
   por demanda sem código novo.

4. **Metadados Forge via `metadata.forge`.** O que A2A não modela
   (fingerprints, trust, execution, requirement, constraints, hashes) é
   preservado numa extensão namespaced — nunca achatado em texto nem
   descartado; modalidades não-texto viram limitation explícita.

5. **Agente remoto ≠ provider local.** O entry convertido carrega
   `runtime.requires_network=true`, `offline=false`,
   `requires_credentials` conforme o card, `distribution=None` e
   limitations de fronteira (external, unverified, data egress,
   authentication). O fit máximo permanece `declared` — verificação é
   pré-condição de qualquer elevação futura.

## Alternativas rejeitadas

- **Cliente A2A completo (JSON-RPC + streaming)**: fora do escopo e
  contradiz "remote execution é dimensão de política" — execução remota
  exigiria aprovação e egresso explícitos que o ciclo não autoriza.
- **`DistributionRef` para o endpoint**: um endpoint não é artefato
  imutável nem pinável por hash — modelá-lo como distribuição mentiria
  sobre instalabilidade.
- **Elevar `securitySchemes` a capability de auth**: a presença de esquemas
  só prova que o card *declara* auth — registramos a exigência, jamais
  a satisfazemos.

## Consequências

- Remote discovery ganha agentes A2A de graça (candidatos `declared`).
- O card emitido pelo bridge reconverte na mesma provider id/capabilities —
  round-trip sem perda, mas sempre como claim não-verificado.
- Wave L herda a superfície adversarial (card malicioso, injeção em
  descriptions, oversized result) já parcialmente coberta pelos limites
  de `_text`/`_MAX_SKILLS`/`_MAX_PARTS`.
