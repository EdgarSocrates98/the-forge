# theforge-doctorapi-adapter

Forge Protocol v1 provider adapter that exposes **Forge Doctor API**
(`forge-doctor-api`) to The Forge. Separate distribution, stdlib-only, installed in the
specialist's interpreter (Python >= 3.11); the adapter itself runs on Python >= 3.10 for
`--replay` and environment refusals. It never imports `theforge`; it drives only the
specialist's **public seams** (spec 070 / §26):

| Capability | Action | Public seam |
| --- | --- | --- |
| `api.diagnose` | `analyze` | `DoctorBoundary.handle` + `endpoint_dict` — `ForgeRequest` → bounded `ApiHandoffBundle` v2 + `ForgeHandoff` envelope + `diagnostic-manifest` |
| `api.verify` | `verify` | `ApiHandoffBundle.from_dict` / `ForgeHandoff.parse` strict parse + `body_sha256` integrity for v2 bundles |

The diagnose runs over the staged workspace root (`stage/`): the adapter hands the
specialist a copy of the workspace, never the original. The emitted document
(`{bundle, handoff, capabilities, manifest}`) is stored verbatim (canonical JSON) as the
`native/handoff.json` artifact and translated into the Evidence Bus: findings → `Finding` +
one `Evidence` per native evidence entry, detected capabilities → observed evidence,
external references → typed-reference evidence (foreign graphs are never merged),
remediation candidates → `proposed` evidence, `UnknownFact`s → `unknowns`, and the service
graph / context refs stay inside the artifact (reference semantics).

## Install

```bash
python -m pip install -e path/to/forge-doctor-api -e path/to/adapters/doctorapi
```

## Record the native surface

`describe` derives the manifest from `native_surface.json`, a recorded snapshot of the
public seams (boundary methods, §26 protocol version, strict parses). Re-record it in the
specialist interpreter:

```bash
python -m theforge_doctorapi.record           # rewrite native_surface.json
python -m theforge_doctorapi.record --check   # exit 1 when the installed surface drifts
```

## Replay

`--replay <scenario>` serves `describe`/`health`/`execute` from a recorded scenario without
the specialist: `environment.json`, `health.json` and one `<capability>.<action>.json`
(the bridge document) or `<capability>.<action>.error.json` per action.
