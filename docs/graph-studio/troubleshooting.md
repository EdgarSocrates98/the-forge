# Troubleshooting

| Symptom | Cause → fix |
|---|---|
| `*-GRAPH-NO-*` refusal | engine has no graph → run its build/index verb |
| `FORGE-GRAPH-STUDIO-DISABLED` | declined at install → reinstall with `graph-studio` |
| browser didn't open | remote/headless → `--no-browser` + port-forward |
| federated view missing a provider | check `notes[]` — refused/timed-out providers are named |
| truncated node list | `--limit` reached; raise it or filter |
