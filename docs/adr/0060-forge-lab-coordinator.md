# ADR 0060 — Forge Lab coordinator: subsistema novo no core, ou orquestração sobre labs existentes?

- Status: **aceito (2026-10-15)** — opção B aprovada pelo mantenedor
  (agregador fino: contrato `forge/Benchmark*/v1` + consumer
  `theforge lab collect`; motores ficam nos especialistas)

## Contexto

O programa ecosystem-2026 (Ciclo 9, `prompt_evo_cycles.md`) pede um Forge
Lab federado: cenários versionados por especialista, harness com modos de
execução (A=offline fixtures, B=replay gravado, C=sandbox real opt-in),
métricas comparáveis cross-forge e relatórios em
`docs/programs/ecosystem-2026/benchmarks/`.

Evidência coletada em cyc0-01/cyc8 (baseline + packaging):

- Labs **já existem** nos especialistas, cada um local e determinístico:
  - `forge-doctor-api lab` — corpus precision/recall (AGENTS.md: gate do repo);
  - `forge-doctor-data` — `benchmarks.yml` com cenários declarados;
  - `platform-forge` — `platformforge lab run-all` (skill platformforge-lab);
  - `api-forge` — `evals economy-hardening`/`agentic-quality` com baselines.
- O que **falta** é coordenação: nenhum registry de cenários cross-forge,
  nenhum contrato de métrica compartilhado (`forge/BenchmarkResult/v1`
  não existe), nenhum relatório agregado.
- `ExecutionResult`/`RunTelemetry`/`contracts/` já dão a infraestrutura
  de execução e evidência — não há motor de avaliação no core por invariante
  (o core não conhece domínios; sinais vêm declarados pelos providers).

## Opções

**A. `theforge.lab` novo no core** — registry próprio, harness próprio,
contrato de métricas, orquestra subprocessos dos labs especialistas.
Prós: single source of truth, relatórios uniformes, cumpre §9.x à risca.
Contras: subsistema novo sob feature freeze; risco de reimplementar
lógica que os especialistas já têm; core ganharia conhecimento de shape
de métricas (fronteira fina, mas real).

**B. Agregador fino** — sem subsistema: `contracts/benchmark.py`
(`forge/BenchmarkResult/v1`, `forge/BenchmarkSuite/v1`) + CLI
`theforge lab collect` que invoca os labs existentes (subprocess +
receipts), normaliza para o contrato e emite o relatório federado.
Prós: não é "subsistema" no sentido do freeze — é contrato + consumer
(o mesmo padrão de `_forge_portal.py`/compat manifest do Ciclo 8);
motores ficam nos especialistas (dono da verdade do domínio);
implementável dentro da disciplina atual.
Contras: modos A/B/C do §9 passam a ser política do harness agregador
(profile de execução), não engines novas — precisa ficar explícito no
contrato (campo `mode`).

**C. Nada central** — cada especialista publica seus resultados e um doc
agrega. Contras: sem verificação, sem comparação — não atende a spec.

## Decisão proposta

**Opção B** — agregador fino, alinhado ao padrão já aprovado no Ciclo 8
(manifesto `EcosystemCompatibility` + consumidores). Escopo:

1. `src/theforge/contracts/benchmark.py`: `forge/BenchmarkSuite/v1`
   (id, owner_forge, mode, scenarios[], created_at) e
   `forge/BenchmarkResult/v1` (scenario_id, metrics{name:value+unit},
   duration_ms, evidence_ref, verdict). Stdlib-only, `from_dict` strict.
2. `src/theforge/lab.py` (ou `cli/lab.py`): `theforge lab collect`
   — descobre labs via `forge.json`/`lab.json` declarado por repo,
   invoca com profile `{mode: A|B|C}`, coleta receipts, normaliza,
   escreve `docs/programs/ecosystem-2026/benchmarks/<date>.md` +
   `results.jsonl`. Nenhum motor de domínio no core.
3. Modos como política do harness: `A` default (fixtures offline),
   `B` replay (exige `recorded/` declarado), `C` sandbox real
   (exige flag explícita + receipt `mode: C` marcado — §9.11 guardrails:
   custo/destruição nunca implícitos).
4. Ground truth compartilhado (G-08): `evals/corpus/` versionado por
   repo especialista, agregador só referencia por path + sha256 —
   nunca copia conteúdo para o core.

## Consequências

- Desbloqueia cyc9-01..cyc9-09 sem quebrar o freeze (padrão contrato+
  consumer, não subsistema).
- Se o aceite preferir A, o custo é um subsistema novo justificado —
  a decisão fica registrada aqui para o revisor.
- G-07/G-08/G-09 fecham com: contrato (G-08), aggregator+harness
  (G-07), cenários `*.lab.yaml` por repo (G-09, specs cyc9-04..09).

## Riscos

- Métricas de domínios diferentes não são comensuráveis — o contrato
  leva `metrics` como mapa nome→(value,unit) e o relatório compara
  por cenário, nunca agrega cross-domínio.
- Labs que ainda não existem (spark-forge-aws/azure) ganham
  `lab: false` honesto até suas specs cyc9-04/05.
