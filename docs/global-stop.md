# Global Stop and Information Gain

The Forge owns cross-provider continuation.

`theforge/GlobalStopDecision/v1` is a core artifact. It is never provider-authored.

Current Cycle 4.1 integration is deliberately conservative: after an executed
plan reaches its final planned node, The Forge writes `global-stop.json` and
binds its hash in the plan receipt. If no unresolved questions remain the action
is `stop_sufficient_evidence`; if unresolved questions remain but the plan has
no remaining candidate, it records `stop_no_expected_gain`.

This is not yet an arbitrary early-stop scheduler. That future step requires
proof that remaining nodes are optional, add no unique capability, and are not
required for independent verification.

Safety ordering: policy/budget/user constraints and mandatory verification
always dominate economy.


## Terminal plan semantics

Ausência de próximo nó no plano não significa `no_expected_gain`. No fechamento
terminal o core usa ganho `unknown` quando ainda existem incógnitas, porque não há
um candidato concreto sendo avaliado. Portanto:

- sem incógnitas e com verificação satisfeita: `stop_sufficient_evidence`;
- com verificação obrigatória pendente: `continue`;
- com incógnitas restantes e nenhum candidato concreto: `continue` + ganho
  `unknown`.

`stop_no_expected_gain` fica reservado para uma decisão em que um candidato real
tenha sido avaliado e não ofereça evidência incremental declarada.


## Falhas são incerteza, não evidência

Falhas de nós também são unresolved. Um nó `refused`, `provider_failure`,
`no_route` ou `skipped` é materializado como
`node:<id>:<status>` na decisão global. Assim, um plano parcial/falho nunca
pode terminar como `stop_sufficient_evidence` apenas porque nenhum provider
retornou uma string em `unknowns`.
