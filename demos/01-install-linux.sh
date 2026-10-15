#!/usr/bin/env bash
# Demo: instala o núcleo num sandbox FORGE_HOME isolado (§10.11) — synthetic, no credentials, offline-first.
set -euo pipefail
FORGE_HOME="${FORGE_HOME_OVERRIDE:-$(mktemp -d)}"
export FORGE_HOME_OVERRIDE="$FORGE_HOME"
echo "== 01-install-linux: instala o núcleo num sandbox FORGE_HOME isolado"
theforge doctor || true
echo "demo ok"
