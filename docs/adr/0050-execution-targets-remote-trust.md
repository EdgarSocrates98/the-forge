# ADR 0050 — Execution targets, classificação de dados e trust remoto (modelo primeiro)

- Status: aceito (2026-10-15)

## Contexto

Cycle 5 introduz execução federada. Sem um modelo de alvos e dados, "remote"
viraria `ssh + comando arbitrário` — inaceitável para a invariante de
governança da plataforma.

## Decisão

**Alvos declarados, nunca descobertos.** `ExecutionTarget/v1` (`local`,
`isolated-local`, `remote-forge`, `a2a-agent`) é carregado de
`targets.toml` (`.forge/config/` vence o de usuário). Sem arquivo, o único
alvo é o `local` builtin. Negociação (`negotiate_target`) escolhe o melhor
par provider×target com ordenação determinística — localidade > saúde > trust
> id — e registra toda recusa (`refusals`), nunca descarte silencioso.

**Classificação estrutural.** `unknown` só é admitido por alvos locais;
`remote-*`/`a2a-agent` jamais carregam `confidential`/`restricted`/`unknown`
— o cap é do contrato, não configurável. `a2a-agent` tem trust travado em
`unverified` no registro do alvo: promoção acontece via policy, não via
auto-declaração.

**Remote é modelo, não transporte.** `RemoteExecutionRequest/v1` só existe
totalmente ligado (hashes de task/context/budget, fingerprint de surface,
identidade do alvo, artifacts esperados) e `policy_decision="allow"` exige
`policy_ref`. `RemotePolicy` (remote-policy.toml) é deny-by-default com
allowlist explícita; o gate é monotônico (estilo in-toto: nada omitido pode
virar deny→allow). `RemoteExecutionReceipt/v1` liga `request_sha256` e hashes
de input/output; `accept_receipt` compara replay binding, eco de identidade e
cobertura dos artifacts esperados — divergências são violações nomeadas.

**Custo nunca vence segurança** (§133): economia compara local×remote só com
métricas medidas; `cost=unknown` permanece unknown.

## Consequências

- Não existe caminho no core que execute em remote sem policy explícita e
  request ligado por hash.
- Dados `confidential`/`restricted`/`unknown` são estruturalmente locais.
- Simulação (`PlanSimulation`) registra `execution_target` por nó ou a
  limitation `no valid execution target`.
