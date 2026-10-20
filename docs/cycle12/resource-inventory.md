# Resource inventory (Cycle 12 §2.4)

Recursos de runtime empacotados por Forja (force-include → resolver):

- **the-forge**: `forge-knowledge/*.json` (bootstrap metadata),
  `forge/InstallationManifest/v1` registry `~/.forge/installations/`.
- **spark-forge-aws**: `evals_data/` (evals/agentic), `integrate/bundle`
  (playbook/surface/goldset/catalog) — resolver `evals/paths.py`
  (env `SPARKFORGE_AWS_EVALS` → cwd → repo-marker → packaged).
- **spark-forge-azure**: `_data/evals` via `group_dir()`; env
  `SPARKFORGE_AZURE_EVALS`/`SPARK_FORGE_AZURE_EVALS`.
- **api-forge**: `_data/{knowledge,evals,tests/fixtures}`,
  `host_assets/{agents,skills,AGENT_PROTOCOL.md}`, `portal_assets/`.
- **platform-forge**: `platformforge/data/{rules,knowledge,contracts,
  evals}` via `data_path()` (as_file+ExitStack, zipimport-safe).
- **forge-doctor-api**: `_data/labs` via `lab/packaged.py`
  (allowlisted importlib boundary).
- **forge-doctor-data**: `_data/{labs,golden,knowledge}` via
  `_packaged_dir` (âncora ausente → Path inexistente, nunca raise).
- **forge-cli**: `~/.forge-cli/{forges,bin,cache}` — venvs, launchers
  (shims POSIX/.cmd), wheel cache, `state.json` registry.
- **forge-portal**: `portal_assets/` vendored ×7 + manifest
  `forge/PortalAssets/1` (sha256 por arquivo).

Prova: `test_artifact_contents.py` por repo constrói a wheel real e
assere presença arquivo-a-arquivo (zero skip com `build>=1.0` nos dev
extras instalados). Detalhe por arquivo: `baseline.md` §2-3.
