# Receita — portal web local: command center da federação

**O quê:** `theforge portal` sobe uma UI web opcional em `127.0.0.1` +
token de sessão sobre os serviços reais — instalação, hosts, handshakes
MCP por forja, federação (lifecycle dos especialistas + registry),
agents, skills, grafo federado e tasks — com o mesmo plan→confirm→apply
dos verbos.
**Por que:** o command center é onde a federação é o objeto de trabalho;
para quem prefere ver o estado antes de agir, a UI mostra a mesma
verdade do CLI — receipts incluídos.
**Quando:** primeira configuração do workspace, auditoria visual da
federação, demos do fluxo sem decorar comandos.
**Quando não:** automação/CI — use `theforge install auto`, `specialists`
e `graph --federated` diretamente; o portal é interativo e
loopback-only.

## Problema

"Quero ver o estado das seis forjas — quem está instalada, com MCP
verificado, com checkout — sem rodar seis comandos."

## Pré-requisitos

`theforge` instalado (venv ou wheel com `portal_assets`); forjas
registradas pelo bootstrap em `~/.forge/installations/` para a federação
reportar mais que `NOT_INSTALLED`.

## Passo a passo

```bash
theforge portal                  # sobe em 127.0.0.1 e abre o browser
theforge portal --no-browser     # só imprime a URL com token de sessão
theforge portal --port 8765      # porta fixa (default: livre)
theforge portal --root DIR       # workspace alvo (default: cwd)
```

O servidor imprime `{"url": "http://127.0.0.1:PORT/?forge_session=…"}` —
chamadas `/api/*` sem `X-Forge-Session` recebem `403`.

## Saída esperada / interpretação

- **Federation**: `specialists.collect` real — `INSTALLED/CONFIGURED/
  REGISTERED/DEGRADED/INSTALLABLE/NOT_INSTALLED` por forja, mais o
  registry `~/.forge/installations` e a contagem de checkouts. É o mesmo
  par de evidências de `theforge specialists`.
- **MCP**: o Doctor/Spark/APIs declaram servidor; o handshake é real
  (`kit.mcp_verify` — initialize → tools/list), `NOT_APPLICABLE` quando
  a forja não declara MCP — the-forge inclusive (control plane não
  expõe MCP, por desenho).
- **Graph**: `federated_merge` real — nós com prefixo `provider:`; sem
  arestas inferidas entre forjas.
- **Install auto**: `federation/plan` → `federation/install-auto`
  delega ao CLI real de cada forja — cada forja executa a si mesma
  (ADR-0058), nunca simulado.
- **Tasks**: intents seguros mapeiam para doctor/status/federation/
  mcp_verify/graph — receipt por tarefa com `exit_code`.

## Verificação

O receipt de cada operação (`InstallReceipt/v1`, task receipt) é a
prova — "apareceu na UI" nunca é. Mutações exigem `confirm` literal +
`plan_token` assinado sobre o plano ecoado; token velho vira
`PORTAL-PLAN-STALE` (409, retryable).

## Limitações

Loopback apenas. Assets vendored (`portal/assets` + manifest sha256) —
sem CDN, sem telemetria, offline-first. `install_auto` delega CLIs
reais: forja sem CLI resolvível vira `BLOCKED` nomeado no receipt,
não falso PASS. Probe de checkout cobre o workspace — forjas fora da
árvore do workspace aparecem pelo registry, não por `checkout`.

## Erros comuns

| Sintoma | Causa | Ação |
|---|---|---|
| `403` na API | header `X-Forge-Session` ausente | usar a URL com `?forge_session=` |
| `PORTAL-PLAN-STALE` | apply sem o `plan_token` do plano | refazer o plan e enviar o token |
| `TF-PORTAL-NOT-REGISTERED` | forja ausente do registry | rodar o bootstrap/setup primeiro |
| `TF-PORTAL-MCP-NONE` | nenhum especialista declara MCP | instalar forjas com servidor MCP |
| especialistas `NOT_INSTALLED` | registry vazio no HOME | `theforge install auto` ou setup.sh |
| `PORTAL-HOST` 403 | Host não-loopback (rede/túnel/DNS rebinding) | acesse por 127.0.0.1/localhost |
| `PORTAL-ORIGIN` 403 | POST com Origin fora do loopback | só a UI do portal muta |
| `PORTAL-RATE-LIMITED` 429 | >10 mutações/min | aguarde a janela; envelope sinaliza retry |
