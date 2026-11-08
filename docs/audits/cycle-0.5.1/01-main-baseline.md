# Main baseline and evidence boundary

## Commits observados

| repository | branch observed | HEAD | status |
|---|---|---|---|
| the-forge | `docs/cycle-0.5.1-revalidation-20261108` | `6ebb7083eea98bc2808e6d5650aafad2e046abd4` | PASSED |
| forge-agent-bridge | `main` | `1c560542b99c4cb1892e29b9376211341286cf67` | PASSED |
| forge-portal | integrated PR #88 | `324b6287facd45bb4573577410303ca1e0d8600a` | PASSED |
| forge-doctor-api | `main` | `fe99013ed9b5583f655b4b4bb66b59aca58a842c` | PASSED |
| code-atlas-forge | `main` | `19e703aff08b6973afabad683bd261571dfe1b7f` | PASSED |
| api-forge | `main` | `00c458e15190e37c2a5f29a64f626f8efcca3bd7` | PASSED |
| forge-lens | `main` | `86bd7572f2aecce1c84865b964246ae4513bc76b` | PASSED |
| data-sentinel-forge | `main` | `e222af87e0003c88a2de1c6fd83108184ac3c63b` | PASSED |

O workspace possuía artefatos locais de auditorias anteriores; eles foram
preservados e não foram usados como prova nova sem correlação com comando e
commit. O repositório `api-sentinel-forge` não foi criado.

## Ambiente externo

| check | result |
|---|---|
| Docker | PASSED — `29.8.1`, Docker Desktop Linux |
| AWS identity | BLOCKED — `NoCredentials` |
| Azure CLI | NOT_RUN — executável ausente |
| GCloud CLI | NOT_RUN — executável ausente |

Consequentemente, somente evidências locais L1/real-local-engine são usadas para
conclusões de integração.
