# Specialist reality manifests

`specialist-reality.json` é a representação canônica e machine-readable da
realidade dos seis specialists, coletada de evidência viva (não de relatórios
antigos) por:

```bash
python scripts/reality/collect.py            # usa os refs locais de origin
python scripts/reality/collect.py --fetch    # git fetch em cada checkout antes
python scripts/reality/collect.py --check    # exit 1 se drifted/unverifiable/missing
```

Os interpretadores são resolvidos na mesma ordem do contrato dos testes reais:
`--python nome=caminho` > `THEFORGE_REAL_<NOME>_PYTHON` > a convenção de venvs
irmãos (`.venv-spark-aws`, `.venv-api`, `.venv-dd`, `.venv-da`). Ver
[real-providers.md](../real-providers.md).

## O que o manifest separa

Seguindo o Cycle 5.1, versões semânticas não provam compatibilidade. Cada
entrada registra camadas distintas:

```text
repository commit (o git do checkout instalado)
  != package version (a distribuição no venv)
  != runtime surface (o que o interpretador expõe ao vivo)
  != adapter snapshot (native_*.json commitado no repo)
```

Para cada specialist o manifest carrega: `commit_sha` do checkout que produz o
pacote instalado, `origin_main` do ref local (e `refs_fetched`), a relação de
ancestralidade `installed ↔ origin/main` (`same` | `ancestor` | `descendant` |
`diverged` | `unverifiable`), o sha256 do snapshot empacotado, o `recorded_at` e
a contagem de entradas, o resultado do `record --check` (`none` | `additive` |
`breaking` | `unverifiable`) e o `compatibility_status` de rollup:

| Status | Significado |
|---|---|
| `fresh` | snapshot corresponde à surface viva **e** o checkout instalado é `origin/main` |
| `snapshot_fresh_install_ahead` | snapshot corresponde à surface viva; instalado à frente de `origin/main` |
| `snapshot_fresh_install_diverged` | snapshot corresponde à surface viva; instalado diverge/atrasa `origin/main` |
| `drifted` | `record --check` classificou `breaking` — snapshot obsoleto |
| `unverifiable` | evidência insuficiente para classificar |
| `missing` | interpretador não configurado |

`additive`/`breaking`/`none` vêm diretamente do classificador de drift de cada
adapter (`python -m theforge_<adapter>.record --check`), não de heurísticas do
coletor.

## Por que isso existe

Adapters em modo replay usam o snapshot empacotado como a verdade da surface.
Se o especialista instalado evoluir (ou se o checkout instalado não for o
publicado), evidência derivada da surface fica *stale* — o manifest é a prova
datada de qual realidade cada snapshot descreve. A política de invalidação de
evidência por drift de surface está em
[ADR 0050](../adr/0050-execution-targets-remote-trust.md) e
[engineering-memory.md](../engineering-memory.md).
