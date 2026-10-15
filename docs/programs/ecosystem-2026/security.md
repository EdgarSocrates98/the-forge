# Supply chain — ecosystem-2026

Spec: `factory/specs/active/cyc8-03-supply-chain.md` (§8.8 do prompt-fonte).
Evidência gerada em 2026-10-15 a partir dos artefatos reais da cyc8-02.

## O que existe agora

| Controle | Estado | Evidência |
|---|---|---|
| Hashes SHA-256 por artefato | **real** | `supply-chain/SHA256SUMS.txt` — 7 wheels + tarball npm + `forge/PortalAssets/1` manifest |
| SBOM por pacote Python | **real** | `supply-chain/sbom/<repo>.cdx.json` — CycloneDX do **ambiente instalado** (deps resolvidas), gerado por `cyclonedx-py environment` |
| Inventário de deps npm (CLI) | **real** | `supply-chain/sbom/forge-cli-deps.json` — `npm ls --all` (307 deps) |
| Integridade do bundle Portal | **real** (preexistente) | `forge/PortalAssets/1` — sha256 por arquivo em `portal/manifest.json` |
| Vuln scan | **real** | `supply-chain/audit/` — pip-audit ×7 venvs + npm audit (forge-cli) |
| Verificação de licenças | **real** | relatório abaixo — `importlib.metadata` por venv |
| Dependency-confusion protection | **parcial** | `forge-cli/.npmrc` fixa `registry.npmjs.org`; pip: política documentada abaixo |
| Assinatura de artefatos | **pendente ⚠** | sigstore vs gpg — decisão de produto registrada na spec |
| Proveniência de build | **parcial** | `forge/PortalAssets/1` para o bundle; wheels: sdist/wheel reproduzível só no spark-forge-azure (`reproducible=true`); provenance formal depende do pipeline CI (cyc8-04) |

## Findings (registrados, não contornados)

### F-01 · api-forge: `cryptography` pinned sob fixes disponíveis — **resolvido 2026-10-15**

- `api-forge` declarava `cryptography>=43,<47` → resolvia **46.0.7** com
  **4 CVEs** (`PYSEC-2026-3552/3553/3554`, `GHSA-537c-gmf6-5ccf`), todos
  com fix fora do range (`48.0.1`, `49.0.0`, `50.0.x`).
- **Bump aplicado 2026-10-15** sob instrução do usuário ("trate todos os
  warnings e gaps"): pin agora `cryptography>=50,<51` em
  `api-forge/pyproject.toml` → resolve **50.0.2**.
- Uso de `cryptography` no api-forge é somente Ed25519
  (`src/apiforge/report/keys.py`) — API estável entre majors.
- **Evidência**: `supply-chain/audit/api-forge.json` regenerado —
  zero vulns em `cryptography` (único restante: `pip` bundled do venv de
  auditoria, ruído de ambiente, não dependência do artefato).
- Verificação: install da nova linha em venv limpo + `keys.py` importa +
  110 testes `keys`/`report` verdes (2 skipped, pytest 2026-10-15).

### F-02 · Metadados/arquivos de licença

| Repo | LICENSE file | `license=` no manifesto | Estado |
|---|---|---|---|
| the-forge | **ausente** | `MIT` (text) | declara sem arquivo — completar |
| forge-portal | **ausente** | nenhum | sem licença — decisão do dono |
| forge-doctor-api | **ausente** | nenhum | sem licença — decisão do dono |
| demais 6 | presente | MIT/declarado | ok |

Deps de terceiros: 100% permissivas (MIT/BSD-2-Clause/ISC/Apache-2.0/PSF-2.0) —
zero copyleft nos ambientes instalados. `markdown-it-py`, `mdurl`, `tree-sitter`
aparecem como UNKNOWN por metadados antigos, mas declaram MIT via classifier —
não é risco, é higiene de metadados upstream.

### F-03 · ruído de ambiente (não é finding)

- pip-audit reporta `pip` vulnerável em todos os venvs — é o **pip bundled**
  do `python3 -m venv`, não dependência dos artefatos. Excluído dos findings.
- forge-cli `npm audit`: **1 vuln `low`** (307 deps) — abaixo do limiar da
  política, registrado para acompanhamento.

## Política de severidade (requisito da spec — política antes de gate)

- **Blocker**: vuln `critical`/`high` em dependência **declarada** do artefato,
  sem fix disponível dentro do pin → bloqueia release candidate; com fix
  disponível dentro do pin → bump obrigatório antes de publicar.
- **Warn**: `moderate`/`low`, ou vuln em dependência transitiva fora do
  controle de pin → registrado em `audit/`, revisado por release.
- **Ignore**: findings em toolchain de ambiente (pip/setuptools do venv) —
  não são deps do artefato.
- F-01 classifica como **Blocker** (fixes existem mas fora do pin → decisão
  de bump pendente no repo dono).

## Dependency-confusion

- **npm**: `forge-cli/.npmrc` fixa `registry=https://registry.npmjs.org/` —
  sem fallback silencioso; pacote é unscoped (risco interno baixo).
- **pip**: instalações de release devem fixar `--index-url https://pypi.org/simple`
  (ou mirror interno declarado) — incorporado à política de release da cyc8-04;
  o core the-forge é stdlib-only, exposição é dev/CI.
- Vendored code (`_forge_portal.py`, installkit, ui kit) é protegido por
  byte-parity + `forge/PortalAssets/1` sha256 — não passa por registry.

## Reproduzir

```bash
python3 -m venv /tmp/sc && /tmp/sc/bin/pip install pip-audit cyclonedx-bom
# por repo com venv de instalação limpa:
/tmp/sc/bin/cyclonedx-py environment <venv>/bin/python --of JSON -o <repo>.cdx.json
/tmp/sc/bin/pip-audit --path <venv>/lib/python3*/site-packages -f json -o <repo>.audit.json
# npm:
cd forge-cli && npm audit --json && npm ls --json --all
# hashes:
sha256sum wheels/*/*.whl forge-cli-0.1.0.tgz the-forge/portal/manifest.json
```
