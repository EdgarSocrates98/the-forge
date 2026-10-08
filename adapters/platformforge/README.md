# theforge-platformforge-adapter

Forge Protocol v1 provider adapter that exposes **Platform Forge**
(`platformforge`) to The Forge.

The adapter is a separate distribution installed in the specialist's own
interpreter (a sibling venv — see `docs/real-providers.md`). It imports only
`platformforge` public seams, speaks `forge/v1` on stdin/stdout, and never
imports `theforge`. The Forge core knows nothing about platforms — every claim
in the manifest is derived from the recorded native surface
(`native_surface.json`, rewritten by `python -m theforge_platformforge.record`
in the specialist venv; `--check` classifies drift).

```text
python -m theforge_platformforge [options] describe|health|execute
python -m theforge_platformforge.record [--check] [--out PATH]
```

`--replay <dir>` replays a recorded scenario (`environment.json`,
`health.json`, `<capability>.<action>.json`) without the specialist —
the offline conformance path the test suite uses.

Platform Forge declares its own `platformforge/capability-manifest/v3` surface
(29 tools, 6 operation executors, the `cross_forge` delegation contract). The
adapter exposes only the offline, read-only analyze seams (`iac`, `plan`,
`state`, `k8s`, `secrets`, `gha`, `gitops`, `catalog`) plus `platform.manifest`;
mutating executors the manifest marks `runtime_available: false` are never
claimed as capabilities.
