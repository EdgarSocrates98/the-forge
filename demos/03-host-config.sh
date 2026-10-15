#!/usr/bin/env bash
# Demo: detecta hosts e mostra estado real (read-only) (§10.11) — synthetic, no credentials, offline-first.
set -euo pipefail
FORGE_HOME="${FORGE_HOME_OVERRIDE:-$(mktemp -d)}"
export FORGE_HOME_OVERRIDE="$FORGE_HOME"
echo "== 03-host-config: detecta hosts e mostra estado real (read-only)"
theforge doctor || true
echo "demo ok"
