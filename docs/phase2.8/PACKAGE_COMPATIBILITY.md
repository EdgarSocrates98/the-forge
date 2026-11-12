# Package Compatibility

## Distribution matrix

The isolated wheel matrix built and installed 12 Forge distributions on
Windows 11 / Python 3.14.6; every build, install and CLI `--help` check passed:

`api-forge`, `code-atlas-forge`, `data-sentinel-forge`, `forge-agent-bridge`,
`forge-doctor-api`, `forge-doctor-data`, `forge-lens`, `platform-forge`,
`product-forge`, `spark-forge-aws`, `spark-forge-azure`, and `the-forge`.

The installed federation lane additionally built and installed the standalone
`forge-obsidian` 0.1.1 wheel and exercised its vault functions through the
federated harness. Product Forge's wheel also retains its bundled neutral
module; no Product Forge dependency was added to the standalone package.

The audit preserved optional Obsidian integration, offline operation, existing
CLI names, and no new mandatory flags. Cross-platform CI remains the authority
for the supported Python/OS matrix; this local Windows matrix is a reproducible
distribution smoke test, not a substitute for every CI runner.

Forge Portal's locked Angular toolchain was refreshed within the existing
22.2.x line. `npm ci`, `npm audit --audit-level=high`, the portable CLI tests,
installer tests, and Angular production build all passed; the final audit
reported zero vulnerabilities.

