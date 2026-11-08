# Defuddle hardening

The optional CLI receives already-fetched HTML over stdin without a shell. Output
and diagnostics are drained concurrently into bounded buffers; a limit breach or
timeout terminates the process and produces a typed error. Invalid JSON, non-object
payloads, missing content, non-zero exits and unavailable binaries remain explicit
failure states.

Evidence: Product Forge full suite `225 passed, 1 skipped`; focused Defuddle tests
cover stdin, legacy payloads, unavailable tool, output overflow and timeout.
