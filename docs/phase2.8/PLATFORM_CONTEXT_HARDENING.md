# Platform Context Hardening

## Changes

- Added an adapter-facing `ContextAuthorizer` protocol and immutable
  `AuthorizationDecision` shape.
- Bound capsules to workspace, session, and policy metadata without treating
  those fields as a grant.
- Split internal storage resolution (`_inspect_storage`) from authorized
  context resolution (`inspect`).
- Applied authorization before protected `inspect`, `expand`, role projection,
  and delta persistence.
- Applied the persistence invariant to every write path and verified bytes
  after atomic replacement.
- Kept CLI/MCP signatures compatible and made authorization hints optional;
  protected content still refuses without a trusted host authority.

## Verification

The negative suite covers missing/wrong principal, workspace mismatch, expired
or revoked decision, denied operation, invented classification, adulterated
reference/content, protected inspection, protected expansion, role access,
secret-bearing delta input, unknown classification, and hash-before-persist
ordering. The targeted gateway suite passed `29 passed`; the full Platform
Forge suite passed after the CLI surface and economy receipt were regenerated
for the current HEAD.

The design deliberately does not add a second authentication system or a hard
dependency on Agent Bridge. Host integration can implement the protocol at the
existing boundary.

