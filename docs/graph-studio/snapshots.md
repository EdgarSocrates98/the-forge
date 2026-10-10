# Snapshots

Platform Forge engines produce snapshots (`graph snapshots`, `diff`,
`at`, `timeline`). Adapters surface `descriptor.snapshot_id` when the
loaded graph carries one. The Studio's snapshot selector/timeline
renders only when `capabilities` advertise `snapshot_listing`/`temporal`
— absent history, the controls stay hidden.
