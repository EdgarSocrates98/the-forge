# Federated mode

`theforge graph --federated` discovers sibling specialist checkouts
(workspace registry), runs each provider's `graph view` argv, and merges
the views with `federated_merge`:

- the producer argv comes from the checkout's `forge.agentic.json`
  `cli_entry` (`module:function` run via subprocess); a `cli_entry` key
  on `forge.json` is accepted as a fallback for minimal providers;
- node ids become `provider_id:node_id` — no silent unification;
- edge provenance becomes `provider/provenance`;
- `notes` list providers that were skipped, refused, or timed out —
  each note carries the reason (`refused <CODE>`, `producer exited N`,
  `no cli_entry declared`), so absence is displayed, never hidden;
- capability negotiation uses each descriptor's `capabilities` —
  unsupported operations are not offered;
- entity resolution is evidence-backed: heuristic matches would be
  `epistemic_state=inferred` with the match's source; nothing is
  auto-merged by name.
