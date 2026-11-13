# Known Limitations — 2026-11-13T12:04:45+00:00

- **api-sentinel-forge PyPI**: trusted publisher not registered on
  pypi.org — publish run fails `invalid-publisher` until owner registers
  (owner: EdgarSocrates98, workflow publish-pypi.yml, env release).
- **forge-lens dependabot PRs**: 12 open — dependency hygiene, out of
  program scope.
- Federation Lake Formation scenario returns `partial` honestly when no
  artifact input is provided — by design (no fabricated findings).
- Perf baseline medians are single-host measurements, not SLAs.
