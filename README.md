<p align="center">
  <img src="docs/assets/logo.png" alt="Forge Doctor" width="440">
</p>

# The Forge

> Uma entrada. Vários especialistas. Apenas o contexto necessário. Resultado verificável.

The Forge é um control plane local-first. Ele descobre Forges especialistas (Spark Forge, API Forge, …), escolhe o provider certo por capability de forma determinística e explicável e registra cada execução com evidência e receipt verificáveis. **The Forger** é o orquestrador interno.

**Status:** Cycle 2 em encerramento (Cycle 2.1 — [relatório de fechamento](docs/reports/cycle-2.1.md)); [relatório do Cycle 2](docs/reports/cycle-2.md). Uma linha por wave:

- **Wave A — endurecimento:** contratos com invariantes semânticas, Forge Protocol resistente a providers adversariais, routing resistente a manipulação, cache do registry fora do workspace ([ADR 0009](docs/adr/0009-registry-cache-location.md)), ambiente mínimo para providers, policy de risco com `--approve` ([ADR 0010](docs/adr/0010-policy-model.md)) e CI em Linux e Windows, com macOS semanal ([ADR 0011](docs/adr/0011-ci-support-matrix.md)).
- **Wave B — providers reais:** adapters de Spark Forge e API Forge ([providers reais](docs/real-providers.md)), versão de provider em SemVer e matriz de compatibilidade ([versionamento](docs/versioning.md)), taxonomia de capabilities com aliases e depreciação ([capabilities](docs/capabilities.md)).
- **Wave C — contexto v2:** tiers, negociação e revalidação de contexto, sinais git somente leitura, cache de fingerprints, perfis `economy`/`balanced`/`max` e telemetria por run ([arquitetura](docs/architecture.md#contexto-e-perfis), [performance](docs/performance.md)).
- **Wave D — execução multi-provider:** `theforge plan`, descritor de workspace multi-repo, verificação em quatro níveis, reprodutibilidade, `explain --json` com verificação de hashes, `replay` e taxonomia de erros por família ([ADR 0018](docs/adr/0018-multi-provider-execution.md), [ADR 0019](docs/adr/0019-error-taxonomy-and-reproducibility.md), [códigos de erro](docs/errors.md)).
- **Wave E — manutenção agentic:** auditoria de paridade dos assets agentic, instruções de host curtas, documentação e ADRs consolidados ([desenvolvimento com agentes](docs/agentic.md), [ADR 0020](docs/adr/0020-agentic-assets-canonical-source.md)).

O core continua provado também com o provider nativo `echo-forge` e com providers de teste.

## Instalação (desenvolvimento)

```bash
git clone <repo> the-forger && cd the-forger
python3.11 -m venv .venv                      # qualquer Python >= 3.11
.venv/bin/python -m pip install -e ".[dev]"   # Windows: .venv\Scripts\python
```

O runtime só usa a stdlib. O comando canônico é `theforge`, usado em todos os exemplos; `forge` é um alias de conveniência ([ADR 0008](docs/adr/0008-cli-name.md)). Use `theforge` se `forge` colidir com Foundry ou Laravel Forge no seu PATH. Para rodar a suíte de testes, instale também os adapters (ver [Desenvolvimento](#desenvolvimento)).

## Primeiros passos

Os comandos abaixo assumem o venv ativado (`source .venv/bin/activate`; no Windows, `.venv\Scripts\activate`). Sem ativar, chame `.venv/bin/theforge` (Windows: `.venv\Scripts\theforge`).

```bash
theforge doctor
theforge init
theforge capabilities list
theforge ask "eco olá" --capability demo.echo
theforge explain <run_id>   # o run_id é impresso por `ask`
theforge plan "<tarefa>" --profile max            # só planeja (desfecho planned)
theforge plan "<tarefa>" --profile max --execute  # executa os nós em sequência
```

## Registrar um provider

O `providers.toml` **do usuário** é o único que concede trust. Ele fica em `%APPDATA%\theforge\providers.toml` no Windows e em `$XDG_CONFIG_HOME/theforge/providers.toml` no POSIX (fallback `~/.config/theforge/providers.toml`); `$THEFORGE_CONFIG_DIR` sobrescreve o diretório em qualquer plataforma.

```toml
[[providers]]
id = "my-forge"
argv = ["my-forge-cli", "protocol"]   # "{python}" vira o interpretador atual
trust = "local"                        # trusted | local | unverified | blocked (padrão: unverified)
```

O `providers.toml` de projeto (`.forge/config/providers.toml`) pode declarar providers, mas eles entram sempre como `unverified` e não são executados (nem `describe`) sem `--allow-unverified`. Para confiar num provider de projeto, copie a entrada para o arquivo do usuário. Ids builtin (`echo-forge`) são reservados: usá-los em qualquer `providers.toml` é erro de uso (exit 2). Uma entrada de projeto cujo id já esteja definido no arquivo do usuário é ignorada, com aviso.

Depois rode `theforge registry refresh`.

O `version` do manifest precisa ser SemVer 2.0.0 (senão o provider fica `invalid`, `FORGE-MANIFEST-VERSION`), e cada capability segue a [taxonomia](docs/capabilities.md) (fora dela, a capability é excluída com aviso `FORGE-MANIFEST-TAXONOMY`). Para quem já tem um provider: [nota de migração](docs/provider-authoring.md#nota-de-migração-ciclo-2-wave-b).

## Spark Forge e API Forge

Os Forges reais entram por dois adapters em `adapters/`, instalados no interpretador de cada especialista (o API Forge exige Python 3.12) e registrados como qualquer provider ([ADR 0014](docs/adr/0014-provider-adapter-location.md)). Só capabilities read-only e offline são expostas; o resto aparece em `limitations` do manifest com o motivo ([catálogo](docs/capabilities.md), [ADR 0017](docs/adr/0017-capability-taxonomy.md)). O estado nativo de cada execute fica em `.forge/runs/<id>/work/` e é reduzido aos artifacts declarados; esse diretório não passa por redaction ([segurança](docs/security.md#exceção-forgerunsidwork)). Instalação, registro, testes de integração e troubleshooting: [docs/real-providers.md](docs/real-providers.md).

## Exit codes

| Código | Significado |
|---|---|
| 0 | sucesso: `ok` / `partial` em `ask` e `plan`, `planned` em `plan` sem `--execute`, `explain`/`replay` sem divergência |
| 1 | `doctor` / `providers health` com falha |
| 2 | uso inválido (inclusive arquivo de plano ilegível, `FORGE-PLAN-FILE`, e run id malformado ou desconhecido) ou workspace não inicializado |
| 3 | `no_route` / `ambiguous` |
| 4 | `provider_failure` / `refused` (inclusive recusa de policy, plano rejeitado e `replay --mode execute` recusado) |
| 5 | falha ao gravar ou ler o run (`theforge: persistence error:`) |
| 6 | divergência de integridade: `explain`, `replay --mode verify` e `replay --mode render` |
| 70 | erro interno inesperado (sem traceback) |
| 130 | interrompido (Ctrl+C) |

Igual à tabela de [docs/cli.md](docs/cli.md#exit-codes-gerais), que detalha o exit de cada subcomando.

## Documentação

- [Arquitetura](docs/architecture.md)
- [Forge Protocol v1](docs/protocol.md)
- [Escrevendo um provider](docs/provider-authoring.md)
- [Providers reais: Spark Forge e API Forge](docs/real-providers.md)
- [Capabilities: taxonomia e catálogo](docs/capabilities.md)
- [Versionamento e compatibilidade](docs/versioning.md)
- [Segurança](docs/security.md)
- [CLI](docs/cli.md)
- [Códigos de erro](docs/errors.md) (lista canônica dos códigos `FORGE-*`)
- [Performance: benchmark, baseline e budgets](docs/performance.md)
- [Desenvolvimento com agentes](docs/agentic.md)
- [Índice de ADRs](docs/adr/README.md)
- [Relatório final do Cycle 2](docs/reports/cycle-2.md)
- [Spec do ciclo 1](docs/superpowers/specs/2026-10-02-the-forge-protocol-core-design.md)

## Desenvolvimento

A suíte offline roda os adapters reais em modo replay, então o setup de desenvolvimento os instala editáveis junto com o core:

```bash
.venv/bin/python -m pip install -e ".[dev]" -e ./adapters/sparkforge -e ./adapters/apiforge
.venv/bin/python -m pytest            # suite offline
.venv/bin/python -m pytest -m slow    # gates de zero deps e instalação limpa (baixa hatchling)
.venv/bin/python -m pytest -m security   # categoria: unit, contract, integration, e2e, slow, security
.venv/bin/python -m pytest -m real_provider   # Forges reais; ver docs/real-providers.md
.venv/bin/ruff check .
.venv/bin/mypy
.venv/bin/python -m theforge.contracts.schema schemas   # regenerar schemas
.venv/bin/python scripts/agentic/audit_assets.py        # auditoria dos assets agentic; ver docs/agentic.md
```
