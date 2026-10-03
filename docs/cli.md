# CLI

`theforge` (alias `forge`). Todo subcomando aceita `--root <dir>` (padrão: diretório atual) e `--json`, sempre **depois** do subcomando final: `theforge registry list --json`, `theforge init --root X`. Colocá-los antes (`theforge --root X init`) não funciona.

| Comando | Faz | Exit |
|---|---|---|
| `init` | cria `.forge/` (idempotente); remove o cache legado `.forge/registry` com aviso | 0 |
| `doctor` | OS, Python, git, host, workspace, providers | 0 / 1 só se algum check for `fail` (Python < 3.11, `.forge` sem escrita, provider builtin não saudável, `providers.toml` inválido); provider não builtin não saudável e workspace não inicializado são `warn` (exit 0) |
| `status` | resumo do workspace, incluindo os providers com cache | 0 |
| `registry list` | providers (usa o cache do usuário) | 0 |
| `registry refresh` | re-`describe` de todos os providers; remove o cache legado `.forge/registry` com aviso | 0 |
| `registry show <id>` | manifest, argv e hash | 0 / 2 se desconhecido |
| `capabilities list [--provider id]` | capabilities declaradas, com aliases, depreciação (`replaced_by`) e `declared_by`; aviso em stderr para cada depreciada | 0 |
| `capabilities search <q>` | busca em id, aliases, descrição e keywords | 0 |
| `providers health` | health de cada provider | 0 / 1 |
| `ask "<texto>" [--capability id] [--action a] [--profile economy\|balanced\|max] [--target path]... [--allow-unverified] [--approve CAPABILITY]...` | roteia, avalia a policy e executa | 0 / 2 / 3 / 4 / 5 |
| `explain <run_id>` | reconstrói a decisão, o risco e o resultado de um run | 0 / 2 |

## Exit codes gerais

| Código | Significado |
|---|---|
| 0 | sucesso (`ok` / `partial` em `ask`) |
| 1 | `doctor` / `providers health` com falha |
| 2 | uso inválido ou workspace não inicializado |
| 3 | `no_route` / `ambiguous` |
| 4 | `provider_failure` / `refused` (inclusive recusa de policy) |
| 5 | falha ao persistir o run |
| 70 | erro interno inesperado (sem traceback) |
| 130 | interrompido (Ctrl+C) |

## Trust e `--allow-unverified`
Providers de projeto são sempre `unverified`: um `trust` maior em `.forge/config/providers.toml` é rebaixado com aviso. Sem `--allow-unverified`, eles aparecem como `untrusted` no registry e não são executados. Com a flag, entram no routing, mas `local_mutation` continua pedindo aprovação. Semântica completa dos níveis em [security.md](security.md#níveis-de-trust) e [ADR 0010](adr/0010-policy-model.md).

## Aprovação (`--approve`)
Antes de executar, `ask` avalia a policy do `operation_class` declarado pela capability selecionada:

- `allow`: executa.
- `ask` sem aprovação: não executa; sai com exit 4, código `FORGE-POLICY-APPROVAL-REQUIRED` e `Unlock: --approve <capability>`. Repita o comando com `--approve <capability>` para executar; o run registra `approved: yes`.
- `deny`: não executa; exit 4 com `FORGE-POLICY-DENIED`. `--approve` não desbloqueia (por padrão, `destructive` é sempre `deny`).

`--approve` é repetível e vale só para a capability nomeada. As regras padrão e os arquivos `policy.toml` estão em [security.md](security.md#policy-e-risco).

## `explain`
Além de task, candidatos (cada um com sinais, `rank` e `state`: `supported`, `heuristic` ou `unresolved`), seleção, confiança e fallbacks, `explain` mostra o artefato `risk`:

```
Risk:        local_mutation (source: provider_declaration)
Policy:      allow   rule: default.local_mutation.local   approved: yes
Dimensions:  read_only=no local_mutation=yes external_read=no external_mutation=no destructive=no credentials=unknown cross_account=unknown
```

Quando a decisão foi `ask` sem aprovação, a linha `Policy` termina com `unlock: --approve <capability>`. Runs sem artefato `risk` (anteriores ao ciclo 2, ou que pararam antes de selecionar um provider) mostram `Risk:        not recorded`.

## Variáveis de ambiente
| Variável | Efeito |
|---|---|
| `THEFORGE_CONFIG_DIR` | diretório de configuração do usuário (`providers.toml`, `policy.toml`) |
| `THEFORGE_CACHE_DIR` | diretório de cache do usuário (cache do registry); ver [ADR 0009](adr/0009-registry-cache-location.md) |
