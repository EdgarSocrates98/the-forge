# theforge-doctordata-adapter

Forge Protocol v1 provider adapter that exposes **Forge Doctor Data**
(`forge-doctor-data`) to The Forge. Separate distribution, stdlib-only, installed in the
specialist's interpreter (Python >= 3.11); the adapter itself runs on Python >= 3.10 for
`--replay` and environment refusals. It never imports `theforge`; it drives only the
specialist's **public seams**:

| Capability | Action | Public seam |
| --- | --- | --- |
| `data.scan` | `analyze` | `forge_doctor_data.core.forger.accept_request` — `{"kind": "scan", "path": …}` → `forge-contracts/1` `HandoffBundle` |
| `data.verify` | `verify` | `forge_doctor_data.core.conformance.check_conformance` — schema + strict model decode + version negotiation of any `forge-contracts/1` payload |

The scan runs over the staged workspace root (`stage/`): the adapter hands the specialist a
copy of the workspace, never the original. The emitted `HandoffBundle` is stored verbatim
(canonical JSON) as the `native/handoff.json` artifact and translated into the Evidence Bus:
findings → `Finding` + one `Evidence` each, capabilities → observed evidence, remediation
plans → `proposed` evidence, `UnknownFact`s → `unknowns`, and the platform graph stays
inside the artifact (reference semantics, never re-modelled inline).

## Install

```bash
python -m pip install -e path/to/forge-doctor-data -e path/to/adapters/doctordata
```

## Record the native surface

`describe` derives the manifest from `native_surface.json`, a recorded snapshot of the
public seams (which boundary callables exist, the accepted request kinds, the contract
version). Re-record it in the specialist interpreter:

```bash
python -m theforge_doctordata.record           # rewrite native_surface.json
python -m theforge_doctordata.record --check   # exit 1 when the installed surface drifts
```

## Replay

`--replay <scenario>` serves `describe`/`health`/`execute` from a recorded scenario without
the specialist: `environment.json`, `health.json` and one `<capability>.<action>.json`
(the bridge document) or `<capability>.<action>.error.json` per action.
