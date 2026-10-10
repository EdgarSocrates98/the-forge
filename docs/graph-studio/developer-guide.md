# Developer guide

Add a forge's graph to the Studio:

1. Write `<pkg>/graphview.py`: `build_view(...) -> ForgeGraphView|None`
   using the vendored `<pkg>/_graphview.py` contract.
2. Advertise only real capabilities; map epistemic vocab via
   `EPISTEMIC_TRANSLATION`; put truncations in `descriptor.limitations`.
3. Wire `graph view` (JSON out) + `graph ui` (`open_studio`, gate via
   `graph_studio_enabled(root, state_rel=..., user_state_rel=...)`).
4. Canonical files live in the-forge (`_installkit.py`,
   `contracts/graphview.py`, `graphstudio.py`, `ui/`); sibling copies
   are vendored and lint-exempt — change the canonical, then re-vendor.
5. Test: fixture graph → view schema round-trip; no-graph → named
   refusal; real engine → counts match the engine's own stats.
