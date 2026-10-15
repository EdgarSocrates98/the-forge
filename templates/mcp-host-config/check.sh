#!/usr/bin/env bash
# Template check — structure + offline validation (cyc10-03 §10.10)
set -euo pipefail
cd "$(dirname "$0")"
[ -f README.md ] || { echo "README missing"; exit 1; }
echo "mcp-host-config: structure ok — run the documented install to exercise the forge"
