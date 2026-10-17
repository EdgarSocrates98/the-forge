# Cycle 11.2 — Native installers (P2-002)

Escopo: forge-doctor-api#65 OPEN (`feat/c11-2-native`) — instalador
nativo `forge/*` fora da wheel → `forge-cli --native` não conseguia
delegar pelo pacote instalado (SKIP honesto).

## Comandos executados

```text
gh pr view 65 --json body,files,state
cat docs/adr/ADR-0006-native-install-cli.md
```

## Decisão — ADR-0006 (accepted, RC exception, 2026-10-17)

Três opções pesadas:

- **A** — script como wheel data + entry point: console script não pode
  mirar data file; launcher teria que subprocessar/runpy o script
  embutido — mesmo problema de import proibido em `src/` + indireção
  extra. Rejeitada.
- **B** — subcomando público de CLI sustentado por código carregado na
  wheel: `forge-doctor-api install` (Typer sub-app) sobre
  `forge_doctor_api.install.service` + `forge_doctor_api._installkit`
  vendored. Mesmo layout que `forge-doctor-data` já shipa; o header do
  installkit nomeia `<pkg>/_installkit.py` como alvo primário de
  vendoring. **Escolhida.**
- **C** — manter instalador source-only: fronteira mais estreita mas
  deixa `--native` permanentemente SKIPPED — o defeito motivador.
  Rejeitada.

## O que a decisão fixa

- `_installkit.py` vendored **byte-idêntico** —
  `test_package_carries_install_surface` prova paridade com
  `scripts/forge_installkit.py` (drift impossível de esconder).
- `install/service.py` carrega `ForgeSpec` + wrappers tipados —
  byte-equivalent a `scripts/forge_install.py` (mesmos verbos, receipts,
  ledger).
- `cli/install_cmd.py`: `forge-doctor-api install {status, doctor,
  install, repair, uninstall, update, mcp-verify}`; scopes
  project/workspace/user; perfis minimal/recommended/full; hosts;
  components; gateway profiles; `--yes`/`--dry-run`.
- Fronteira de pacote: a superfície `install` é a **única** fronteira
  documentada de mutação/processo — `test_boundary.py` ganha allowlist
  `_INSTALL_SURFACE`; `test_install_surface_isolation` prova que o
  scan/engine nunca a importa. subprocess confinado a `kit._spawn` +
  `service.update` (`pip install --upgrade` pinado, sem shell, cap 900s).
- `scripts/forge_install.py` permanece adaptador canônico de checkout.
- argv de delegação documentado para o catálogo do forge-cli:
  `{python} -m forge_doctor_api install …`.

## Gates declarados no PR

`pytest` 1863 passed · ruff · mypy 251 arquivos · contratos CLI/docs
regenerados. Forge-cli **não foi tocado** — adoção do template
`{python} -m forge_doctor_api install` no catálogo fica para depois do
merge/publicação.

## Estado do PR

OPEN em captura (2026-10-17) — files: ADR-0006, `_installkit.py`,
`install/{__init__,service}.py`, `cli/{__init__,catalog,install_cmd}.py`,
`forge.json` (`install_command` → `{python} -m`), goldens
`install-*.txt` ×6, boundary/package/packaging tests, spec
`factory/specs/c11-2-native-install-cli.md`.

## Veredito

IN_PROGRESS — decisão registrada (ADR), implementação completa no PR,
não mergeado; a delegação efetiva pelo catálogo do forge-cli depende de
release publicado (a wheel 0.2.0 no PyPI não carrega o instalador).

## Risco residual

`{python} -m forge_doctor_api install` exige o pacote já instalado —
ordem de bootstrap permanece registry-venv-primeiro. Só doctor-api tem o
padrão; demais Forjas sem installer nativo na wheel seguem SKIPPED
honesto (siblings doctor-data já shipa; the-forge/api-forge/etc. sem
decisão equivalente).
