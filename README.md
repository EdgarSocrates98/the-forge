<p align="center">
  <img src="docs/assets/logo.png" alt="Forge Doctor" width="440">
</p>

# The Forge

> Uma entrada. Vários especialistas. Apenas o contexto necessário. Resultado verificável.

The Forge é um control plane local-first. Ele descobre Forges especialistas (Spark Forge, API Forge, …), escolhe o provider certo por capability de forma determinística e explicável e registra cada execução com evidência e receipt verificáveis. **The Forger** é o orquestrador interno.

**Status:** ciclo 2, Waves A–C. Sobre o endurecimento da Wave A (contratos com invariantes semânticas, Forge Protocol resistente a providers adversariais, routing resistente a manipulação, cache do registry fora do workspace, ambiente mínimo para providers, policy de risco com `--approve` e CI em Linux e Windows), a Wave B traz os adapters reais de Spark Forge e API Forge, versão de provider em SemVer, taxonomia de capabilities com aliases e depreciação e uma matriz de compatibilidade testada, e a Wave C traz o contexto v2: tiers (`reference`, `excerpt`, `requested`), negociação de contexto com o provider, revalidação declarada (`context_revalidation`), sinais git somente leitura, cache de fingerprints, perfis (`economy`, `balanced`, `max`) e telemetria por run ([performance](docs/performance.md)). O core continua provado também com o provider nativo `echo-forge` e com providers de teste.

## Instalação (desenvolvimento)

```bash
git clone <repo> the-forger && cd the-forger
python3.11 -m venv .venv                      # qualquer Python >= 3.11
.venv/bin/python -m pip install -e ".[dev]"   # Windows: .venv\Scripts\python
```

O runtime só usa a stdlib. Os comandos são `theforge` e o alias `forge`. Use `theforge` se `forge` colidir com Foundry ou Laravel Forge no seu PATH.

## Primeiros passos

Os comandos abaixo assumem o venv ativado (`source .venv/bin/activate`; no Windows, `.venv\Scripts\activate`). Sem ativar, chame `.venv/bin/theforge` (Windows: `.venv\Scripts\theforge`).

```bash
theforge doctor
theforge init
theforge capabilities list
theforge ask "eco olá" --capability demo.echo
theforge explain <run_id>   # o run_id é impresso por `ask`
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
| 0 | ok / partial |
| 1 | `doctor` / `providers health` com falha |
| 2 | uso inválido ou workspace não inicializado |
| 3 | no_route / ambiguous |
| 4 | provider_failure / refused |
| 5 | falha ao persistir o run |
| 70 | erro interno inesperado (sem traceback) |
| 130 | interrompido (Ctrl+C) |

## Documentação

- [Arquitetura](docs/architecture.md)
- [Forge Protocol v1](docs/protocol.md)
- [Escrevendo um provider](docs/provider-authoring.md)
- [Providers reais: Spark Forge e API Forge](docs/real-providers.md)
- [Capabilities: taxonomia e catálogo](docs/capabilities.md)
- [Versionamento e compatibilidade](docs/versioning.md)
- [Segurança](docs/security.md)
- [CLI](docs/cli.md)
- [Performance](docs/performance.md)
- [ADRs](docs/adr/)
- [Spec do ciclo 1](docs/superpowers/specs/2026-10-02-the-forge-protocol-core-design.md)

## Desenvolvimento

```bash
.venv/bin/python -m pytest            # suite offline
.venv/bin/python -m pytest -m slow    # gates de zero deps e instalação limpa (baixa hatchling)
.venv/bin/python -m pytest -m security   # categoria: unit, contract, integration, e2e, slow, security
.venv/bin/python -m pytest -m real_provider   # Forges reais; ver docs/real-providers.md
.venv/bin/ruff check .
.venv/bin/mypy
.venv/bin/python -m theforge.contracts.schema schemas   # regenerar schemas
```
