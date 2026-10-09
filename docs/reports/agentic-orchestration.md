# Agentic Ecosystem Control Plane — cycle report

Branch `feat/agentic-orchestration`, 7 repos. Formato §23; status só com
evidência executada neste ambiente.

## the-forge (Cycle A/D — core + integração)

```text
CYCLE: A+D
REPOSITORY: the-forge
BRANCH: feat/agentic-orchestration
COMMIT: f9586dc… (ver git log)
CAPABILITIES: PASS — catálogo via registry/forge-knowledge/forge.json (data-driven, sem literal de provider no core)
DISCOVERY: PASS — catalog_ids compõe installations + knowledge + checkouts; routing de sinais já existente preservado
PROVISIONING: PASS — `install auto` existente; prioridade de reuso: registry→clone local→distribuição
INSTALLATION: PASS — lifecycle real consultado (`specialists list`: 4 registrados DEGRADED pós-limpeza, 3 INSTALLABLE por checkout)
HOST DETECTION: PASS — HostDetectionResult com env/binary/config_dir + confidence_basis; claude/devin/codex detectados por binário
HOST ACTIVATION: PASS — receipt com ACTIVE_NOW só via handshake MCP real; RESTART_REQUIRED/UNSUPPORTED honestos (testes)
SKILLS: PASS — inventário existente; distinção skill≠capability mantida nos manifestos
AGENTS: PASS — 8 AgentSpec existentes; manifest agêntico declara agents/coordinators separadamente
SUBAGENTS: UNVERIFIED — suporte nativo por host não observável offline
MCP: PASS — handshake real reutilizado (mcp_verify) em `specialists doctor`/`hosts activate`
DELEGATION: PASS — DelegationRequest/Result v1 + stages; execução real via argv (test_e2e: aws analyze COMPLETED exit 0)
VERIFICATION: PASS — 25 testes novos (lifecycle/host/activation/delegation/e2e/manifests) + cross-repo manifest gate
HANDOFF: PASS — contratos Handoff existentes preservados; resultados em .forge/delegations/
POLICY: PASS — aprovação/rollback do install contract intactos; nenhuma delegação auto-aprova
SECURITY: PASS — sem provider name no core (gate genérico verde); FORGE-INSTALL-* hints completados
ECONOMY: PASS — progressive disclosure (catalog→manifest→workflow); contexto leve no list
UNIT TESTS: PASS — 21/21 control_plane
CONTRACT TESTS: PASS — manifest agentic × inventário real de verbos
INTEGRATION TESTS: PASS — collect/resolve/fan-out isolados por FORGE_HOME_OVERRIDE
REAL PROVIDER TESTS: PASS — delegação real ao checkout spark-forge-aws (analyze pyspark, exit 0)
REAL HOST TESTS: UNVERIFIED — hosts detectados por binário; consumo de assets pelo host não observável
E2E TESTS: PASS — test_control_plane_e2e (delegação real + stage honesty + CLI subprocess)
LIMITATIONS: ativação de host real pós-restart UNVERIFIED; delegação de CLIs com deps (typer) FAIL honesto sem venv
REMAINING GAPS: scenario E (falhas de rede/permissão reais) parcialmente coberto por unidades
FINAL STATUS: PASS (com UNVERIFIED declarados)
```

## Especialistas (Cycles B/C/E/F/G — manifestos)

```text
CAPABILITIES: PASS — workflows declarados batem com o inventário real de verbos (gate cross-repo)
AGENTIC MANIFEST: PASS — forge.agentic.json × 6 repos, parse estrito
DELEGATION ENTRY: PASS — cli_entry module:function + templates {cli}/{python}/{checkout}/{target}
MCP: PASS(decl) — mcp_command declarado; handshake real só executado onde deps existem (doctor-data antes)
HOST ACTIVATION: UNVERIFIED — assets + outcome honesto; consumo real pelo host pendente
INDEPENDENCE: PASS — nenhuma forja depende do The Forge; manifest é declarativo
DOCTORS BOUNDARY: PASS — workflows read_only/diagnostic only
REAL HOST TESTS: UNVERIFIED
FINAL STATUS: PASS (com UNVERIFIED declarados)
```

## Cenários §17

| Cenário | Resultado |
|---|---|
| A — Devin+PySpark+AWS | delegação real executada (task run → analyze pyspark → COMPLETED); detecção devin por binário; ativação de host pós-restart UNVERIFIED |
| B — Claude+FastAPI+API | cli_entry resolve; execução FAIL honesta sem deps do checkout (typer) — instalação real necessária |
| C — multi-forja | fan_out com budget; excedentes BLOCKED (teste) |
| D — especialista ausente | NOT_INSTALLED→INSTALLABLE por checkout; BLOCKED sem argv resolvível (teste) |
| E — falhas | binary ausente→BLOCKED; exit≠0→FAILED; HOST_AGENTIC→PREPARED (testes) |
| F — sessão ativa | outcome RESTART_REQUIRED/ACTIVE_NOW via receipt; load real pelo host UNVERIFIED |
