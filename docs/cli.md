# CLI

`theforge` (alias `forge`). Todo subcomando aceita `--root <dir>` (padrão: diretório atual) e `--json`.

| Comando | Faz | Exit |
|---|---|---|
| `init` | cria `.forge/` (idempotente) | 0 |
| `doctor` | OS, Python, git, host, workspace, providers | 0 / 1 se algo `fail` |
| `status` | resumo do workspace | 0 |
| `registry list` | providers (usa cache) | 0 |
| `registry refresh` | re-`describe` de todos os providers | 0 |
| `registry show <id>` | manifest, argv e hash | 0 / 2 se desconhecido |
| `capabilities list [--provider id]` | capabilities declaradas | 0 |
| `capabilities search <q>` | busca em id, descrição e keywords | 0 |
| `providers health` | health de cada provider | 0 / 1 |
| `ask "<texto>" [--capability id] [--action a] [--profile economy\|balanced\|max] [--target path]... [--allow-unverified]` | roteia e executa | 0 / 2 / 3 / 4 / 5 |
| `explain <run_id>` | reconstrói a decisão e o resultado de um run | 0 / 2 |

## Exit codes gerais

| Código | Significado |
|---|---|
| 0 | sucesso (`ok` / `partial` em `ask`) |
| 1 | `doctor` / `providers health` com falha |
| 2 | uso inválido ou workspace não inicializado |
| 3 | `no_route` / `ambiguous` |
| 4 | `provider_failure` / `refused` |
| 5 | falha ao persistir o run |
| 70 | erro interno inesperado (sem traceback) |
| 130 | interrompido (Ctrl+C) |

Providers de projeto são sempre `unverified`: sem `--allow-unverified` aparecem como `untrusted` no registry e não são executados.
