# Schema evolution policy

1. Keep the schema identifier and semantic version in every persisted envelope.
2. Add optional fields only when old consumers can ignore them without changing
   meaning; preserve deterministic ordering and bounded payloads.
3. A required-field, enum-semantic, identity, hash or truncation change requires
   a new major contract or an explicit compatibility adapter.
4. Package version, manifest version, protocol version and documentation version
   are separate axes. A release must state which axis changed.
5. Producers must preserve provenance, source commit, timestamps, redaction
   state and truncation state. Consumers must refuse an invalid reference rather
   than dereferencing a guessed path.
6. Unknown provider/event types are preserved as unknown metadata or structured
   refusal; they are not rewritten as runtime errors unless an actual runtime
   error occurred.
7. Every contract change needs a positive fixture, a negative fixture, a
   compatibility test and a receipt containing producer/consumer versions.
8. Cross-repository adapters remain optional dependencies and must never cause a
   specialist to claim availability when the adapter or executable is absent.
