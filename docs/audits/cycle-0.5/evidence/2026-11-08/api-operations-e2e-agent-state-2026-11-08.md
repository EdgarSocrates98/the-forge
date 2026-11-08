# API Operations E2E — Agent Bridge availability classification

The deterministic lab was rerun after `forge-bridge status` reported an
installed, authenticated Devin provider.

- Result: `PASS_WITH_LIMITATIONS`
- Specialist roster gate: `PASSED` — 12 entries, all `CONFORMANT`, all
  `routable=true`
- Agent provider gate: `NOT_RUN` — Devin was detected as authenticated, but no
  external session was invoked by the lab
- Fake provider: ignored for availability because it is not installed
- Agent Bridge local suite: `124 passed in 102.64s`
- Receipt SHA-256:
  `D3311DAF6BDC6A001AA894E8EE477652F97B2675B321FD661C96AB70C437F787`

This classification is intentionally different from `UNAVAILABLE`: provider
inventory and authentication are real evidence, while session execution still
requires an explicitly governed invocation and remains outside this
deterministic lab.
