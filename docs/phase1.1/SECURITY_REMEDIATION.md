# Security remediation

The Bridge now denies knowledge-pack authorization when the session is absent,
expired/revoked, workspace/product scope differs, source permissions are empty or
missing, or inline item provenance does not match source/version/workspace/product.
Product Forge URL capture pins the validated public IP in the actual HTTP(S)
connection, disables ambient proxies, refuses redirects and keeps TLS hostname
verification/SNI intact. Defuddle uses bounded concurrent pipe readers and kills
the process when timeout or stdout/stderr limits are crossed.

Result: P0 security controls are `VERIFIED` locally. Provider credentials and cloud
execution were intentionally not used.
