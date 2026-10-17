# Cycle 10.3 — Wave 1: Verificação de registries

Data: 2026-10-16. Método: PyPI JSON API → download → sha256 → venv limpa → CLI.
Sem checkout local na cadeia de prova.

## 1. Hashes registry (§3.1.8)

14/14 arquivos baixados do PyPI batem o `digests.sha256` publicado:

| Pacote | wheel | sdist |
|---|---|---|
| theforge-core 0.5.0 | OK | OK |
| apiforge-af 0.1.0 | OK | OK |
| platformforge 0.1.0 | OK | OK |
| sparkforge-aws 0.5.0 | OK | OK |
| sparkforge-azure 0.1.0 | OK | OK |
| forge-doctor-data 1.0.0 | OK | OK |
| forge-doctor-api 0.2.0 | OK | OK |

## 2. Instalação limpa das wheels baixadas (§3.1.9–10)

Cada wheel instalada numa venv nova (pip resolveu dependências do registry):

| CLI | Resultado |
|---|---|
| `theforge` | `theforge 0.5.0` + `portal --help` OK |
| `apiforge` | `apiforge 0.1.0` |
| `platformforge` | `platformforge 0.1.0` |
| `sparkforge-aws` | `sparkforge-aws 0.5.0` |
| `sparkforge-azure` | `sparkforge-azure 0.1.0` |
| `forge-doctor-data` | `forge-doctor-data 1.0.0` |
| `forge-doctor-api` | `forge-doctor-api 0.2.0` |

## 3. npm (§3.2)

- `theforge-cli@0.1.0`: `dist.integrity` sha512 presente no registry;
  `engines.node >= 20`; `bin.forge-cli = dist/index.js`.
- `npx theforge-cli doctor`: executa o CLI real — banner, modelo
  `forge-health/v1`, checks com evidência (home/tmpdir etc.).
- Lifecycle completo (install/update/repair/uninstall de Forjas): Wave 3.

## 4. GitHub Releases (§3.3)

Verificado na Fase Zero — resumo:

- 8/9 releases têm wheel+sdist+SHA256SUMS; forge-doctor-api adiciona
  `sbom.cdx.json` (e `SHA256SUMS`/`SHA256SUMS.txt` duplicados — G6).
- Hash PyPI↔GH: **5/7 com wheel+sdist idênticos**; `theforge-core` sdist difere
  (G2 — build em commit distinto); `apiforge-af` assets GH carregam o nome
  antigo `apiforge-0.1.0.*` porque o tag é pré-rename (G1).
- forge-portal v0.1.0: sem artefatos por design (vendored no wheel core).
- forge-cli v0.1.0: `theforge-cli-0.1.0.tgz` + checksums.

## 5. Provenance (§3.4)

Endpoint `pypi.org/integrity/<pkg>/<ver>/<file>/provenance`:

| Pacote | attestations |
|---|---|
| theforge-core | 1 bundle — **verificável** (publicado via OIDC) |
| apiforge-af | 1 bundle — **verificável** (OIDC) |
| forge-doctor-api | 1 bundle — **verificável** (OIDC) |
| platformforge | 404 — sem attestation (publicado por token) |
| sparkforge-aws | sem attestation (token) |
| sparkforge-azure | sem attestation (token) |
| forge-doctor-data | sem attestation (token) |

Honesto: provenance criptográfica existe **só** nos 3 projetos publicados
via OIDC. Os 4 por token têm integridade por hash, não provenance de build.
Próximas releases dos 4 (publishers já registrados) saem com attestation.

## 6. Veredito

`VERIFIED_FROM_REGISTRY` para os 8 pacotes. Pendências: G1 (apiforge GH
release stale), G2 (theforge sdist divergente), G3 (metadados), G6
(SHA256SUMS duplicado). Nenhuma é instalabilidade-blocking — todas viram
candidatos a patch (Wave 10).
