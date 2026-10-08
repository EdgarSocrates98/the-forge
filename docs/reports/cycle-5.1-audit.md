# Cycle 5.1 — auditoria da main (Fase 0)

Auditado em 2026-10-08 a partir da `main` real — não de relatórios anteriores.
Os SHAs/versões abaixo foram medidos, não assumidos.

## Estado do repositório

```text
The Forge HEAD:        c70757f9e31f6ff9e7bb3f9d1c33d9996253c4f6 (main)
package:               0.3.0
Python:                >= 3.11
runtime dependencies:  0
contracts exportados:  67  (+39 fechados/core-only)
schemas:               67  (paridade 1:1 com os exportados)
test files:            128 → 129 (este ciclo adiciona reality/staleness)
testes coletados:      4300 (modo offline, sem slow/real_provider)
docs raiz:             31
ADRs:                  51
TODO/FIXME no core:    2 (ambos templates de scaffold — placeholders gerados)
```

## Gates locais (rodados nesta branch)

| Gate | Status | Evidence |
|---|---|---|
| Ruff | green | `ruff check .` — 0 erros |
| Ruff format | green | `ruff format --check .` — 610 arquivos já formatados |
| mypy strict | green | 0 issues em 201 arquivos |
| schemas | green | `python -m theforge.contracts.schema schemas` → `git diff` limpo |
| unit tests | green | suíte offline completa |
| integration tests | green | incluídos na suíte offline |
| offline suite | green | `pytest -m "not slow and not real_provider"` — exit 0 |
| Windows compatibility | green (local) | esta máquina (win32); matriz remota bloqueada |
| Linux compatibility | unverified local | depende do CI remoto — REMOTE_BLOCKED |
| CLI smoke | green | `theforge --version` → `theforge 0.3.0` |
| package build | deferred | gate `slow`/`fresh_install` — ver relatório final |
| docs consistency | green | `test_docs_consistency.py` incluso na suíte |

## Realidade dos specialists (manifest: `docs/reality/specialist-reality.json`)

Coletado por `scripts/reality/collect.py --fetch` em 2026-10-08 — SHAs vindos de
`git` ao vivo, surfaces de `record --check` ao vivo, snapshots do sha256 dos
arquivos empacotados.

| Specialist | Instalado (checkout) | origin/main | Relação | Snapshot drift | Status |
|---|---|---|---|---|---|
| spark-forge-aws | `828827d7` (feat/upstream-facts-v1) | `ab7f02e2` | diverged | none | snapshot_fresh_install_diverged |
| api-forge | `1745f872` (detached = main local) | `07459a20` | diverged | none | snapshot_fresh_install_diverged |
| forge-doctor-data | `3a8d7a56` (main) | `3a8d7a56` | same | none | fresh |
| forge-doctor-api | `035b6358` (main local, +2/−1) | `e916a110` | diverged | none | snapshot_fresh_install_diverged |

Leitura honesta:

- Os **snapshots empacotados batem 1:1 com as surfaces vivas** dos interpretadores
  instalados (drift `none` nos quatro) — o replay dos adapters é fiel.
- Mas **três dos quatro venvs não rodam `origin/main`**: spark roda a feature
  branch `upstream-facts`, api-forge e doctor-api rodam mains locais à frente/
  divergentes do publicado. Versões de pacote e compatibilidade real são coisas
  distintas — exatamente o que o Cycle 5.1 veio medir.
- doctor-data é o único fully `fresh` (instalado == publicado).

## upstream-facts (§13)

Resposta medida em 2026-10-08: **o intake entrou na `origin/main` publicada dos
dois lados.** A afirmação histórica "upstream-facts intake only on feature
branch" está obsoleta.

- `spark-forge-aws` `origin/main` (`ab7f02e2`, release v0.5.0) já contém
  `sparkforge_aws/adapters/upstream.py` + flag `--upstream` + tools — validando
  `sparkforge_aws/upstream-facts/v1` (o schema foi renomeado junto com o pacote
  `sparkforge` → `sparkforge_aws`).
- `api-forge` `origin/main` (`07459a2`, release v0.1.0) contém o intake
  `apiforge/upstream-facts/v1` (`--upstream` no `analyze`).

**Drift real encontrado e corrigido neste ciclo:** o adapter
`theforge_sparkforge_aws` emitia `sparkforge/upstream-facts/v1` hardcoded — o
nome *pré-rename*. Coincidiu com o intake da feature branch instalada no venv
(`828827d`), mascarando a divergência: contra a main publicada o documento seria
recusado. Corrigido emitindo o `UPSTREAM_SCHEMA` que o intake **instalado**
declara (`native_pkg.upstream_schema()`), com fallback ao nome legado — o
adapter agora segue o especialista em vez de presumir.

Limitação residual honesta: 3 dos 4 venvs rodam checkouts divergentes de
`origin/main` (tabela acima). O replay offline continua coberto por fixtures
gravadas; a prova `real_provider` local mede a realidade *instalada*.

## CI remoto

`REMOTE_BLOCKED` — GitHub Actions sem quota (run 37725616843 criou os jobs sem
executar steps). Não confundir com `REMOTE_FAILED`: nenhum resultado remoto foi
falsificado ou inferido neste ciclo.
