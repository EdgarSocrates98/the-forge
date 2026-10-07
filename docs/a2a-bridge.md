# A2A bridge (experimental)

Cycle 4, Wave I — adapter opcional em `theforge.interop.a2a`. Document-level
translation only: **nenhuma chamada de execução remota existe aqui** — o
bridge traduz objetos, marca confiança e para.

## Posição na arquitetura

```
Forge Protocol (nativo)  ──bridge──►  A2A (agent-to-agent externo)
      ▲                                   │
      └──── remote candidates ◄── card ───┘
```

- O Forge Protocol continua o contrato nativo; o core não conhece A2A.
- Um agente A2A remoto **nunca é um provider local**: vira um
  `ForgeRegistryEntry` com claims não-verificados — alimenta negotiation e
  remote discovery como candidato, nunca como executável.
- Fetch de cards usa a mesma disciplina dos `http` registry sources
  (https-only, cache verificado por sha256, freshness, `THEFORGE_NO_NETWORK`).

## Direção Forge → A2A

| Forge | A2A |
|---|---|
| `RegistryRecord` ready | Agent Card (`agent_card`) |
| `Capability` | `skills[]` (+ metadata.forge) |
| `TaskSpec` | `message/send` params (`task_to_send_params`) |
| `ExecutionResult` | artifacts/parts (`artifacts_from_result`) |

O que o A2A não expressa vai em `metadata.forge` — provider id, manifest e
surface fingerprints, trust, execution flags, features, requirement,
constraints, sha256 de artifacts. Nada é perdido em prosa.

Cards emitidos têm `url: ""` e `streaming: false` — providers Forge rodam
como subprocessos locais; o card descreve, não convida execução direta.

## Direção A2A → Forge

`entry_from_card(card)` → `ForgeRegistryEntry` com:

- `provider` = `card.name` sanitizado para o padrão de id Forge;
- `capabilities` = ids das `skills` declaradas;
- `runtime` = `{offline: false, requires_network: true,
  requires_credentials: bool(securitySchemes|security)}` — as dimensões de
  política do §65: execução remota, egresso de dados, retenção externa,
  autenticação e rede viajam no `runtime` + `limitations`;
- `distribution` = `None` — um endpoint de serviço não é artefato
  instalável e não pode ser pinado por hash;
- `limitations` sempre incluem: external service ≠ Forge provider, claims
  não-verificados, egresso de dados, autenticação out-of-band.

`card_to_document` embrulha o entry num `RegistryDocument` de uma entrada —
é assim que o source kind `a2a` entra na descoberta:

```toml
# ~/.config/theforge/registries.toml (opt-in)
[[sources]]
id = "agent-hub"
kind = "a2a"            # card URL em 'url'
enabled = true
url = "https://agent.example/.well-known/agent-card.json"
max_age_s = 3600
```

`theforge capabilities discover --requirement req.json` então considera o
agente como candidato remoto (`RemoteProviderCandidate`, fit máximo
`declared` — nunca `FULL` sem verificação).

## Falhas explícitas (conformance)

- card sem `name` utilizável → `invalid`, sem entry;
- `version` não-SemVer → `0.0.0` + warning;
- `inputModes`/`outputModes` fora de `text`/`application/json` → limitation
  `unsupported modalities` (nada é descartado em silêncio);
- `protocolVersion` ≠ suportado → limitation de drift semântico;
- campos/extensões desconhecidos → tolerados (forward-compat);
- falha de transporte/timeout → `unavailable` ou cache `stale` explícito;
- `THEFORGE_NO_NETWORK=1` → sem fetch, cache se existir.

## Limites conhecidos

- Sem cliente JSON-RPC de execução: o bridge para no candidato/documento.
- `securitySchemes` não são interpretados além de "precisa de credencial" —
  a credencial nunca sai do Forge; o operador a fornece ao agente remoto.
- Agent Cards estendidas autenticadas e assinaturas JWS de card não são
  verificadas ainda — declaradas como claims, não elevadas a `verified`.
