# Release 1 — Open source & comunidade (Wave 9)

## Arquivos comunitários — auditoria 9/9

| Arquivo | the-forge | forge-cli | forge-portal | api-forge | platform-forge | sf-aws | sf-azure | doctor-data | doctor-api |
|---|---|---|---|---|---|---|---|---|---|
| LICENSE (MIT) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| README.md | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| CONTRIBUTING.md | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| CODE_OF_CONDUCT.md | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| SECURITY.md | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| SUPPORT.md | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Issue templates | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| PR template | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| CHANGELOG.md | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |

9/9 repos já possuem o conjunto completo — nenhuma lacuna.

## Extensibilidade (como contribuir)

Canais documentados: providers via `providers.toml` + Forge Protocol
(`docs/protocol.md`, `docs/provider-authoring.md`), skills/agents via
host mirrors (`docs/agentic.md`), regras por especialista, benchmarks via
Forge Lab, MCP adapters `adapters/`. Marketplace completo: **fora de
escopo R1**.

## Telemetria

Opt-in apenas; nenhuma telemetria obrigatória ou oculta (verificado —
nenhum beacon/phone-home nos pacotes).

## Rascunhos de comunicação (para revisão do mantenedor)

- **Curta:** "The Forge — control plane local-first que descobre, roteia
  e governa Forjas especialistas (engenharia de API, dados, plataforma,
  diagnóstico). Instale uma Forja, não um monólito."
- **Técnica:** providers via Forge Protocol (subprocess+JSON), trust
  boundary explícita, receipts sha256, hosts Claude/Codex/Devin
  verificados, Copilot experimental, zero deps de runtime no core.
- **FAQ:** "O CLI é obrigatório?" não — especialistas instalam
  independente. "O Portal é obrigatório?" não — `theforge portal` é
  opt-in. "Funciona offline?" sim — deterministic core, offline-first.

Nenhuma promessa de desempenho/compatibilidade não provada.
