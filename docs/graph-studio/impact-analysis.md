# Impact analysis

Impact comes from the *engine*, never from the Studio's geometry.

- `platformforge graph blast <node>` — real blast radius;
- `apiforge graph impact` — contract impact (observed vs inferred kept
  distinct in the view);
- `theforge` federation delegates impact to the owning provider when
  its descriptor advertises `impact_analysis`.

When no engine impact exists, the Studio offers neighbor expansion and
says so in the status bar.
