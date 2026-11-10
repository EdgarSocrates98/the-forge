# Vault Integrity

Vault operations validate the authorized root and regular-file boundaries,
serialize writes, capture a baseline hash, reject TOCTOU changes, create an
internal backup before mutation, verify the post-write hash, and record a
body-free receipt. Conflicts require review; rollback validates receipt,
backup, path and hashes before mutation.
