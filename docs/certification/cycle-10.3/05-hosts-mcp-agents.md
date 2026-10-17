# Cycle 10.3 — Wave 5: Hosts, MCP, Skills & Agents

Escopo §7 do prompt: validar integrações **testadas** vs apenas **declaradas**.
Todos os testes abaixo rodaram contra as **wheels publicadas no PyPI** (baixadas
em Wave 1), não contra checkouts locais.

## 5.1 Hosts de IA — detecção observada

### forge-cli (theforge-cli@0.1.0, npm)

`forge-cli hosts` em 2026-10-17:

| Host | Estado reportado | Versão detectada | Auth |
|---|---|---|---|
| claude | integração presente | 2.1.295 | não verificada |
| codex | integração presente | 0.159.0 | autenticado |
| devin | configurado | 3000.11.92 | não verificada |
| cursor | integração presente | 3.24.18 | não verificada |
| copilot | integração presente | "Runs the GitHub Copilot CLI." | não verificada |

"Integração presente" = arquivos de integração encontrados no disco
(skills/agents instalados previamente). Detecção **testada**: o comando reporta
versões reais e distingue auth verificada de não verificada — honesto.

### theforge (theforge-core==0.5.0, PyPI wheel)

`theforge hosts list` em venv limpa:

```
claude   not detected  (weak: binary only)   [binary] claude on PATH
devin    not detected  (weak: binary only)   [binary] devin on PATH
codex    not detected  (weak: binary only)   [binary] codex on PATH
copilot  not detected  (no evidence)
```

Comportamento honesto: reporta "not detected" com evidência fraca declarada
(binary on PATH) em vez de declarar suporte pleno. **Testado.**

### apiforge (apiforge-af==0.1.0, PyPI wheel)

`apiforge ai` (JSON): reporta por host `binary`, `state`
(`SUPPORTED`/`NOT_DETECTED`/`unverified`), `version`, `logged_in`,
`launch_command` e integrações de arquivo (ex.: `.mcp.json` → `missing`).
Codex reportado `SUPPORTED`, `logged_in: true`, `codex-cli 0.159.0`.
Copilot `NOT_DETECTED` (binário fora do PATH do probe). **Testado** — a
observação é por host e nunca generalizada.

## 5.2 MCP — protocolo, testado de ponta a ponta

Transporte: **stdio + JSON-RPC 2.0** (`initialize` → `notifications/initialized`
→ `tools/list` → `tools/call`).

### Dependência opcional — comportamento correto

`apiforge-mcp` sem extra falha com `ModuleNotFoundError: mcp.server.mcpserver`
— esperado: o pacote base não instala o SDK MCP. Com `apiforge-af[mcp]` o
servidor sobe. O extra está declarado no `pyproject.toml` publicado.
**Gap de UX documentado**: a mensagem de erro é um traceback cru; candidato a
mensagem guiada ("instale apiforge-af[mcp]") — registrado no gap register.

### Matriz de surface/protocolo (apiforge-af==0.1.0)

| Invocação | tools/list | Resultado |
|---|---|---|
| `apiforge-mcp` (default) | **154 tools** | OK |
| `--surface compact` | **6 tools** | OK — superfície reduzida deliberada |
| `--protocol legacy` | 154 tools | OK |
| `--protocol modern` | 154 tools | OK |

Nota: a primeira sondagem reportou `tools: 0` — artefato de timeout curto no
pipeline de teste (resposta chegou após o `sleep`), **não** defeito do servidor.
Com janela adequada o servidor responde integralmente. Registrado aqui para
não propagar falso negativo.

### tools/call — invocação real

`tools/call name=capabilities_list arguments={}` → `isError: false`, conteúdo
JSON estruturado:

```json
{"version": 1, "capability_id": "api.analyze", "vertical": "api",
 "operation": "analyze", "state": "supported",
 "surfaces": ["cli", "ide", "mcp", "ui"],
 "evidence": ["case_manifest", "facts", "findings", "smoke_test"]}
```

Nome inexistente → `isError: true` + `Unknown tool: ...` — erro estruturado
correto no envelope MCP. **Testado: handshake + listagem + invocação + erro.**

### platformforge-mcp (platformforge==0.1.0)

`initialize` + `tools/list` → **39 tools**. Mesmo transporte stdio/JSON-RPC.
**Testado** (handshake + listagem; invocação não exercitada neste ciclo).

## 5.3 Specialists — plano de controle via wheel

`theforge specialists list` (venv limpa) reporta os 7 componentes como
`CONFIGURED` com versões lidas de dist metadata:

```
api-forge         CONFIGURED  vapiforge        0.1.0  cli:apiforge
forge-doctor-api  CONFIGURED  vforge-doctor-api 0.2.0  cli:forge-doctor-api
forge-doctor-data CONFIGURED  vforge-doctor-data 1.0.0 cli:forge-doctor-data
platform-forge    CONFIGURED  vplatformforge   0.1.0  cli:platformforge
spark-forge-aws   CONFIGURED  vsparkforge-aws  0.5.0  cli:sparkforge-aws
spark-forge-azure CONFIGURED  vsparkforge-azure 0.1.0 cli:sparkforge-azure
the-forge         CONFIGURED  vtheforge        0.5.0  cli:theforge
```

**Testado** — a leitura vem do estado do ambiente, não de declaração estática.

## 5.4 Skills & Agents — testado vs declarado

| Item | Evidência | Estado |
|---|---|---|
| Skills/agents instalados nos hosts | `forge-cli hosts` → "integração presente" em claude/codex/cursor/copilot; "configurado" em devin | **testado** (presença no disco) |
| Eficácia funcional dos agents em cada host | não exercitada end-to-end neste ciclo | **declarado** — exigir uma sessão real de host por forja seria E2E de Wave 8; registrado no gap register |
| `apiforge agents sync/lint` (roster 25 coordinators) | documentado em AGENTS.md; não executado contra a wheel | **declarado** |
| Roster de agents sparkforge (14 coordinators + 5 executors) | AGENTS.md + mirrors `.claude/agents` | **declarado** |
| MCP tools apiforge (154) | handshake + tools/list + tools/call reais | **testado** |
| MCP tools platformforge (39) | handshake + tools/list real | **testado** |

## 5.5 Veredito Wave 5

`CONDITIONALLY_VERIFIED` — a camada de **protocolo** está provada de ponta a
ponta (stdio JSON-RPC: init, list, call, erro). A camada de **detecção de
hosts** está provada e é honesta (distingue weak/strong/no evidence, nunca
generaliza). O que **não** está provado neste ciclo: a eficácia funcional de
cada agent dentro de cada host (sessões reais) — isso é explicitamente
"declarado, não testado" e entra no gap register como item de E2E, não como
falha.
