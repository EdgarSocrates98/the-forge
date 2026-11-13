# Corporate Security Report — 2026-11-13T17:10:10+00:00

Security scenario: **PASS** — real refusals, no mocks.

Checks executed (operational-e2e.json `security` steps):
- `missing-request-id` → refused
- `undeclared-action` → refused
- `tampered-manifest` → refused
- `unknown-mcp-tool` → refused

Threat-model documents found in 7/15 repos (`docs/**/*threat*`).

Policy: no credential material flows to provider env; persisted output passes
through redact boundaries per-repo AGENTS contracts. Cloud mutation defaults
to deny; ambiguous routing returns `ambiguous`/`no_route`, never guessed.
