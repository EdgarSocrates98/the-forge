# Runtime path audit (Cycle 12 §2.4)

Todos os caminhos de runtime resolvidos sem checkout (ordem canônica):

1. **Env override nomeada** (`SPARKFORGE_AWS_EVALS`,
   `SPARKFORGE_AZURE_EVALS`, `FORGE_CLI_HOME`, `FORGE_HOME_OVERRIDE`)
   — quebrada → recusa nomeando a var, nunca `[]` silencioso.
2. **cwd** (`knowledge/`, `evals/`) — workspace de uso.
3. **Checkout com marcador** (`pyproject.toml` ao lado) — impede ler
   `site-packages/knowledge` estranho.
4. **Packaged** (`_data/*` via `importlib.resources` + `as_file` +
   `ExitStack` — zipimport-safe; `Path(str(t))` só para âncora
   ausente, nunca para conteúdo).

Escritas recusam site-packages: `knowledge_new`/`golden_update` pedem
que `resolve()` prove fora-de-purelib (zipimport e unresolvable →
recusa nomeada). Run records vão para cwd do consumidor.

Registry: `~/.forge/installations/<id>.json` (canônico, bootstrap
smoke-antes-de-register) + `~/.forge-cli/forges/state.json`
(forge-cli registry; `_forge_cli_state()` honra `FORGE_CLI_HOME`) —
`specialists.collect()` faz dedup canônico-vence.

Gaps residuais por severidade: `baseline.md` §5.
