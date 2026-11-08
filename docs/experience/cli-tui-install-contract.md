# CLI, TTY/TUI e instalação — contrato do ecossistema

Os 14 projetos oficiais seguem o mesmo princípio de interação:

```text
comando nu em terminal real → superfície visual → plano → aprovação → aplicação → doctor
flags / pipe / CI            → saída determinística → JSON ou dry-run, sem prompts
```

## O que o operador pode esperar

- `install` sem flags, quando stdin **e** stdout são TTYs reais, abre o wizard
  visual do projeto. As escolhas usam setas, espaço, Enter e `q`/Esc para
  cancelar.
- O wizard mostra ambiente detectado, escopo, perfil, componentes, hosts e um
  plano derivado da instalação real antes de qualquer escrita.
- Cancelar antes da aprovação retorna `130` e não cria artefatos.
- Em pipe, CI ou redirecionamento, o comando nunca pede input. Use `--dry-run`
  para pré-visualização ou `--yes` para uma aplicação explicitamente aprovada.
- `--json` e os caminhos de automação mantêm stdout parseável; decoração visual
  é reservada para terminais humanos.

## Matriz de superfícies

Veja o artefato verificável em
[`audit/reports/cli-tui-install-matrix-2026-11-04.json`](../../audit/reports/cli-tui-install-matrix-2026-11-04.json).

`home+tui+wizard` significa que o CLI nu também abre uma home/dashboard
interativa e oferece um comando `tui` explícito. Todos os projetos de terminal
seguem esse contrato; o wizard continua sendo uma ação real dentro da home.
`forge-cli` usa `@clack/prompts`, enquanto os
projetos Python usam o UI kit stdlib canônico e suas cópias vendorizadas.

`forge-portal` mantém o navegador como superfície primária, mas agora também
oferece uma CLI portátil mínima: a home TUI, `wizard` para host/porta com
confirmação e `status` em JSON para CI. Ela não duplica o servidor Python nem
substitui a experiência Angular; apenas torna descoberta e inicialização
práticas em qualquer workspace.

Além do comando de cada projeto, todos os 14 repositórios publicam as três
entradas de instalação portável (`install.sh`, `install.windows.sh` e
`install.ps1`). Os projetos Python preservam seus contratos próprios de
bootstrap; `forge-cli` e `forge-portal` usam um plano Node comum com `--dry-run`
e `--no-link`, incluindo build e link opcional do comando local.

## Verificação

Na raiz de `the-forge`:

```powershell
python scripts/cli_install_matrix.py --check
```

O gate verifica os 14 repositórios, a presença da superfície declarada e a
evidência estática de TTY de entrada e saída, wizard visual, fallback de
automação e os três instaladores portáveis. Isso complementa — não substitui
— os testes de cada pacote e os smokes em terminal real. A auditoria segura de
instaladores usa `audit/tooling/run_installers.py`; shells ausentes aparecem
como `BLOCKED`, nunca como `PASS`.
