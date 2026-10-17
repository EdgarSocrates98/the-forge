# Cycle 10.3 — Wave 6: CI & Security Baseline

## 6.1 Dependency vulnerability audit

Ferramenta: `pip-audit` (resolvendo cada pacote publicado + deps).

| Pacote | Resultado |
|---|---|
| theforge-core | No known vulnerabilities |
| apiforge-af | No known vulnerabilities |
| platformforge | No known vulnerabilities |
| sparkforge-aws | No known vulnerabilities |
| sparkforge-azure | No known vulnerabilities |
| forge-doctor-data | No known vulnerabilities |
| forge-doctor-api | No known vulnerabilities |

npm: `npm audit` em projeto com `theforge-cli@0.1.0` instalado → **0 vulnerabilities**.

**7/7 PyPI + 1/1 npm limpos** na data da auditoria (2026-10-17). Snapshot —
não é garantia futura; dependências novas podem introduzir CVEs depois.

## 6.2 Action pinning (SHA-pin audit)

`uses:` em todos os workflows dos 9 repos — exigência: referência por SHA de
40 hex (exceto actions locais `./`).

| Repo | Actions não pinadas |
|---|---|
| the-forge | 0 |
| forge-cli | 0 |
| forge-portal | 0 |
| api-forge | 0 |
| platform-forge | 0 |
| spark-forge-aws | 0 |
| spark-forge-azure | 0 |
| forge-doctor-data | 0 |
| forge-doctor-api | 0 |

**9/9 repos: 100% das actions SHA-pinnadas.** Sem `uses: actions/checkout@v4`
(tag mutável) em lugar nenhum.

## 6.3 Matriz Python — requires-python vs CI testado

| Pacote | `requires-python` | Matrix CI | Floor coberto? |
|---|---|---|---|
| theforge-core | `>=3.11` | 3.11, 3.12 | sim (floor 3.11 ✓; 3.13 permitido não testado) |
| apiforge-af | `>=3.12` | 3.12 | sim |
| platformforge | `>=3.10` | **3.12 apenas** | **não — 3.10 e 3.11 permitidos e não testados** |
| sparkforge-aws | `>=3.10` | 3.11, 3.12 | **não — 3.10 permitido e não testado** |
| sparkforge-azure | `>=3.10` | **3.12 apenas** | **não — 3.10 e 3.11 permitidos e não testados** |
| forge-doctor-data | `>=3.11` | 3.11, 3.12, 3.13 | sim |
| forge-doctor-api | `>=3.11` | 3.11, 3.12, 3.13 | sim |

### Gap: floor desalinhado em 3 pacotes

`platformforge`, `sparkforge-aws` e `sparkforge-azure` declaram `>=3.10` mas a
CI só exercita 3.11/3.12. Um usuário em Python 3.10 instala o pacote (o
metadata permite) e depende de código nunca testado naquele interpretador —
risco real de `SyntaxError`/API ausente só descoberto em runtime.

Opções por pacote (decisão de produto — não implementado neste ciclo):

1. Ampliar a matrix para incluir o floor declarado (3.10 para pf/sfaws/sfaz).
2. Ou subir `requires-python` para o floor realmente testado (`>=3.12` pf/sfaz,
   `>=3.11` sfaws) — **mudança de metadata = patch release**, já que o
   `requires-python` publicado é o contrato.

`theforge-core`/`apiforge-af` permitem 3.13 sem testar — menor risco (versão
mais nova tende a ser compatível), mas mesmo problema de contrato.

→ Registrado no `gap-register.md` como **G-MATRIX-1** (patch candidato para
os 3 pacotes com floor não coberto — decidir opção 1 vs 2).

## 6.4 Workflows de release — postura OIDC

Confirmado na main de todos os 7 repos Python: `publish-pypi.yml` presente,
`if: true`, `permissions: id-token: write`, `pypa/gh-action-pypi-publish`
SHA-pinado, attestation PEP 740 habilitada. forge-cli: `publish-npm.yml`
idêntico (`--provenance`). Publicar = `workflow_dispatch` (ato humano).

## 6.5 Veredito Wave 6

`CONDITIONALLY_VERIFIED` — supply-chain local limpo (0 vulns conhecidas,
pinning 100%, OIDC sem tokens armazenados). A ressalva material é a matriz
Python: 3 pacotes vendem um contrato (`>=3.10`) que a CI não testa.
