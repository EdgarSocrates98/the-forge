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
