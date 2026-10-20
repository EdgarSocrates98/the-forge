# Compatibility matrix (Cycle 12 §2.4)

Canônico machine-readable: `../ecosystem-compatibility.json`
(component, version, scheme, distribution) — gateado por
`test_ecosystem_compat.py::test_declared_versions_match_project_files`
(zero versões fictícias; forge-portal alinhado a 1.0.0 na Rodada 13).

Contratos versionados:
- `forge/InstallationManifest/v1` (+ `installation_method`
  pypi-wheel|wheel|git-checkout).
- `forge/PortalAssets/1` (sha256 por arquivo, manifest vendored ×7,
  `--check` byte-parity no CI).
- `forge/PortalApi/1` (envelope servido por `<cli> portal`).
- `theforge/<Name>/v1` core contracts (schema regen por
  `python -m theforge.contracts.schema`).

Cross-repo: `_forge_cli_state()` descobre installs registry-first;
nomes forge-cli = forge_id 1:1 (catalog + state.json).
Python floor: >=3.10 nos especialistas, >=3.11 no the-forge —
vendored `forge_bootstrap.py` respeita `--config` por repo.
