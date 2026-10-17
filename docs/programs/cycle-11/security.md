# Cycle 11 — Security gate (Wave 0, 2026-10-17)

## G-SEC-1 — exposed PyPI token (status: OPEN — owner action required)

A PyPI API token (`pypi-AgEI…`) circulated in plaintext during the
Release 1 session (gap-register G-SEC-1). Per §3.2:

- **Active?** Cannot be verified without replaying the credential —
  which we must not do. Treat as **compromised until revoked**.
- **Blast radius:** publication-scoped; OIDC trusted publishing now
  covers all 7 PyPI packages, so the token is no longer needed.
- **Required human action:** revoke the token at PyPI account settings,
  then confirm no unintended uploads (audit: recent release timestamps
  vs. expected — all 7 releases match Cycle 10 publication dates).
- **Claim discipline:** no rotation is claimed here; this document only
  records that the revocation is the owner's pending action and that
  development may proceed — publication must not use the old credential.

## OIDC status — verified

`publish-pypi.yml` exists in all 7 Python repos with `id-token: write`
scoped to the publish job and SHA-pinned actions. Confirmed by file
inspection on each `main`.

## Supply-chain checklist status (§11.4)

| Item | State |
|---|---|
| SHA-pinned Actions | ✔ all publish workflows |
| Least-privilege tokens | ✔ `id-token` per-job only |
| Hashes in release assets | ✔ sha256 sidecars published |
| Artifact integrity gate | ✔ doc-gate resolver + link checks on all 7 |
| SBOM | open — assess in Wave 8 |

## Outstanding items tracked in gap-register

- G-REG-1 (sdist hash divergence) — fixed forward in the 0.5.1 patch.
- G-REG-2 (historical api-forge assets) — informational, no action.
- G-HOME-1 (empty GitHub homepage fields) — settings edit, owner-side.
