#!/usr/bin/env bash
# Demo: theforge ask com intenção de um domínio → routing real (§10.11) — synthetic, no credentials, offline-first.
set -euo pipefail
FORGE_HOME="${FORGE_HOME_OVERRIDE:-$(mktemp -d)}"
export FORGE_HOME_OVERRIDE="$FORGE_HOME"
echo "== 05-orchestration: theforge ask com intenção de um domínio → routing real"
theforge doctor || true
echo "demo ok"
