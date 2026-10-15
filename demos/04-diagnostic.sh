#!/usr/bin/env bash
# Demo: roda theforge doctor num workspace sintético (§10.11) — synthetic, no credentials, offline-first.
set -euo pipefail
FORGE_HOME="${FORGE_HOME_OVERRIDE:-$(mktemp -d)}"
export FORGE_HOME_OVERRIDE="$FORGE_HOME"
echo "== 04-diagnostic: roda theforge doctor num workspace sintético"
theforge doctor || true
echo "demo ok"
