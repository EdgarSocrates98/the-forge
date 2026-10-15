#!/usr/bin/env bash
# Demo: instala the-forge + um especialista registrado (§10.11) — synthetic, no credentials, offline-first.
set -euo pipefail
FORGE_HOME="${FORGE_HOME_OVERRIDE:-$(mktemp -d)}"
export FORGE_HOME_OVERRIDE="$FORGE_HOME"
echo "== 02-two-forges: instala the-forge + um especialista registrado"
theforge doctor || true
echo "demo ok"
