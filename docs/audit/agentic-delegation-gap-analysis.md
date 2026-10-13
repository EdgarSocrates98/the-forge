# Agentic delegation gap analysis (FASE 0)

O que existe vs o que a FASE 5 exige.

## Hoje

- `ForgeProviderAdapter` executa capabilities determinísticas
  (analyze/judge) via argv — DIRECT_CAPABILITY existe e é real.
- `theforge ask`/`plan`/`capabilities`/`providers` roteiam intent para
  providers registrados.
- `install auto` delega instalação via CLI/`install_command` (subprocess
  real, stdout capturado, BLOCKED honesto).
- Coordinators/agents existem *dentro* de cada forja como arquivos de
  definição — acessíveis a hosts, não ao The Forge programaticamente.

## Gaps

| Requisito | Gap |
|---|---|
| SPECIALIST_WORKFLOW | não existe — precisa de entry point executável declarado pela forja (`agentic manifest` com `delegation.commands`) |
| HOST_AGENTIC | host-dependente; só PREPARED verificável offline — o submit real é do host |
| MULTI_SPECIALIST | `install auto` faz fan-out de instalação; falta fan-out de *execução* com budget |
| DIAGNOSTIC_ONLY | coberto por capabilities read-only existentes |
| DelegationRequest/Result v1 | não existe — criar contratos com stage tracking PREPARED→COMPLETED |
| Stage tracking | não existe — `COMPLETED` só após evidência real |

## Decisão

Delegação ao nível The Forge = argv real contra o CLI do especialista
(mesmo canal do `install_command`, provado). "Delegação agentic" via
host é `PREPARED` honesto: The Forge produz o envelope; o host executa.
