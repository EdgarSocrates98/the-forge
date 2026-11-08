# CI verification

Current canonical CI evidence: The Forge run `42507344696`, Code Atlas run
`42464291258`, Product Forge run `42462885912` and Portal run `42505763000` are
green on their current `main` heads. Forge Lens' latest recorded main run is
`42448963206`.

Agent Bridge PR #14 merged as `1b8ac82df64cdd53e7ff17324d325e82d8dbaff9`.
Run `42508735903` completed with both `core` and `security` green, so P0-01 is
`VERIFIED`.

Local CI-equivalent gates are recorded in `evidence-manifest.json`. A skipped
conditional job is not interpreted as a pass. Provider homologation run
`42471705402` failed during `setup-uv` with HTTP 504 before any test step; it is
recorded as infrastructure noise, not provider success.
