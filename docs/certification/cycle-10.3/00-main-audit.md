# Cycle 10.3 — Fase Zero: Auditoria das mains

Data: 2026-10-16. Escopo: 9 repositórios + PyPI + npm + GitHub Releases.
Método: `git` local + PyPI JSON API + npm registry + GitHub Releases API + comparação sha256.

## 1. Baseline dos nove HEADs (CI nos HEADs atuais)

| Repo | main HEAD | versão | tag | tag SHA | CI main |
|---|---|---|---|---|---|
| the-forge | `8029099` | `theforge-core` 0.5.0 (py≥3.11) | v0.5.0 | `cd6058fd` | success |
| forge-cli | `7c7fbd1` | `theforge-cli` 0.1.0 (node≥20) | v0.1.0 | `53e44221` | success |
| forge-portal | `55e01d5` | vendored (no dist) | v0.1.0 | `55e01d5` | success |
| api-forge | `4e5bc7c` | `apiforge-af` 0.1.0 (py≥3.12) | v0.1.0 | `4c95613f` | success |
| platform-forge | `9e7ee3b` | `platformforge` 0.1.0 (py≥3.10) | v0.1.0 | `fd68e672` | success |
| spark-forge-aws | `db28a92` | `sparkforge-aws` 0.5.0 (py≥3.10) | v0.5.0 | `bf5f108d` | success |
| spark-forge-azure | `51e366c` | `sparkforge-azure` 0.1.0 (py≥3.10) | v0.1.0 | `620e698e` | success |
| forge-doctor-data | `b105ada` | `forge-doctor-data` 1.0.0 (py≥3.11) | v1.0.0 | `c799ecae` | success |
| forge-doctor-api | `ca2df7b` | `forge-doctor-api` 0.2.0 (py≥3.11) | v0.2.0 | `80918a61` | success |

Tags apontam SHAs anteriores aos HEADs — esperado (merges pós-release:
workflows OIDC, docs, rebinding). §8.1: ambos registrados. Nenhuma divergência
tag→HEAD indica problema por si só; o que importa é tag↔artefato (§2 abaixo).

## 2. Verificação dos registries (PyPI JSON API + npm + comparação de hash)

Cadeia §2.2 do prompt: **source → tag → artifact → registry → installed runtime.**

| Pacote | PyPI | requires-python | files | GH assets | wheel hash PyPI==GH | sdist hash PyPI==GH |
|---|---|---|---|---|---|---|
| `theforge-core` | 0.5.0 | >=3.11 | whl+sdist | whl+sdist+SUMS | ✅ | ❌ **sdist difere** |
| `apiforge-af` | 0.1.0 | >=3.12 | whl+sdist | `apiforge-0.1.0.*` (**nome antigo**) | n/a | n/a |
| `platformforge` | 0.1.0 | >=3.10 | whl+sdist | whl+sdist+SUMS | ✅ | ✅ |
| `sparkforge-aws` | 0.5.0 | >=3.10 | whl+sdist | whl+sdist+SUMS | ✅ | ✅ |
| `sparkforge-azure` | 0.1.0 | >=3.10 | whl+sdist | whl+sdist+SUMS | ✅ | ✅ |
| `forge-doctor-data` | 1.0.0 | >=3.11 | whl+sdist | whl+sdist+SUMS | ✅ | ✅ |
| `forge-doctor-api` | 0.2.0 | >=3.11 | whl+sdist | whl+sdist+sbom+2×SUMS | ✅ | ✅ |
| `theforge-cli` | npm 0.1.0 | node>=20 | tgz+dist bin | tgz+SUMS | ✅ (install limpo verificado) | — |

Instalação limpa dos 7 PyPI + npm já verificada nesta sessão (venvs isoladas,
`--version`/`--help` OK — ver `test-evidence.md` quando consolidado).

## 3. Classificação (§2.3)

| Superfície | Estado |
|---|---|
| 7 dists PyPI publicadas e instaláveis | VERIFIED_FROM_REGISTRY |
| npm `theforge-cli` | VERIFIED_FROM_REGISTRY |
| GitHub Releases (tags, assets, SUMS) | RELEASED (ver divergências G1/G2) |
| CI nos 9 HEADs | TESTED — success |
| OIDC trusted publishing (7 repos) | INTEGRATED — `if: true` nas mains; 3 projetos publicaram via OIDC |
| Portal servido da wheel | TESTED (sessão anterior; revalidar Wave 4) |
| forge-cli install path | PARTIAL — **clone-only**, sem caminho pip/registry (§5.6 Wave 3) |
| Metadados PyPI de 3 pacotes | PARTIAL — sem classifiers/project_urls (G3) |

