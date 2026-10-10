---
name: forge-factory
description: Loop Factory spec queue in this repository: factory/specs/{inbox,active,archive} where the folder is the state. Load when picking up a factory spec, dispatching work, verifying criteria, or deciding whether a spec may move state.
---

# forge-factory

<background_information>
Loop Factory is this repo's operational task queue ([docs/loop-factory.md](../../../docs/loop-factory.md), ADR 0057). A task is a Markdown spec; its folder is its state. Agents implement and verify — humans decide what to build and what to accept.
</background_information>

<instructions>
## Workflow

1. `.venv/Scripts/loop-factory scan` — list inbox + active specs.
2. A spec is dispatchable only when its grill gate is complete (`grill: completed` or a filled `# Grill Gate`). Missing gate → report "needs grilling"; never answer the questions for it.
3. `.venv/Scripts/loop-factory dispatch --agent codex --limit 1 --stage` — writes `factory/prompts/`, records the run, moves the spec to `active/`. Add `--execute` only when the user asked for live agent execution.
4. Implement **only** the acceptance criteria, in existing code style.
5. Run every `verification:` command and keep the output as evidence.
6. `.venv/Scripts/loop-factory review <spec-id> --agent codex` — generate the review prompt; check the diff against the criteria.
7. `.venv/Scripts/loop-factory backprop --agent codex` — fold implementation facts back into specs/docs without changing product intent.

## Boundaries

- Never archive autonomously: `archive <id> --accepted` requires an accepted human review — the spec stays in `active/` at the review gate.
- Never grill autonomously: unanswered product questions stay open questions.
- A failed verification leaves the spec `active` with a note in `factory/runs/` — do not retry in a loop or weaken criteria to pass.
- `factory/specs/` is tracked source of truth; `factory/prompts|runs|reviews|logs` are gitignored audit artifacts — read them, don't treat them as truth.
- `verification:` commands point at the repo's real gates (`pytest`, `ruff`, `mypy`, `audit_assets.py`) — independent verification is the evidence.
</instructions>
