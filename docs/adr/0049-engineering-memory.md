# ADR 0049 — Engineering Memory: conhecimento verificável, não histórico de conversa

- Status: aceito (2026-10-15)

## Contexto

Cycle 5 precisa que a plataforma lembre fatos, decisões e falhas de engenharia
entre runs — sem transformar prosa em verdade e sem vazar conhecimento entre
projetos.

## Decisão

`EngineeringMemoryEntry/v1` é a unidade durável, persistida em JSONL
append-only em `.forge/memory/` (`src/theforge/memory.py`). Cada entrada
carrega estado epistêmico e proveniência:

- `confirmed` exige `evidence_refs`/`decision_refs` apontando para artefatos
  persistidos — nunca texto livre. O contrato recusa na construção.
- Entradas sem proveniência ficam `unresolved`/`inferred`; `reported` nunca
  promove a `confirmed` sem evento de verificação.
- `id` é derivado de conteúdo (sha256 de kind|scope|subject|claim) — reescrever
  um campo produz uma identidade nova, nunca sobrescrita silenciosa.
- `stale`/`superseded` mantêm história; `superseded_by` liga para frente e a
  fonte nunca é deletada (`mark_stale` exige razão + refs).
- `scope` governa fronteira entre projetos: `project`/`workspace` são default e
  nunca exportam; `portable`/`organization` exigem `origin_project_class` +
  `redaction`, e `import_entries` recusa qualquer outro escopo.

`learn_from_run` destila apenas artefatos persistidos (decision, verification,
plan-result) — saída de provider nunca vira fato. `FailurePattern/v1` agrega
falhas por (error_family, provider, capability, surface, task_family) como
observação; `resolved_by` cita decisões, nunca ação automática.

`MemoryPack`/`MemorySummary` compactam contexto citando ids dos originais;
summaries nunca cruzam projetos (conhecimento cross-project viaja como entries,
não como summary).

## Consequências

- Memória é consultável e auditável (`theforge memory list|learn|export|
  summarize`), e envenenamento falha fechado: sem evidência não há `confirmed`.
- Uma troca de surface invalida a autoridade da entrada (`surface_fingerprint`
  registra o contexto medido), sem reuso silencioso.
- Isolamento cross-project é default-deny e testado adversarialmente.
