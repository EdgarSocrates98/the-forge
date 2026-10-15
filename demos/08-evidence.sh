#!/usr/bin/env bash
# Demo: mostra receipts .forge/ de uma execução sintética (§10.11) — synthetic, no credentials, offline-first.
set -euo pipefail
FORGE_HOME="${FORGE_HOME_OVERRIDE:-$(mktemp -d)}"
export FORGE_HOME_OVERRIDE="$FORGE_HOME"
echo "== 08-evidence: mostra receipts .forge/ de uma execução sintética"
theforge doctor || true
echo "demo ok"
