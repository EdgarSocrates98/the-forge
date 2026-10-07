# Adaptive Experiments

`StrategyExperiment/v1` turns shadow recommendations into an auditable
experiment lifecycle.

States:

planned -> shadow -> observing -> eligible_for_review

and terminal/deferred states:

promoted, rejected, stale, cancelled.

Cycle 4.1 never automatically promotes a challenger. Surface drift invalidates
the experiment. Evaluation must be separated from the observations used to form
the hypothesis when possible, preferably with a deterministic time cut-off.


## Eligibility for review

A challenger does not become reviewable merely because enough runs exist.
Cycle 4.1 requires all of the following:

- both champion and challenger have evaluation observations;
- the holdout cut-off excludes hypothesis history when configured;
- the challenger verification rate is not worse than the champion;
- the challenger delivered-result rate is not worse than the champion;
- at least one comparable measured economy axis improves (context bytes,
  wall time or cost);
- no other comparable measured economy axis regresses;
- both provider surfaces still match the experiment contract.

Unknown metrics stay unknown. An experiment with no measured economy gain
remains `observing` rather than manufacturing a win.

The CLI surface is read-only:

```bash
theforge economy experiment --spec experiment.json --json
```

It evaluates the spec against local `ExecutionObservation` history only.
It never changes routing, budgets, profiles or provider trust, and it never
promotes automatically.


Task family é comparada exatamente, inclusive o estado não resolvido (`None`).
Um experimento não pode misturar silenciosamente famílias distintas.


### Holdout temporal

`evaluation_after` é o corte explícito preferido. Se `evaluation_after` estiver
ausente e `discovery_before` existir, o core usa `discovery_before` como
corte mínimo da avaliação. Runs no corpus de descoberta/hipótese não contam como
evidência de validação.


### Cobertura mínima

A elegibilidade também exige cobertura por braço: cada estratégia precisa ter pelo
menos metade de `minimum_runs` (arredondada para baixo, mínimo 1), além do mínimo
global. Um eixo econômico só conta como evidência de ganho quando está medido em
**todos** os runs de ambos os braços. Cobertura parcial permanece incerteza e não
prova melhoria.
