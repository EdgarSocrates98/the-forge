# theforge-sparkforge-azure-adapter

Forge Protocol v1 provider adapter that exposes **Spark Forge Azure**
(`sparkforge-azure`, package `sparkforge_azure`) to The Forge.

The adapter is a separate distribution installed in the specialist's own
interpreter (a sibling venv — see `docs/real-providers.md`). It imports only
`sparkforge_azure` public seams, speaks `forge/v1` on stdin/stdout, and never
imports `theforge`. The Forge core knows nothing about Azure — every claim in
the manifest is derived from the recorded native surface
(`native_surface.json`, rewritten by `python -m theforge_sparkforge_azure.record`
in the specialist venv; `--check` classifies drift).

```text
python -m theforge_sparkforge_azure [options] describe|health|execute
python -m theforge_sparkforge_azure.record [--check] [--out PATH]
```

`--replay <dir>` replays a recorded scenario (`environment.json`,
`health.json`, `<capability>.<action>.json`) without the specialist —
the offline conformance path the test suite uses.

Azure is its own reality: capabilities the adapter declares come from the
Azure surface only (`sdd.*` gates over a staged `docs/sdd`, `*.access-diagnose`
over a staged case bundle with `case.yaml`, `azure.doctor` env report). No
AWS↔Azure equivalence is assumed anywhere.
