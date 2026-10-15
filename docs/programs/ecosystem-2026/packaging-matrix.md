# Matriz de empacotamento — ecosystem-2026

Spec: `factory/specs/active/cyc8-02-packaging.md` (§8.7 do prompt-fonte).
Executada em 2026-10-15: build real + instalação em venv isolado + smoke por repo.

## Resultado: 9/9 artefatos construíveis e instaláveis

| Repo | Backend | Artefato | Install limpo | Smoke | Checkout-dep |
|---|---|---|---|---|---|
| the-forge | hatchling | `theforge-0.5.0-py3-none-any.whl` | venv isolado ✓ | `theforge --version` → 0.5.0 | nenhuma |
| api-forge | hatchling | `apiforge-0.1.0-…whl` | ✓ | `apiforge --version` → 0.1.0 | nenhuma |
| platform-forge | hatchling | `platformforge-0.1.0-…whl` | ✓ | `platformforge --version` → 0.1.0 | nenhuma* |
| spark-forge-aws | hatchling | `sparkforge_aws-0.5.0-…whl` | ✓ | `sparkforge-aws --version` → 0.5.0 | nenhuma |
| spark-forge-azure | hatchling | `sparkforge_azure-0.1.0-…whl` (`reproducible=true`) | ✓ | `sparkforge-azure --version` → 0.1.0 | nenhuma |
| forge-doctor-data | poetry-core | `forge_doctor_data-1.0.0rc1-…whl` | ✓ | `forge-doctor-data --version` → 1.0.0rc1 | nenhuma |
| forge-doctor-api | poetry-core | `forge_doctor_api-0.2.0-…whl` | ✓ | `forge-doctor-api --version` → 0.2.0 | nenhuma |
| forge-cli | npm/tsup | `forge-cli-0.1.0.tgz` (188,9 kB, 8 arquivos) | `npm install <tgz>` em prefixo local, sem admin ✓ | `forge-cli` banner + REPL init | nenhuma |
| forge-portal | ng build | `dist/forge-portal-app/browser` (33 arquivos, chunks hashed) | servido por `theforge portal` (backend oficial stdlib) | `curl /` → 200 index.html real | nenhuma |

\* platform-forge: 9 arquivos `docs/` com `/home/edgar` (receipts/SBOM/dogfood) — **não no pacote nem no código**; o wheel é limpo. Gap G-03 rebaixado: é higiene de docs, não bloqueio de release.

## Método (reproduzível)

```bash
# por repo Python:
<venv>/bin/python -m build --wheel --outdir /tmp/pack-matrix/wheels/<repo>
python3 -m venv /tmp/pack-matrix/venvs/<repo>
venvs/<repo>/bin/pip install wheels/<repo>/*.whl   # deps reais do PyPI
venvs/<repo>/bin/<cli> --version

# forge-cli:
npm run build && npm pack
npm install forge-cli-0.1.0.tgz   # prefixo local

# forge-portal:
npm run build                    # dist/forge-portal-app/browser
python scripts/vendor.py         # propaga _forge_portal.py + assets + manifest
theforge portal --port 0         # backend oficial serve o bundle
```

## Portal: bundle ↔ backend oficial

Mecanismo existente, agora exercido de ponta a ponta nesta sessão:

- `forge-portal/scripts/vendor.py` propaga `portal_core/forge_portal.py` +
  assets para os 7 siblings; `--check` reporta byte-parity.
- Integridade: `portal/manifest.json` (`forge/PortalAssets/1`) com
  **sha256 por arquivo** e `portal_version: 1.0.0` — eixo de versão
  independente do `package.json` (0.1.0).
- Estado antes desta run: server em parity, **assets stale** nos 7 repos.
  `vendor.py` re-sincronizou — `--check` agora: `assets: manifest unchanged
  (33 files)` em todos.
- Smoke real: `theforge portal --port 0` → URL com session token; `GET /` →
  200 `text/html` servindo o bundle recém-gerado (SPA fallback ativo).

## Checklist "dependência indevida do checkout" — zerado

- Zero `file:`/`path`/deps de workspace nos 7 `pyproject.toml`.
- `pythonpath`/`mypy_path` são dev-only (pytest/mypy), não vazam ao wheel.
- Wheels `py3-none-any` — sem extensões nativas, portáteis.
- Doctor-data inclui `knowledge/`, `contracts/fixtures`, `portal_assets` no
  wheel via `packages` do poetry — dados empacotados, não lidos do checkout.

## Gaps e decisões abertas

- **Nada publicado**: artefatos são buildáveis/verificáveis, não estão em
  registries — publicação é decisão de produto (⚠ Pending) e exige G-01 (tags).
- **pipx vs uv tool**: canal recomendado pendente — ambos aceitam wheel local;
  decisão é de documentação (cyc10-01).
- **Forge CLI standalone/bundle**: `dist/index.js` único via tsup já permite
  `npx`-style; binário standalone (pkg/bun compile) **rejeitado** pela spec
  salvo justificativa técnica — nenhuma encontrada (node>=20 declarado).
- **Docker**: permanece opcional — nenhum repo o exige; confirmado.
- **Drift pré-existente herdado**: ruff-format (22 arquivos, G-17) e
  `ui/wizard.py` do api-forge (G-18) não foram tocados aqui — pertencem ao
  repo dono, não à matriz de empacotamento.
