# Performance: benchmark, baseline e budgets

Medir antes de otimizar: o baseline foi registrado antes do cache de fingerprints e da nova seleção de contexto ([ADR 0015](adr/0015-context-intelligence.md)), e os budgets de regressão são derivados só dele.

## Procedimento
`scripts/bench/run_bench.py`, só stdlib, fora da suíte offline e do gate de PR. Precisa do pacote instalado no ambiente (`pip install -e .`).

```bash
python scripts/bench/run_bench.py [--quick] [--runs N] [--out PATH] [--check scripts/bench/budgets.json]
python scripts/bench/run_bench.py --results PATH --check scripts/bench/budgets.json
python scripts/bench/run_bench.py --budgets-from scripts/bench/baseline.json [--factor F] [--out PATH]
```

- Repetições: 10 por medição (padrão), 3 com `--quick`, ou `--runs N`. Cada medição reporta mediana e p90 (nearest rank) com `time.perf_counter_ns`; preparação (diretórios de cache novos, aquecimento) nunca é cronometrada.
- Isolamento: tudo roda num diretório temporário — workspaces sintéticos, configuração de providers e caches —, com `THEFORGE_CONFIG_DIR` e `THEFORGE_CACHE_DIR` apontando para lá. A configuração e os caches do usuário não são lidos nem tocados. A única outra saída é `--out`.
- Workspaces sintéticos: `scripts/bench/workspace.py`, determinístico (semente fixa): rotação de `.md`, `.txt`, `.py` e `.json`, tamanhos fixos de 256, 1 024 e 4 096 bytes, 100 arquivos por diretório, ASCII com LF; nenhum nome de segredo e nenhum diretório ignorado pela varredura.
- Saída: `{"schema": "theforge-bench/v1", "origin": {machine, os, python, date, forge_version, git_head, git_dirty}, "results": {nome: {median_ms, p90_ms, runs}}}`.
- `--check`: compara cada mediana com `budgets.json` (`{nome: {budget_ms, baseline_ms, factor, origin}}`), imprime cada regressão e cada medição sem budget (`no budget`) e sai com código 1 se houver regressão. Nunca roda na suíte padrão: uma regressão é reportada, não bloqueia o gate.

| Medição | O que mede |
|---|---|
| `cli_startup` | `python -m theforge --help` em subprocesso |
| `registry_cold` / `registry_warm` | registry com o eco e os providers de fixture, cache vazio e depois populado |
| `scan_1k` / `scan_10k` | varredura de workspaces sintéticos de 1 000 e 10 000 arquivos |
| `routing_10k` | routing sobre a varredura de 10 000 arquivos |
| `context_1k_cold` / `context_1k_warm`, `context_10k_cold` / `context_10k_warm` | `build_context_pack` com o perfil `balanced`, cache de fingerprints frio (desligado) e quente (populado) |
| `persist_run` | gravação de `task`, `routing`, `context`, `result`, `telemetry` e `receipt` de um run real com o eco |

## Baseline
Arquivo: `scripts/bench/baseline.json` (gravado no commit `f1df8a0`; medido em `d77ba5f`). Medido antes do cache de fingerprints: nesse ponto `warm` só difere de `cold` por uma chamada de aquecimento não cronometrada, então as duas variantes medem o mesmo trabalho e a diferença entre elas é ruído.

Origem:

| Campo | Valor |
|---|---|
| máquina | AMD64; 6 CPUs; Intel64 Family 6 Model 158 Stepping 13, GenuineIntel |
| sistema operacional | Windows-10-10.0.26300-SP0 (Windows 11) |
| Python | CPython 3.11.15 |
| data | 2026-10-04T10:54:15Z |
| versão de The Forge | 0.1.0 |
| commit medido | `d77ba5f2f124a7d2b8d17a61f79d5f0fc3454c5b` (worktree limpo) |
| repetições | 10 por medição |

