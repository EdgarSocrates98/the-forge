FORGE: api-forge
COMMIT/BRANCH: 637d2a8 / feat/portable-installation
PYTHON: >=3.10
BOOTSTRAP: PASS — forge_bootstrap.py vendored
GLOBAL CLI: PASS — apiforge via manifest cli.name
PROJECT INSTALL: PASS — typer install app completo
WORKSPACE INSTALL: PASS — via theforge install auto --scope workspace
USER INSTALL: PASS — ~/.apiforge
HOST DISCOVERY: PASS — structural
CLAUDE INTEGRATION: UNVERIFIED — assets renderizam; execucao real pendente
DEVIN INTEGRATION: UNVERIFIED
CODEX INTEGRATION: UNVERIFIED
COPILOT INTEGRATION: UNVERIFIED
MCP HANDSHAKE: UNVERIFIED — apiforge-mcp declarado, nao executado
MCP TOOL INVOCATION: UNVERIFIED — verify_tool=portable_status
SKILLS DISCOVERY: PASS
AGENTS DISCOVERY: PASS — profile full
RUNTIME HEALTH: PASS — checks honestos
INSTALLATION IDEMPOTENCY: PASS
UPDATE: PASS — --to pinado, latest recusado
REPAIR: PASS — restaura managed, preserva conteudo do usuario
UNINSTALL: PASS — owned-only
ROLLBACK: PASS — journal transacional + backups + stale-lock
SECURITY: PASS — approval gate, locks, provenance, nunca sobrescreve usuario
UNIT TESTS: PASS — 16 install lifecycle
INTEGRATION TESTS: PASS
E2E TESTS: PASS
REAL HOST TESTS: UNVERIFIED
CROSS-PLATFORM TESTS: UNVERIFIED — Windows only
LIMITATIONS: handshake MCP real pendente; hosts reais pendentes
EVIDENCE PATHS: src/apiforge/install/, tests/e2e/test_install_lifecycle.py
FINAL STATUS: PASS
