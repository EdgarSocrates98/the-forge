# CLI/TUI e instalação — fechamento da rodada

Data: 2026-11-04  
Spec: `lf-0007`

## Resultado

`PASS` para o contrato de superfície dos 14 projetos. A matriz verificável está
em [`cli-tui-install-matrix-2026-11-04.json`](cli-tui-install-matrix-2026-11-04.json)
e é validada por `python scripts/cli_install_matrix.py --check`.

## Alteração efetiva

O Data Sentinel já possuía o wizard visual canônico, mas o callback Typer ainda
aceitava uma rota de prompts simples quando usado diretamente e verificava
apenas stdin. O caminho padrão agora exige stdin **e** stdout TTY e encaminha a
instalação sem flags ao wizard visual; pipe/CI continua sem prompts e requer
`--dry-run` ou `--yes`.

## Evidência

- `data-sentinel-forge`: `43 passed` em `tests/e2e/test_install_matrix.py`.
- `forge-cli`: `96 passed` nos testes focados de menu/TUI, pureza de plano,
  JSON e polimento; `npm run typecheck` passou.
- `the-forge`: teste do contrato com `2 passed`; `ruff check` passou.
- Matriz: 14/14 repositórios, sem erros estruturais.
- Dump: [`2026-11-04-ecosystem-v12`](../release-dumps/2026-11-04-ecosystem-v12/)
  gerado com `release_dumps.py all --check` (exit 0).

## Limitação ambiental conhecida

O suite completo do `forge-cli` não foi usado como gate desta alteração: o
processo Node do ambiente não resolveu `git` por PATH (`spawnSync git ENOENT`).
Com o diretório do Git explicitamente no PATH, os testes focados passaram. Isso
é uma limitação do runner, não uma falha observada na superfície TTY/TUI.

## Decisões de superfície

- Projetos Python usam o kit stdlib visual vendorizado e seus wizards.
- `forge-cli` usa `@clack/prompts`.
- `forge-portal` é conscientemente web-only; não declara TUI inexistente.
- Projetos com home/dashboard mantêm esse acesso no comando nu; os demais
  abrem o wizard ao menos no `install` nu.