| Medição | Mediana (ms) | p90 (ms) |
|---|---:|---:|
| `cli_startup` | 1 317,417 | 1 807,333 |
| `registry_cold` | 962,393 | 1 674,901 |
| `registry_warm` | 10,118 | 16,142 |
| `scan_1k` | 898,238 | 1 578,824 |
| `scan_10k` | 12 897,393 | 22 243,237 |
| `routing_10k` | 594,259 | 668,430 |
| `context_1k_cold` | 478,228 | 984,354 |
| `context_1k_warm` | 411,964 | 493,704 |
| `context_10k_cold` | 3 348,102 | 4 065,909 |
| `context_10k_warm` | 3 817,534 | 6 696,873 |
| `persist_run` | 14,741 | 33,107 |

## Budgets de regressão
Arquivo: `scripts/bench/budgets.json`. Regra (gerada por `--budgets-from`): `budget_ms` = fator × mediana do baseline da mesma medição, com fator inicial 1,5; cada entrada registra `budget_ms`, `baseline_ms`, `factor` e `origin` (o baseline acima). Os budgets valem para a máquina de origem: em outra máquina, meça um baseline próprio antes de comparar. Mudar um budget exige um novo baseline registrado com origem.

| Medição | Baseline (ms) | Fator | Budget (ms) | Remedição final (ms) |
|---|---:|---:|---:|---:|
| `cli_startup` | 1 317,417 | 1,5 | 1 976,125 | 302,389 |
| `registry_cold` | 962,393 | 1,5 | 1 443,590 | 335,892 |
| `registry_warm` | 10,118 | 1,5 | 15,177 | 5,307 |
| `scan_1k` | 898,238 | 1,5 | 1 347,357 | 649,580 |
| `scan_10k` | 12 897,393 | 1,5 | 19 346,090 | 5 654,459 |
| `routing_10k` | 594,259 | 1,5 | 891,389 | 391,325 |
| `context_1k_cold` | 478,228 | 1,5 | 717,342 | 61,114 |
| `context_1k_warm` | 411,964 | 1,5 | 617,946 | 92,977 |
| `context_10k_cold` | 3 348,102 | 1,5 | 5 022,153 | 196,159 |
| `context_10k_warm` | 3 817,534 | 1,5 | 5 726,301 | 196,742 |
| `persist_run` | 14,741 | 1,5 | 22,111 | 10,665 |

Origem da remedição final (`scripts/bench/final.json`, `--quick`, 3 repetições): AMD64; 6 cpus; Intel64 Family 6 Model 158 Stepping 13, GenuineIntel; Windows-10-10.0.26300-SP0; CPython 3.11.15; 2026-10-04T15:33:14Z; The Forge 0.1.0; commit `68eb7ef` com worktree sujo (`git_dirty: true`; o commit seguinte, `f637e2a`, só acrescenta `budgets.json` e `final.json`). Comparação contra os budgets: 0 regressões em 11 medições. Uma remedição anterior com 10 repetições, feita com a máquina carregada (pouca memória livre e outro processo ativo), acusou `registry_warm` (28,1 ms) e `scan_1k` (1 481,6 ms) acima do budget; a repetição em máquina quieta não as reproduziu, então foram tratadas como ruído. O contexto frio ficou ~8× (1k) e ~17× (10k) mais rápido pela nova seleção limitada por perfil (medianas `context_*_cold`); no contexto quente o cache evita reler os 64 arquivos selecionados (`files_hashed=0`, `cache_hits=64`), mas não reduz o tempo de parede nesse tamanho, pois carregar e gravar o JSON do cache custa tanto ou mais que reler ~125 KB.

## Custos fora do benchmark
- Git: quando o workspace está dentro de um repositório, cada `ask` faz 5 processos `git` com orçamento total de 5 s ([ADR 0016](adr/0016-git-read-only-signals.md)); observado em ~0,7–1,3 s por run nos testes, nesta máquina. O benchmark de contexto chama `build_context_pack` sem git.
- Negociação: até 2 chamadas `execute` extras por run, cada uma com o timeout inteiro do perfil.
- Reverificação: proporcional ao nível do perfil (nenhuma em `economy`, todos os itens em `max`), sempre sem cache.
