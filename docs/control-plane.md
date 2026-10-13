# Control Plane — Specialist Lifecycle, Hosts & Delegation

O The Forge como *Agentic Ecosystem Control Plane*: descobre, classifica,
ativa e delega — sem confundir instalação, ativação e execução.

## Lifecycle (forge/SpecialistLifecycleState/v1)

```text
UNKNOWN → DISCOVERED → NOT_INSTALLED → INSTALLABLE → INSTALLING
→ INSTALLED → CONFIGURED → REGISTERED → HEALTHY
→ HOST_ACTIVATION_PENDING → HOST_ACTIVATED → READY
                        ↘ DEGRADED / FAILED / INCOMPATIBLE
INSTALLING/… → UNINSTALLING → REMOVED
```

Transições fora do grafo lançam `ContractError` — não se pula estado.

Fontes da verdade, em ordem: `~/.forge/installations/*.json` → probe real
do CLI (`--version`) → provider registry → checkout local com
`forge.json`. Nada é HEALTHY por presença de arquivo.

## Descoberta contextual

O catálogo é **data-driven** (`specialists.catalog_ids`): união de
installations registry + `forge-knowledge/*.json` + `forge.json` dos
checkouts do workspace. Uma forja nova entra no plano de controle
adicionando dados, nunca código core.

## Hosts (FASE 4)

`theforge hosts list` — `HostDetectionResult/v1` com evidência por host:

- `env` — markers de sessão (DEVIN_CLI, CLAUDECODE…) → `running`
- `binary` — executável no PATH → instalado, não necessariamente ativo
- `config_dir` — `.claude/`, `.devin/`… no projeto

`detected` exige ≥2 classes de evidência ou marker de sessão. Cada claim
carrega `confidence_basis` — binário sozinho é `weak`, nunca `running`.

`theforge hosts activate <host>` — `HostActivationReceipt/v1`:

| Outcome | Quando |
|---|---|
| `ACTIVE_NOW` | só quando o único componente pendente foi verificado por check vivo (handshake MCP real) |
| `RESTART_REQUIRED` | skills/agents escritos — o host os lê na próxima sessão; vem com instruções de retomada |
| `UNSUPPORTED` | host sem caminho de consumo declarado para o componente |

`ACTIVE_NOW` nunca sai de "arquivo existe".

## Delegação (FASE 5)

`SpecialistDelegationRequest/v1` → `SpecialistDelegationResult/v1` com
stages `PREPARED → SUBMITTED → RUNNING → COMPLETED / FAILED / BLOCKED`.
`COMPLETED` exige `exit_code` real — o schema recusa sem ele.

Modos: `DIRECT_CAPABILITY`, `SPECIALIST_WORKFLOW`, `HOST_AGENTIC`
(sempre `PREPARED` — o host executa), `MULTI_SPECIALIST` (fan-out com
`--max-parallel`, excedentes → `BLOCKED`), `DIAGNOSTIC_ONLY`.

O canal é o argv real do especialista. Templates no manifest:

| Placeholder | Resolve para |
|---|---|
| `{cli}` | launcher instalado; senão `python -c "from <cli_entry> import fn; fn()"` no checkout |
| `{python}` | interpretador corrente |
| `{checkout}` | clone local |
| `{target}` | alvo da delegação |

```bash
theforge task plan "analise meu pipeline"        # DelegationRequests
theforge task run "..." --provider spark-forge-aws --target ./jobs
theforge task explain <task_id>                  # resultado gravado
```

Registros em `.forge/delegations/<task_id>.json`.

## Manifest agêntico (forge/SpecialistAgenticManifest/v1)

Cada forja declara `forge.agentic.json` na raiz: `cli_entry`
(module:function), workflows executáveis, skills/agents/coordinators,
`mcp_command`, `host_adapters`, `requires_network/credentials`,
`read_only_default`. Validado contra o contrato e contra o inventário
real de verbos (`tests/test_agentic_manifests.py`).

## Fronteiras preservadas

- Forjas funcionam sem o The Forge — o manifest é declarativo.
- Capability ≠ skill ≠ agent ≠ MCP — cada um declarado separadamente.
- Instalação ≠ execução: cada eixo verificado independentemente.
- Nenhuma delegação auto-aprova mutação: workflows `read_only` por
  padrão; mutações seguem a governança de install (`--yes` pós-`--dry-run`).
