# Graph Explorer (the Studio UI)

Embedded zero-dependency canvas explorer:

- pan/zoom, node and edge selection, inspector panels;
- search box (debounced), kind/layer filters, legend;
- status bar with counts, provider, epistemic mix, limitations;
- neighbor expansion for large graphs; `--limit` truncation is shown.

Keyboard: arrows pan, `+`/`-` zoom, `0` fit, `/` search focus,
`Esc` clears selection.

Deliberately absent when the engine lacks the data: timeline, diff
viewer, snapshot selector (Platform Forge engines expose them via CLI;
Studio support is on the roadmap).
