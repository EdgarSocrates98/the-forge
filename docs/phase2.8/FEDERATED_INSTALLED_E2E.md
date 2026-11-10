# Federated Installed E2E

## Source conformance

Command:

```text
PYTHONPATH=src python scripts/phase2_federated_obsidian_e2e.py --repos-root <cycle2.8-clones>
```

Result: PASS. Four specialist notes were generated, validated through the
body-free reference projection, exported/reimported, hash-checked, related in
Code Atlas, traced in Forge Lens, authorized in Agent Bridge, and exercised
through manual conflict detection. Vault writes were temporary and fixture
only.

## Installed-package conformance

Fresh wheels from the audited clones were installed in an isolated Python 3.12
venv, including the standalone `forge-obsidian` wheel. The harness was invoked
with `PYTHONPATH` empty and `--installed`, so no checkout source path was added.

Result receipt:

```json
{
  "notes_exported": 4,
  "notes_roundtripped": 4,
  "note_contracts_validated": 4,
  "atlas_relations": 1,
  "lens_spans": 1,
  "bridge_authorized": true,
  "manual_conflict_detected": true,
  "cloud_access": false,
  "body_persisted_in_federation_outputs": false
}
```

This is installed-package conformance, not production provider certification.
Real AWS/Azure credentials, real vault authorization, disk-full injection and
provider outages remain external lanes and are not marked PASS.

