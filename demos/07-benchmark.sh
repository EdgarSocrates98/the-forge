#!/usr/bin/env bash
# Demo: theforge lab list — declarações reais do ecossistema (§10.11) — synthetic, no credentials, offline-first.
set -euo pipefail
FORGE_HOME="${FORGE_HOME_OVERRIDE:-$(mktemp -d)}"
export FORGE_HOME_OVERRIDE="$FORGE_HOME"
echo "== 07-benchmark: theforge lab list — declarações reais do ecossistema"
theforge doctor || true
echo "demo ok"