## 4. Gaps encontrados (severidade / causa-raiz / correção)

### G1 — P1 — api-forge: release GitHub carrega artefatos do nome antigo
- **Causa**: tag `v0.1.0` (`4c95613f`) é pré-rename (`name = "apiforge"`);
  PyPI `apiforge-af` foi publicado via OIDC a partir de commit pós-tag.
- **Impacto**: GH release e PyPI descrevem código diferente; §3.3 exige
  documentação explícita ou realinhamento.
- **Correção proposta**: patch release `v0.1.1` taggeado em commit com
  `apiforge-af` (ou `v0.1.0` doc + rebuild de assets — preferir patch).
  Decisão do mantenedor (SemVer/renomear ≠ bugfix? — reclassify como release
  normal 0.1.1 com nota de rename).

### G2 — P1 — the-forge: sdist PyPI ≠ sdist GitHub Release
- **Causa provável**: sdist do GH release foi buildado no commit do tag;
  o do PyPI saiu do workflow OIDC em commit posterior (branch pré-merge —
  `publish-pypi.yml` rodou na branch do PR). Wheel bate (payload idêntico);
  sdist inclui arquivos extras que divergem entre commits.
- **Impacto**: `pip download --no-binary :all:` produz árvore ≠ release doc;
  checksums públicos de sdist inconsistentes.
- **Correção**: (a) investigar diff dos sdists; (b) publicar patch 0.5.1 a
  partir de main alinhada, ou documentar explicitamente (§3.3).

### G3 — P2 — metadados PyPI ausentes em 3 pacotes
- `theforge-core`, `apiforge-af`, `forge-doctor-api`: **zero classifiers,
  zero project_urls** no JSON do PyPI (Hatchling/pyproject sem a seção
  correspondente). platformforge/sparkforges/doctor-data têm.
- **Correção**: acrescentar `classifiers` + `[project.urls]` (Homepage,
  Repository, Issues, Documentation, Changelog) nos 3 pyprojects → entra no
  patch release.

### G4 — P2 — forge-doctor-data 1.0.0 GA com classifier "Development Status :: 3 - Alpha"
- Incoerência semântica flagged pelo §4.5 do prompt. `platformforge`/
  `sparkforge-aws` são Beta; `sparkforge-azure` Alpha (0.1.0 — coerente).
- **Decisão (mantenedor)**: 1.0.0 + 2668 testes + rc-baseline ⇒ Beta ou
  Production/Stable. Não subir só pela numeração — avaliar maturidade real
  (critério: contratos congelados + baseline + evals → justifica Stable?).

### G5 — P2 — forge-cli: caminho de instalação é clone-only
- `repos.ts` só tem `url` GitHub + `nativeInstall` do source; `pip` é apenas
  prereq check. §5.6 do prompt pede instalação pública sem obrigatoriedade
  de `git clone`.
- **Correção**: spec pip-path (PyPI dists já existem) — item de Wave 3,
  provável patch `theforge-cli` 0.2.0.

### G6 — P3 — forge-doctor-api release: `SHA256SUMS` + `SHA256SUMS.txt` duplicados
- Cosmético; consolidar num só nome canônico (`SHA256SUMS.txt`).

### G7 — P3 — classifiers `Development Status` ausentes vs. Alpha (ver G3/G4)
- Unificar política de classifiers entre os 7 pacotes.

## 5. Evidências

- PyPI JSON API consultada em 2026-10-16 para os 7 projetos.
- GitHub Releases API: assets + SHA256SUMS baixados e comparados.
- npm registry JSON: `theforge-cli@0.1.0`, `engines.node>=20`, `bin.forge-cli`.
- `git`: SHAs/tags/ancestors verificados localmente.
- CI: `gh run list --branch main` — último run por repo = success.

## 6. Ação imediata

Prosseguir Wave 1 (registry deep-verify: download+install+CLI por pacote,
provenance/attestations) e Wave 2 (metadata polish). Patches candidatos:
api-forge 0.1.1 (G1), the-forge 0.5.1 (G2/G3), forge-doctor-data 1.0.1 (G3/G4),
forge-doctor-api 0.2.1 (G3), theforge-cli 0.2.0 (G5 — após spec).
