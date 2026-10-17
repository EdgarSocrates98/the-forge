# Cycle 11.2 — plan/dry-run purity (P0-002)

Escopo: `tests/plan-purity.test.ts` em `forge-cli@origin/main = 6ea2e79`
(pós-#29). Prova por hash: snapshot SHA-256 da árvore `FORGE_CLI_HOME` +
workspace antes/depois de cada comando — divergência = mutação oculta.

## Comandos executados

```text
npx vitest run tests/plan-purity.test.ts   # worktree /tmp/forge-cli-main @ origin/main
git show origin/main:src/cmd/registry.ts   # leitura de runRegistryPin/ignoredRegistryFlags
```

Saída real (2026-10-17):

```text
✓ tests/plan-purity.test.ts (18 tests) 2767ms
```

## Matriz — coberto (18/18 verde)

| Grupo | Cenário |
|---|---|
| registry plan/check (6) | `install --plan`, `update --check`, `update --plan`, `reinstall --check`, `rollback --check`, `uninstall` não-TTY sem `--yes` (emite `needsYes`, remove nada) |
| consultas read-only (12) | `registry` (list), `status`, `list`, `mcp --verify` (probe mockado), `hosts plan`, `hosts list`, `doctor`, `heal --plan`, `update --check` (git), `recover`, `env plan`, `uninstall` (git) não-TTY |

Mecanismo: `resolveRelease.ephemeral` — plan/check não escrevem cache
PyPI, venv, receipt ou state (confirmado pelo hash idêntico, não por
inspeção de código).

## Ainda aberto (honesto)

- **`pin`/`unpin` não têm modo `--plan`**: `runRegistryPin`
  (src/cmd/registry.ts) grava `state.forges[name].pinned` via
  `saveForgeState` incondicionalmente — sem ramo `cli.plan` e `--plan`
  não consta em `REGISTRY_IGNORED_FLAGS`, ou seja, nem warning é
  emitido. Encontrado via portal (forge-portal#32): o backend passou a
  derivar o preview offline justamente porque o verbo muta. Segue como
  gap real em main.
- `registry lock` (verbo novo, in-flight em feat/c11-2-bc) e `hosts
  register --yes` são mutações por desenho — fora do contrato de pureza,
  mas ainda sem cenário próprio.
- `mcp --verify` é coberto com probe **mockado** — a pureza do handshake
  real depende do server remoto não escrever em home (fora do escopo).

## Veredito

VERIFIED para o contrato "consulta/plan/check não muta" nos 18 cenários;
OPEN o sub-gap `pin/unpin --plan` (mutação silenciosa sem flag honrada
nem avisada).

## Risco residual

Usuário/script que assuma `pin --plan` como dry-run muta `state.json`
sem aviso. Portal já contorna; CLI segue devendo o fix.
