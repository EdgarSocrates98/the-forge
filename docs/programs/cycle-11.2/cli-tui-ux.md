# Cycle 11.2 — CLI/TUI/UX (P1-001 + P2-004)

Escopo: estado real do TUI no-args e superfícies de UX em
`forge-cli@origin/main = 6ea2e79` + o que está in-flight no working tree
(feat/c11-2-bc, workers B/C).

## Comandos executados

```text
forge-cli --help          # real, instalado via npm link → theforge-cli@0.2.0
forge-cli --version       # real
npx vitest run tests/menu.test.ts tests/wizard.test.ts tests/tui-repos.test.ts
sed -n 1,150p src/menu.ts
```

## O que existe em main

- **Menu guiado no-args**: `shouldShowMenu` só em TTY interativo, sem
  posicionais/flags/`--plan`/`--help`/não-interativo — `src/menu.ts:52`.
  10 ações (`MENU_ITEMS`): install, wizard, update, reinstall, repair,
  versions, status, uninstall, doctor, exit — hints PT-BR via
  `S.menu*`.
- **Modo registry filtrado**: `menuItemsFor` reduz a 6 ações suportadas
  pelo engine PyPI (install/update/reinstall/uninstall/status/exit) —
  clone/versions/git-only fora. `status` mapeia para `registry` list.
- **Tradução menu→posicionais**: `applyMenu` sem efeitos colaterais além
  das perguntas — testável sem TTY; `actionToPositionals` mapeia repair→
  `doctor`+`--fix`, wizard→`wizard`, etc.
- **Prompts**: `@clack/prompts` (select/multiselect com busca —
  tui-repos.test.ts prova filtro por teclas simuladas), spinner,
  note/outro, `exitCancelled` em isCancel.
- **Testes**: menu.test.ts 19 · wizard.test.ts 15 · tui-repos.test.ts 3 —
  todos verdes no run de main (909 testes totais).

## O que NÃO existe em main (verificado real)

- `forge-cli --version` sozinho **falha**: `Option '--version <value>'
  argument missing` — `--version` é flag de pin de Forja, não de versão
  do CLI. Saída real capturada nesta máquina.
- Sem `--no-color`/`NO_COLOR`: banner ANSI e clack sempre coloridos.
- Sem `registry lock` (verb em-flight).

## In-flight (feat/c11-2-bc, uncommitted — workers B/C)

Diff ativo no working tree: `cli-args.ts` adiciona `--version`
disambiguado (sozinho → `CLI_VERSION`; com valor → pin), `--no-color` +
`NO_COLOR` honrado globalmente (`setColorEnabled`), `--out` para
`registry lock`; `index.ts` despacha `registry lock`/`registry install`.
Estado em captura: uncommitted, não mergeado.

## Gaps P2-004 restantes

- Screen-reader/leitor de tela no TUI: nunca verificado (manual-needed).
- i18n: strings PT-BR hardcoded em `ui/strings.ts` — sem en/es.
- Erros nomeados cresceram (portal codes, lock kinds), cobertura parcial.

## Veredito

FIXED_UNVERIFIED — menu guiado existe e é testado; polish (no-color,
--version, a11y real) em-flight ou open.
