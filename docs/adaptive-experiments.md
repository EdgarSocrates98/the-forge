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
