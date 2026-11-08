# Compatibility matrix

| surface | backward-compatible change | status |
|---|---|---|
| Agent Bridge events | unknown events remain typed, errors remain errors | PASSED |
| Bridge retention/replay | markers/cursors preserve prior replay semantics | PASSED |
| The Forge provider routing | additive eligibility/reason/receipt validation | PASSED |
| Portal API client | existing `forge/PortalApi/1` envelope retained | PASSED |
| Portal navigation | lazy route and search/dashboard entry added | PASSED |
| CLI installation | existing shell/PowerShell entry points preserved | PASSED |
| cloud/external provider | no compatibility claim without credentials | NOT_RUN |

Não foram introduzidos Redis, Kafka, PostgreSQL, Kubernetes, um segundo router,
um segundo runtime de sessões ou um frontend standalone de API Operations.
