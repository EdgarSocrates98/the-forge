FORGE: forge-doctor-data
COMMIT/BRANCH: c96ef5f / feat/portable-installation
PYTHON: >=3.10
BOOTSTRAP: PASS — forge_bootstrap.py vendored
GLOBAL CLI: PASS — forge-doctor-data
PROJECT INSTALL: PASS — typer install family
WORKSPACE INSTALL: PASS — via theforge install auto --scope workspace
USER INSTALL: PASS — ~/.forge-doctor-data
HOST DISCOVERY: PASS — structural
CLAUDE INTEGRATION: UNVERIFIED — assets renderizam; execucao real pendente
DEVIN INTEGRATION: UNVERIFIED
CODEX INTEGRATION: UNVERIFIED
COPILOT INTEGRATION: UNVERIFIED
MCP HANDSHAKE: PASS — handshake real: initialize→13 tools→clean exit
MCP TOOL INVOCATION: PASS — get_execution_baseline tools/call real
SKILLS DISCOVERY: PASS
AGENTS DISCOVERY: PASS — profile full
RUNTIME HEALTH: PASS — checks honestos
INSTALLATION IDEMPOTENCY: PASS
UPDATE: PASS — --to pinado, latest recusado
REPAIR: PASS — restaura managed, preserva conteudo do usuario
UNINSTALL: PASS — owned-only
ROLLBACK: PASS — journal transacional + backups + stale-lock
SECURITY: PASS — approval gate, locks, provenance, nunca sobrescreve usuario
UNIT TESTS: PASS — 22 install lifecycle; suite 2618
INTEGRATION TESTS: PASS
E2E TESTS: PASS
REAL HOST TESTS: UNVERIFIED
CROSS-PLATFORM TESTS: UNVERIFIED — Windows only
LIMITATIONS: hosts reais pendentes
EVIDENCE PATHS: src/forge_doctor_data/install/, tests/test_install_lifecycle.py
FINAL STATUS: PASS
