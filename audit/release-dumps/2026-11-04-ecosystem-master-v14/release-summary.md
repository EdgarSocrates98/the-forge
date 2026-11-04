# Release diagnostic summary

Generated: 2026-11-04T16:53:30Z \xb7 mode: `safe`

Safety: no env var values, cookies, tokens, Authorization headers or SSH keys are collected; user paths appear as `<HOME>`; secret-shaped strings appear as `<REDACTED>`.

## Inventory \u2014 `forge/ReleaseInventory/1`

- repository: `the-forge` @ `09886b14c7f5` (branch `main`, dirty=False)
- tag on HEAD: `none` \xb7 latest tag: `v0.7.2`
- package: `theforge-core` 0.7.2 (python)
- workflow: `.github/workflows/publish-pypi.yml`
- published_version: `unresolved` \u2014 registry lookups are outside the offline boundary; compare `commit.sha` and `package.version` against the registry record externally

## Vendor integrity \u2014 `forge/VendorIntegrity/1`

Forges dir: `E:\projetos\FORJAS` \xb7 8/8 checkouts \xb7 8 OK \xb7 0 drifted

| forge | status | files | missing | extra | mismatched |
|---|---|---|---|---|---|
| the-forge | OK | 66 | 0 | 0 | 0 |
| spark-forge-aws | OK | 66 | 0 | 0 | 0 |
| spark-forge-azure | OK | 66 | 0 | 0 | 0 |
| api-forge | OK | 66 | 0 | 0 | 0 |
| platform-forge | OK | 66 | 0 | 0 | 0 |
| forge-doctor-data | OK | 66 | 0 | 0 | 0 |
| forge-doctor-api | OK | 66 | 0 | 0 | 0 |
| product-forge | OK | 66 | 0 | 0 | 0 |

## npm pack \u2014 `forge/NpmPackManifest/1`

- dir: `E:\projetos\FORJAS\forge-cli`
- package: `theforge-cli` 0.4.1 (integrity `sha512-xPatcC2DmFBWw5BeBMPV06k+hy7zO9qINwMDS/E7cXDZSB2GFhBX8xRFOxHTF25xHFAh0RfrFqqxcjaZpJUZQg==`)
- members: 11 files, 1150655 bytes unpacked
- forbidden findings: 0
- status: OK

_`wheel-manifest.json` not collected in this run._

## Integrity

`checksums.sha256` covers every emitted artifact in this directory.
