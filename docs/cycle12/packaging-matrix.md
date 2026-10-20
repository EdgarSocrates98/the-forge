# Packaging matrix (Cycle 12 §2.4)

Matriz real de artefatos construídos (não declarados) — `baseline.md` §2
tem SHAs/tamanhos; aqui o formato:

| Forja | dist PyPI | wheel | _data/launcher |
|---|---|---|---|
| the-forge | `theforge-core` | sim | registry `~/.forge` |
| spark-forge-aws | `sparkforge-aws` | sim | `evals_data` + bundle |
| spark-forge-azure | `sparkforge-azure` | sim | `_data/evals` |
| api-forge | `apiforge-af` | sim | `_data/{knowledge,evals,tests}` |
| platform-forge | `platformforge` | sim | `platformforge/data/*` |
| forge-doctor-api | `forge-doctor-api` | sim | `_data/labs` |
| forge-doctor-data | `forge-doctor-data` | sim | `_data/{labs,golden}` |
| forge-cli | npm `theforge-cli` 0.2.2 | tsup bundle | `~/.forge-cli/bin` shims |
| forge-portal | `forge-portal-app` 1.0.0 | dist+vendor | `portal_assets` ×7 |

Instalação: `forge-cli install` → PyPI+venv (registry-first, §7.3);
`forge_bootstrap.py --dist` → PEP 503 name check + `--allow-url` +
redação de userinfo; wheel-first nos `install.sh|ps1` (editable só
opt-in). Update: `-U` preserva origem (extras + URL spec); `--to` em
direct reference (`@`) recusa origin swap nomeado — inclui `file://`.
