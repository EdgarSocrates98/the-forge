# Phase 1 E2E evidence

## Portal visual, accessibility and usability gate — 2026-11-07

The Portal gate is green on the current `main` build:

- visual probe: 42 route/variant combinations; 0 axe entries; 0 serious or
  critical violations; 0 focus targets without a visible ring; 0 bad clips;
- visual audit: 214 captures; 0 pages with horizontal overflow;
- responsive reflow: 252 captures; 0 page-level horizontal overflows; 0 bad
  clips outside an approved scroller;
- keyboard/usability cycle: 9/9 steps, 94 keystrokes, 0 friction findings;
- browser E2E: 35 passed, 1 skipped; unit suite: 584 passed; production build:
  successful.

The raw audit output is retained locally under
`E:\projetos\FORJAS\.audit-work\portal-gate-20261107\` and the Portal's
existing E2E artifacts. Intentional responsive ellipses remain visible in the
capture counts, but none is an unlabelled or page-breaking clip.

## Cross-Forge contract path

The new cross-Forge contract path is currently covered at adapter/unit level:

`Code Atlas ContextPack → KnowledgeContextPack → Agent Bridge authorization →
Lens provenance`

An end-to-end process test across all four repositories is the next gate and is
not claimed here.
