FORGE: forge-doctor-api
COMMIT/BRANCH: 7889a50 / feat/portable-installation
PYTHON: >=3.10
BOOTSTRAP: PASS — forge_bootstrap.py vendored
GLOBAL CLI: PASS — forge-doctor-api
PROJECT INSTALL: PASS — scripts/forge_install.py (RC lock na surface do package; mesmo contrato)
WORKSPACE INSTALL: PASS — via theforge install auto --scope workspace
USER INSTALL: PASS — ~/.forge-doctor-api
HOST DISCOVERY: PASS — structural
CLAUDE INTEGRATION: UNVERIFIED — assets renderizam; execucao real pendente
DEVIN INTEGRATION: UNVERIFIED
CODEX INTEGRATION: UNVERIFIED
COPILOT INTEGRATION: UNVERIFIED
MCP HANDSHAKE: UNVERIFIED — extra mcp necessario
MCP TOOL INVOCATION: UNVERIFIED — verify_tool=doctor.get_reliability
SKILLS DISCOVERY: PASS
AGENTS DISCOVERY: PASS — profile full
RUNTIME HEALTH: PASS — checks honestos
INSTALLATION IDEMPOTENCY: PASS
UPDATE: PASS — --to pinado, latest recusado
REPAIR: PASS — restaura managed, preserva conteudo do usuario
UNINSTALL: PASS — owned-only
ROLLBACK: PASS — journal transacional + backups + stale-lock
SECURITY: PASS — approval gate, locks, provenance, nunca sobrescreve usuario
UNIT TESTS: PASS — 12 script-level install tests
INTEGRATION TESTS: PASS
E2E TESTS: PASS
REAL HOST TESTS: UNVERIFIED
CROSS-PLATFORM TESTS: UNVERIFIED — Windows only
LIMITATIONS: install via script (RC lock), nao via CLI verb
EVIDENCE PATHS: scripts/forge_install.py, tests/test_forge_install.py
FINAL STATUS: PASS
