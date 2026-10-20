# Cycle 12.4 — Contrato de variáveis de ambiente e raízes

Dois namespaces coexistem por design. Não são aliases livres: respondem a
perguntas diferentes e têm donos diferentes.

## 1. Contrato de instalação — `<FORGE>_*` (dono: bootstrap / registry)

Escrito por `scripts/installkit/forge_bootstrap.py --persist-env` em
`~/.config/forjas/env.sh` (bloco gerenciado, XDG), e no registro de usuário
do Windows. Ciclo de vida: install/update/repair/uninstall.

```text
SPARK_FORGE_AWS_HOME           # source root (checkout) — só existe com checkout
SPARK_FORGE_AWS_INSTALL_ROOT   # install root (~/.forge/installs/<id>)
SPARK_FORGE_AWS_VENV           # runtime root (venv do install root)
SPARK_FORGE_AWS_PYTHON         # interpretador do venv
SPARK_FORGE_AWS_CLI            # executável real dentro do venv
SPARK_FORGE_AWS_LAUNCHER       # shim em ~/.forge/bin
```

Mesmo conjunto para `SPARK_FORGE_AZURE_*`, `API_FORGE_*`, `PLATFORM_FORGE_*`,
`FORGE_DOCTOR_API_*`, `FORGE_DOCTOR_DATA_*`, `THE_FORGE_*` (prefixo =
`forge_id` upper-snake, ver `env_prefix()` no bootstrap).

## 2. Overrides de recurso — `<FORGE sem underscore>_*` (dono: o pacote)

Opcionais, nunca escritos pelo instalador. Precedência em todos os Forges:
override → workspace/cwd → checkout (se houver) → dados empacotados no wheel.

| Variável | Recurso | Aliases aceitos |
|---|---|---|
| `SPARKFORGE_AWS_CATALOG` | rules catalog | `SPARKFORGE_CATALOG` (legado), `SPARK_FORGE_AWS_CATALOG` |
| `SPARKFORGE_AWS_KNOWLEDGE` | knowledge packs | `SPARKFORGE_KNOWLEDGE` (legado), `SPARK_FORGE_AWS_KNOWLEDGE` |
| `SPARKFORGE_AWS_EVALS` | eval suites | `SPARK_FORGE_AWS_EVALS` |
| `SPARKFORGE_AWS_FIXTURES` | dev fixtures | — |
| `SPARKFORGE_AZURE_CATALOG` | rules catalog | `SPARK_FORGE_AZURE_CATALOG` |
| `SPARKFORGE_AZURE_KNOWLEDGE` | knowledge packs | `SPARK_FORGE_AZURE_KNOWLEDGE` |

Depreciação: a forma `<FORGE>_<RES>` (do prefixo de install) é aceita como
alias para que um único prefixo mental baste; a forma documentada continua
sendo `SPARKFORGE_*`. Nenhuma instalação existente quebra: aliases são só
fallback de leitura, o nome canônico sempre vence.

## 3. Semântica de raiz (não usar HOME ambiguamente)

| Conceito | Valor concreto |
|---|---|
| Source root | checkout git; ausente em install wheel-only |
| Install root | `~/.forge/installs/<forge_id>` (ou `--install-dir`) |
| Runtime root | `<install_root>/.venv` |
| Config root | `$XDG_CONFIG_HOME/forjas/` (`env.sh`) |
| State root | `~/.forge/` (installations/, ledger, installs/) |
| Workspace root | cwd do projeto do usuário — recursos locais vencem |
| Cache root | por-forge (`.apiforge/`, `.sparkforge_*/`) |

`<FORGE>_HOME` = source root de um checkout — só é emitido quando existe um.
Em install `--dist` (PyPI) o manifesto registra `source.kind="pypi"` com
`installation_method="pypi-wheel"`, o contrato omite `<FORGE>_HOME` e o
pacote não depende desse path.

## 4. Segurança

- Nenhum valor secreto vai para `env.sh`, manifesto ou logs.
- `.env` de projeto não é tocado; templates só para chaves do componente
  efetivamente instalado.

Nota `--dist`: a porção *nome* do requirement é verificada contra
`forge.json.distribution` (PEP 503). Referências diretas `name @ URL` são
recusadas por default (`FORGE-INSTALL-DIST-URL`) e só passam com o flag
explícito `--allow-url` — o check cobre só o nome, o URL segue verbatim
para o pip, então a origem fica a critério do operador.
