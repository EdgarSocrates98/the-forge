# Provenance & epistemic state

Every edge carries `provenance` (who/what produced it) and
`epistemic_state` (contract vocabulary). Evidence refs (`fact_id`,
`source_file`, `line`, `confidence`) pass through unchanged — the Studio
displays them in the inspector; it never fabricates them.

Rule: *proximity is not causality* — the UI labels impact as computed by
the engine; absent an engine impact algorithm the viewer shows
neighbors, not inferred blast radius.
