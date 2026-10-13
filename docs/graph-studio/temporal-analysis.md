# Temporal analysis

Engines with real history (platform-forge `at`/`timeline`, snapshot
diffs) expose it through `descriptor.capabilities += ("temporal",)`.
The Studio never synthesizes time series from a single snapshot; the
timeline control only appears for engines that advertise `temporal`.
