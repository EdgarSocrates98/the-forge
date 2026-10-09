---
id: lf-0001
title: Loop Factory smoke validation on the-forger
agent: any
risk: low
grill: completed
verification:
  - .venv/Scripts/loop-factory doctor
  - .venv/Scripts/loop-factory scan
  - .venv/Scripts/python -m pytest tests/test_docs_consistency.py -x -q
---

# Grill Gate

- Owner: repository operator.
- Problem: the loop needs one visible spec proving scan → dispatch → review mechanics work in this repo before real specs are authored.
- Out of scope: authoring product specs, autonomous daemon/cron, archiving without human acceptance.
- Review failure: generated prompt misses spec id/verification commands, or a verification command fails.
- Riskiest assumption: the Windows venv path (`.venv/Scripts/loop-factory`) is the canonical invocation here — documented in `docs/loop-factory.md`.
- Smallest acceptable implementation: this spec plus a dispatch/review prompt generated against it; the spec stays in `active/` awaiting human archive.

# Context

Loop Factory was initialized in this repo (`factory/` scaffold, CLI installed editable from the sibling checkout). This spec exercises the state machine end-to-end without inventing product work.

# Acceptance Criteria

- `loop-factory scan` lists this spec while it is in `inbox/`.
- `loop-factory dispatch --stage` moves it to `active/` and writes a prompt under `factory/prompts/` plus a run record under `factory/runs/`.
- `loop-factory review lf-0001` generates a review prompt under `factory/reviews/`.
- `docs/loop-factory.md` documents the state machine, commands and boundaries for this repo.
- The spec remains in `active/` — archive requires an accepted human review.

# Constraints

- Do not add runtime dependencies to the core (`src/theforge` stays stdlib-only); the `loop-factory` CLI is a dev tool.
- Do not archive this spec autonomously.
- `factory/specs/` is tracked; `factory/prompts|runs|reviews|logs` are gitignored audit artifacts.

# Review Notes

- Confirm the generated prompt contains the spec id and the verification commands.
- Confirm `factory/prompts/`, `factory/runs/` and `factory/reviews/` contents are not committed.
