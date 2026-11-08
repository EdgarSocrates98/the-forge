# Control-plane provider execution — 2026-11-08

## Command

```text
uv run pytest tests/test_control_plane_e2e.py -q -rA
```

## Result

`4 passed`.

The test `test_e2e_delegate_analyze_pyspark_to_aws_checkout` resolved the
workflow command from the real `spark-forge-aws/forge.agentic.json`, executed
the resulting argv against the sibling checkout through
`theforge.delegation.execute`, and asserted a completed result with exit code
zero and a serializable delegation receipt.

The same run verifies that `HOST_AGENTIC` is only prepared, a missing checkout
is blocked instead of invented, and the real specialists catalog CLI returns a
structured manifest. The fixture uses static analysis over a local PySpark
project; it does not call AWS or mutate cloud resources.

## Boundary

This proves one real specialist execution through The Forge's control-plane
delegation path. It does not claim that every catalog entry has been executed,
nor that an external Agent Bridge session was created.
