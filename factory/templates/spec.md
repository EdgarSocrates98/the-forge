---
id: lf-0000
title: Replace with concise spec title
agent: any
risk: medium
grill: required
verification:
  - python3 -m unittest
---

# Grill Gate

Use `grill-me` before dispatch. Ask one question at a time. For each question, record recommended answer and final decision.

- Who owns this decision?
- What user/customer problem is this solving?
- What is explicitly out of scope?
- What would make this spec fail review?
- Which assumption is riskiest?
- What is the smallest acceptable implementation?

# Context

What problem should be solved and why now.

# Acceptance Criteria

- Criterion 1.
- Criterion 2.

# Constraints

- Automate implementation, not product decisions.
- Keep changes scoped.

# Review Notes

- Evidence reviewer should inspect.
- Known risks or edge cases.
