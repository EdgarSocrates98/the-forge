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
| `graph_build` | `build_capability_graph` sobre o descritor do workspace de 10 000 arquivos (Cycle 3, Wave W) |
| `graph_refresh_warm` | `refresh_intel` com snapshot válido — o caminho incremental que alimenta o grafo (seções frescas reusadas) |
| `plan_validate` | `check_plan` de um plano `pipeline` de 32 nós encadeados |
| `replay_verify` | `verify_run_hashes` de um run real com o eco |
| `explain_build` | `build_explain_report` de um run real com o eco |

O planner semântico não entra no SLA determinístico: é medido à parte pelo
`run_runs_bench.py` (métrica `semantic_calls` por caso — Wave P), nunca por budget
de latência aqui.

## Benchmark de economia de contexto

`scripts/bench/run_context_economy.py` (Cycle 3.1, fases 50–51): mede a premissa
do mesh — *o Doctor observa uma vez; os engenheiros recebem contexto delimitado
mais a evidência via handoff* — contra o baseline em que cada especialista relê
o workspace inteiro. Mesmo procedimento de isolamento do `run_bench` (diretório
temporário, `THEFORGE_CONFIG_DIR`/`THEFORGE_CACHE_DIR` próprios, workspace
sintético determinístico), fora da suíte offline.

```bash
python scripts/bench/run_context_economy.py [--runs N] [--out PATH]
```

- Braços: `direct` (Spark Forge AWS e API Forge com `targets: ["."]`) e `mesh`
  (`forge-doctor-data` sobre `["."]`, depois Spark e API delimitados aos seus
  domínios — `jobs`/`requirements.txt` e `api`/`src` — com `inputs` no doctor).
- Tudo roda em `specialist-replay` (terminologia em [real-providers.md](real-providers.md#níveis-de-real)): adapters reais em subprocesso, saída nativa gravada. O relatório declara `provider_mode`.
- Métricas observáveis por braço, lidas dos artifacts do run store: `provider_calls`, `files_scanned`, `context_files`, `context_bytes`, `handoff_bytes`, `evidence_bytes`, `wall_ms`, mais um breakdown por nó. `model_calls` e `provider_tokens` saem `null` — não observáveis offline, e desconhecido não é zero.
- Saída: `{"schema": "theforge-economy-bench/v1", "origin", "provider_mode", "arms", "comparison"}` — `comparison` traz `mesh_minus_direct` por métrica.
- Leitura honesta esperada: `files_scanned` cai pela metade (o scan inteiro acontece uma vez, não por especialista) e o contexto dos engenheiros colapsa para os arquivos do domínio; o `context_bytes` total pode **subir** quando a superfície de globs do doctor é mais larga que a soma dos especialistas — o ganho é uma varredura ampla única em vez de N.

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

## Benchmark de runs cross-forge (Ciclo 3, Wave P)

`scripts/bench/run_runs_bench.py` mede **runs inteiros** pela superfície real de orquestração — onde `run_bench.py` mede etapas internas sobre workspaces sintéticos, este mede o pipeline completo: os providers de fixture são subprocessos reais falando Forge Protocol v1 (o mesmo argv que o kit de conformidade certifica), então cada caso atravessa routing, avaliação de risco, contexto, transporte, verificação, persistência e receipt. Offline e sem credenciais por construção — os fixtures reexecutam comportamento declarado, que é o que um benchmark isolado precisa; se os SparkForge/APIForge *reais* se comportam igual é coberto pela suíte opt-in de providers reais ([docs/real-providers.md](real-providers.md)), uma medição diferente.

```bash
python scripts/bench/run_runs_bench.py [--quick] [--runs N] [--out PATH] [--check BUDGETS]
python scripts/bench/run_runs_bench.py --results PATH --check BUDGETS
python scripts/bench/run_runs_bench.py --budgets-from BASELINE [--factor F] [--out PATH]
```

Casos (cada um afirma o status esperado — um outcome errado falha o caso):

| Caso | O que mede |
|---|---|
| `single_spark` | `ask` roteado a `fixture-spark` (com `fixture-verifier` presente) |
| `single_api` | `ask` roteado a `fixture-api` |
| `pipeline` | plano `pipeline`: nó Spark → nó API (handoff cross-provider) |
| `ambiguous` | `ask` empatado entre `fixture-spark` e `fixture-spark-b` — termina `ambiguous` sem executar |
| `high_risk` | `ask` pinado numa capability `destructive` — a política recusa antes de contexto/execução |
| `semantic_fallback` | o mesmo `ask` ambíguo, resolvido por `fixture-resolver` (ADR 0025) |
| `parallel` | plano `parallel`: dois nós independentes + um dependente, threads reais |
| `debate` | plano `debate`: dois proposers + referee, `DecisionRecord` persistido |

Por caso o relatório registra mediana e p90 do tempo de parede da chamada (`time.perf_counter_ns`; uma repetição de aquecimento não cronometrada popula o cache de describe do registry) mais as métricas de run pedidas pela onda, **lidas dos artefatos persistidos** do run e de seus filhos — nunca de objetos vivos: `context_bytes` (counter), `provider_calls` (`providers_executed` somado sobre root + nós, incluindo as chamadas `plan` de estimativa), `semantic_calls` (planner + resolver), `handoff_bytes` (bytes de cada artefato `handoff`), `verification_calls` (spans `verification`) e `status`.

Cada repetição usa um workspace **novo** (setup não cronometrado): sem isso, o histórico de intel/performance da repetição anterior alimentaria o routing da próxima — um routing ambíguo poderia ser resolvido pelo histórico (ADR 0022) em vez do resolver, e as métricas variariam entre reps. O cache de describe do registry vive fora do workspace e permanece quente — esse é o estado estacionário.

Saída: `{"schema": "theforge-bench-runs/v1", "origin": {...}, "cases": {nome: {median_ms, p90_ms, runs, status, expect, nodes, metrics}}}` — `origin` tem o mesmo formato de `theforge-bench/v1`. `--check`/`--budgets-from` comparam as medianas de wall time como no `run_bench.py`. Isolamento idêntico: tudo sob um diretório temporário, `THEFORGE_CONFIG_DIR`/`THEFORGE_CACHE_DIR` apontando para lá.

Medição de referência nesta máquina (`--runs 1`, commit `9377061`, worktree sujo): `single_spark` ~0,9 s, `single_api` ~0,4 s, `pipeline` ~1,7 s (4 provider calls: 2 `execute` + 2 estimativas `plan`), `ambiguous` ~0,6 s (zero execução), `high_risk` ~0,3 s (recusa na política), `semantic_fallback` ~1,0 s (1 chamada semântica), `parallel` ~2,0 s (6 calls, 3 verificações, ~5,3 KB de handoff), `debate` ~1,9 s (6 calls, ~6,6 KB de handoff). Números de uma única repetição — referência de ordem de grandeza, não baseline.

## Custos fora do benchmark
- Git: quando o workspace está dentro de um repositório, cada `ask` faz 5 processos `git` com orçamento total de 5 s ([ADR 0016](adr/0016-git-read-only-signals.md)); observado em ~0,7–1,3 s por run nos testes, nesta máquina. O benchmark de contexto chama `build_context_pack` sem git.
- Negociação: até 2 chamadas `execute` extras por run, cada uma com o timeout inteiro do perfil.
- Reverificação: proporcional ao nível do perfil (nenhuma em `economy`, todos os itens em `max`), sempre sem cache.
