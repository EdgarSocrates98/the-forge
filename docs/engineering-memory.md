# Engineering Memory (Cycle 5, Wave B)

Memória de engenharia é **conhecimento verificável**, não histórico de
conversa. Cada `EngineeringMemoryEntry/v1` é uma unidade durável com estado
epistêmico e proveniência — persistida append-only em
`.forge/memory/entries.jsonl` (project-local, gitignored).

## Estados epistêmicos

| estado | significado |
|---|---|
| `confirmed` | verificado — exige `evidence_refs`/`decision_refs` |
| `observed` | medido num run, sem verificação independente |
| `reported` | afirmado por fonte externa; nunca promove sozinho |
| `inferred` | derivado; fica marcado como inferência |
| `unresolved` | sem proveniência suficiente — default honesto |
| `stale` | surface/contexto mudou; história preservada |
| `superseded` | substituída por entrada nova (`superseded_by`) |

`confirmed` recusa construção sem refs — prosa não é verificação
([ADR 0049](adr/0049-engineering-memory.md)). O `id` é derivado de conteúdo
(sha256 de kind|scope|subject|claim).

## Aprendizado por run

`learn_from_run(root, store, run_id)` destila artefatos persistidos:
`decision` → entrada `decision`; `verification` passed → `resolution`
`confirmed`; falhou → `failure` observada; falhas de nós de plano → `failure`
por provider/capability. Texto de provider **nunca** vira fato.

## Escopos e isolamento cross-project

```
project (default) ┐
workspace         ┘ nunca exportam, nunca importam

portable      ┐  exigem origin_project_class + redaction;
organization  ┘  únicos que cruzam a fronteira (export/import)
```

`export_entries` filtra para escopos portáveis/org; `import_entries` recusa
`project`/`workspace` (default-deny, §112). Summaries são project-local —
conhecimento cross-project viaja como entries.

## Padrões de falha

`failure_patterns(root)` agrega entradas `failure` por
`(error_family, provider, capability, surface, task_family)` em
`FailurePattern/v1` — rollup observacional; `resolved_by` cita refs de
decisão como recomendação, nunca ação automática.

## CLI

```text
theforge memory list [--kind K] [--epistemic E] [--subject Q] [--all]
theforge memory learn --run <run_id>
theforge memory export > pack.json
theforge memory import <pack.json>            # ou '-' para stdin
theforge memory patterns
theforge memory summarize <subject> --claim "..." --source <id>...
```

`export`/`import` são os únicos comandos que cruzam a fronteira do projeto:
só escopos `portable`/`organization` saem, e `import` recusa
`project`/`workspace` contando-os em `limitations`. `patterns` mostra o
rollup `FailurePattern` — recomendação, nunca regra. Tudo offline; writes
passam por `security.redact` como qualquer persistência.

## Instrumentação e ROI (Cycle 5.1)

`pack_stats(root, query, surface=...)` retorna contadores determinísticos do
mesmo pipeline de `memory_pack` — `entries_considered`/`matched`/`fresh`/
`not_fresh`/`delivered`/`withheld`/`terminal`, `bytes_matched`/`delivered` —
sem escrever nada. É a instrumentação usada por
`scripts/bench/run_memory_roi.py`, que mede memory-on vs memory-off, custo de
retrieval vs scan, influência via canal governado
(`failure_patterns → experimento → StrategyPolicy → preferred_providers`) e
as propriedades de segurança (terminal nunca entregue; surface desconhecida
não é fresh). Resultado medido e limitações:
`docs/reports/cycle-5.1-memory-roi.md`.
