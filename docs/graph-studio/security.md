# Security

- Server binds `127.0.0.1`; read-only verbs (405 elsewhere); no
  directory traversal; no request-body parsing at all.
- Payload caps via `--limit`; truncation is declared in limitations.
- `components.json` gate: a declined component stays off.
- Labels are rendered as text, never as markup/commands.
- Federation runs provider CLIs via argv with timeouts; a malformed
  provider document fails schema parse and lands in `notes`, not in the
  merged view.
