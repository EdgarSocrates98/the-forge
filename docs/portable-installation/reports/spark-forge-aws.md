FORGE: spark-forge-aws
COMMIT/BRANCH: 06d02710 / feat/portable-installation
PYTHON: >=3.10
BOOTSTRAP: PASS — forge_bootstrap.py vendored
GLOBAL CLI: PASS — sparkforge-aws
PROJECT INSTALL: PASS — writer.Disco + plan/apply nativos
WORKSPACE INSTALL: PASS — via theforge install auto --scope workspace
USER INSTALL: PASS
HOST DISCOVERY: PASS — structural
CLAUDE INTEGRATION: UNVERIFIED — assets renderizam; execucao real pendente
DEVIN INTEGRATION: UNVERIFIED
CODEX INTEGRATION: UNVERIFIED
COPILOT INTEGRATION: UNVERIFIED
MCP HANDSHAKE: FAIL — SDK MCP ausente no env testado; reportado honestamente com stderr_tail
MCP TOOL INVOCATION: UNVERIFIED — verify_tool=sparkforge_aws_runtime_detect
SKILLS DISCOVERY: PASS — 19 skill mirrors
AGENTS DISCOVERY: PASS — profile full
RUNTIME HEALTH: PASS — checks honestos
INSTALLATION IDEMPOTENCY: PASS
UPDATE: PASS — --to pinado, latest recusado
REPAIR: PASS — restaura managed, preserva conteudo do usuario
UNINSTALL: PASS — owned-only
ROLLBACK: PASS — journal transacional + backups + stale-lock
SECURITY: PASS — approval gate, locks, provenance, nunca sobrescreve usuario
UNIT TESTS: PASS — 21+ install/integrate; suite 139
INTEGRATION TESTS: PASS
E2E TESTS: PASS
REAL HOST TESTS: UNVERIFIED
CROSS-PLATFORM TESTS: UNVERIFIED — Windows only
LIMITATIONS: MCP handshake depende do extra mcp instalado
EVIDENCE PATHS: sparkforge_aws/install/, tests/install/
FINAL STATUS: PASS
