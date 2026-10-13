FORGE: the-forge
COMMIT/BRANCH: 51e09e4 / feat/portable-installation
PYTHON: 3.14.6 (spec >=3.10)
BOOTSTRAP: PASS — setup.sh/ps1 + forge_bootstrap.py, E2E real (wheel→venv→launcher→registry)
GLOBAL CLI: PASS — `theforge` via launcher em shell nova
PROJECT INSTALL: PASS — install apply/plan/status/doctor/repair/update/uninstall
WORKSPACE INSTALL: PASS — auto --scope workspace, discovery + precedence + WorkspaceInstall/v1
USER INSTALL: PASS — --scope user (ledger sob FORGE_HOME isolado)
HOST DISCOVERY: PASS — structural
CLAUDE INTEGRATION: UNVERIFIED — assets renderizam; execucao real pendente
DEVIN INTEGRATION: UNVERIFIED
CODEX INTEGRATION: UNVERIFIED
COPILOT INTEGRATION: UNVERIFIED
MCP HANDSHAKE: NOT_APPLICABLE — sem servidor MCP proprio
MCP TOOL INVOCATION: NOT_APPLICABLE
SKILLS DISCOVERY: PASS
AGENTS DISCOVERY: PASS — profile full
RUNTIME HEALTH: PASS — checks honestos
INSTALLATION IDEMPOTENCY: PASS
UPDATE: PASS — --to pinado, latest recusado
REPAIR: PASS — restaura managed, preserva conteudo do usuario
UNINSTALL: PASS — owned-only
ROLLBACK: PASS — journal transacional + backups + stale-lock
SECURITY: PASS — approval gate, locks, provenance, nunca sobrescreve usuario
UNIT TESTS: PASS — 84 testes install (kit+orchestration+e2e+matrix)
INTEGRATION TESTS: PASS
E2E TESTS: PASS
REAL HOST TESTS: UNVERIFIED
CROSS-PLATFORM TESTS: UNVERIFIED — Windows only
LIMITATIONS: execucao real em hosts e CI multi-OS pendentes
EVIDENCE PATHS: tests/test_installkit.py, test_install_orchestration.py, test_install_e2e.py, test_e2e_matrix.py
FINAL STATUS: PASS
