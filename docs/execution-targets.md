# Execution Targets e classificação de dados (Cycle 5, Waves H–L)

Execução não escolhe só o *melhor provider* — escolhe o melhor
**par provider×target válido** (§73). Alvos são declarados, nunca
descobertos; remote é um modelo de trust, não um transporte
([ADR 0050](adr/0050-execution-targets-remote-trust.md)).

## `targets.toml`

```toml
# .forge/config/targets.toml (projeto vence o de usuário, por id)
[[targets]]
id = "local-ci"
type = "isolated-local"           # local | isolated-local | remote-forge | a2a-agent
health = "healthy"
data_classes = ["internal", "confidential"]

[[targets]]
id = "ci-remote"
type = "remote-forge"
identity_ref = "org-forge:ci"     # obrigatório para tipos remotos
network = "egress"                # obrigatório para tipos remotos
trust = "verified"                # unverified | verified | org-approved
data_classes = ["public", "internal"]
health = "healthy"
```

Sem arquivo, o único alvo é o `local` builtin (verified, todas as classes —
é o runtime que o próprio Forge controla). Entradas malformadas viram
warnings, nunca quebram o planning.

## Caps estruturais (contrato)

- `unknown` só é admitido por `local`/`isolated-local`;
- tipos remotos jamais carregam `confidential`/`restricted`/`unknown`;
- `a2a-agent` só carrega `public` e seu trust fica travado em `unverified`
  — promoção acontece via policy, não via auto-declaração;
- tipos remotos exigem `identity_ref` + `network="egress"`.

## Negociação (`negotiate_target`)

`TargetRequirement` (de `PlanNode.required_locality`/`data_classification`)
casa contra cada alvo: recusas são nomeadas em `refusals`, e os candidatos
ordenam localidade > saúde > trust > id — contenção primeiro, sempre
determinístico. `simulate_plan` registra `execution_target` por nó ou a
limitation `no valid execution target` — nunca um chute de placement.

## Remote trust model (`remote-policy.toml`)

```toml
[remote.policy]
policy_ref = "org-forge:policy/remote.v1"
allowed_target_ids = ["ci-remote"]
allowed_identity_refs = ["org-forge:ci"]   # pinning opcional de identidade
max_data_classification = "internal"       # teto da organização
require_healthy = true
```

Deny-by-default e monotônico (in-toto): allowlist vazia ⇒ tudo negado; nada
omitido vira deny→allow. `remote-forge` exige trust ≥ `verified`; `a2a-agent`
só passa com promoção explícita no policy.

`build_request` emite `RemoteExecutionRequest/v1` totalmente ligado (sha256
de task/context/budget, fingerprint de surface, identidade do alvo,
artifacts esperados) ou levanta `ContractError` com as razões do deny.
`accept_receipt` valida o replay binding: `request_sha256`, eco de
target/identity/provider, cobertura dos artifacts esperados e presença de
verificação — divergências são violações nomeadas, nunca toleradas.

**Não existe transporte no core** — o modelo é o contrato; um futuro
conector remoto consome request + receipt por essa porta.

## CLI

```text
theforge targets list                       # alvos declarados (user+project)
theforge targets negotiate --provider p --capability x.y \
    --locality local-or-remote --data-classification internal
theforge remote policy                      # política efetiva (ausente = deny-all)
theforge remote check --data-classification internal
```

`targets negotiate` roda o mesmo `negotiate_target` do planner (dry-run;
exit 4 quando nenhum alvo serve). `remote check` avalia cada alvo remoto
declarado contra a política e mostra `allow`/`deny` com as razões — inspeção
pura, nada executa.
