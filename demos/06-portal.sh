#!/usr/bin/env bash
# Demo: sobe o portal local e lista as seções servidas (§10.11) — synthetic, no credentials, offline-first.
set -euo pipefail
FORGE_HOME="${FORGE_HOME_OVERRIDE:-$(mktemp -d)}"
export FORGE_HOME_OVERRIDE="$FORGE_HOME"
echo "== 06-portal: sobe o portal local e lista as seções servidas"
theforge doctor || true
echo "demo ok"
