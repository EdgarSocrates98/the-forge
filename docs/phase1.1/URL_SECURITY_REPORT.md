# URL security report

Product Forge validates scheme, credentials, ports, DNS answers, IPv4/IPv6 and
public-address policy before capture. The default opener has no proxy handler,
does not follow redirects, and uses a connection pinned to the approved IP while
preserving the original Host/SNI for TLS certificate validation.

Evidence: `14 passed` in `tests/test_url_capture.py`, including mixed DNS, private,
metadata, credential, port, redirect, content-type, size and pinned-connection
cases. Real external scanning was not performed.
