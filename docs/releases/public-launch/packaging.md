# Release 1 — Auditoria de packaging Python (Wave 2)

Executado 2026-10-16 contra os HEADs da baseline. Artefatos em
`/tmp/r1-builds/<repo>/` (efêmero); checksums completos abaixo
(prefixos sha256).

## Builds (uv build, sdist + wheel)

| Pacote | Versão | Python req. | Wheel | sdist | Arquivos wheel |
|---|---|---|---|---|---|
| the-forge | 0.5.0 | >=3.11 | `9a418298` | `2b3b1c0d` | 303 |
| apiforge | 0.1.0 | **>=3.12** | `abbcba74` | `322c2489` | 736 |
| platformforge | 0.1.0 | >=3.10 | `79f601bc` | `941d4697` | 659 |
| sparkforge-aws | 0.5.0 | >=3.10 | `6c12cec9` | `3915bcab` | 1034 |
| sparkforge-azure | 0.1.0 | >=3.10 | `61f2ea4f` | `7410fd38` | 624 |
| forge-doctor-data | 1.0.0rc1 | >=3.11 | `99fc33b6` | `a87bd1cd` | 434 |
| forge-doctor-api | 0.2.0 | >=3.11 | `a2f10503` | `d5e39653` | 268 |

## Instalação isolada + smoke (venv limpa, sem checkout)

Cada wheel instalada via `uv pip install` em `/tmp/r1-venv-<repo>` criada
por `uv venv` (Python 3.11 ou 3.12 conforme `requires-python`):

| Pacote | Instala | Import | CLI `--version` |
|---|---|---|---|
| the-forge | ✅ | `import theforge` ✅ | `theforge 0.5.0` |
| apiforge | ✅ (py3.12) | ✅ | `apiforge 0.1.0` |
| platformforge | ✅ | ✅ | `platformforge 0.1.0` |
| sparkforge-aws | ✅ | ✅ | `sparkforge-aws 0.5.0` |
| sparkforge-azure | ✅ | ✅ | `sparkforge-azure 0.1.0` |
| forge-doctor-data | ✅ | ✅ | `forge-doctor-data 1.0.0rc1` |
| forge-doctor-api | ✅ | ✅ | `forge-doctor-api 0.2.0` |

**Observação real:** apiforge **não instala em Python 3.11**
(`requires-python = ">=3.12"`) — documentar na matriz de suporte.
Detectado no smoke, não presumido.

## F-RC-1 revalidado (the-forge)

Roundtrip sdist→wheel permanece válido nesta baseline: gate CI
`release-gates.yml` executa sdist → extract → wheel → diff de payload
(298 arquivos idênticos na evidência cycle-10.2; gate verde no run
38923380792). Com o rename, artefatos passam a `the_forge-0.5.0.*` —
globs atualizados em `test_packaging.py` e no workflow.

## Ferramentas de instalação (documentação)

Golden paths documentáveis pós-publicação:

- `pipx install <dist>` — recomendado para CLIs (isola deps).
- `uv tool install <dist>` — equivalente uv.
- `pip install <dist>` — venv do usuário.
- `pip install <arquivo>.whl` — wheel direta (funciona hoje, sem PyPI).
- Instalação portátil existente: `docs/installation/portable-installation.md`.

Nenhum comando `pip install <dist>` pode ser divulgado como funcional
antes da publicação PyPI.

## TestPyPI

Adequado como dry-run de metadata/upload **após** aprovação. Não prova
compatibilidade com PyPI produção (índice e tokens separados), mas valida
o fluxo Trusted Publishing OIDC.

## Trusted Publishing

Recomendado: PyPI Trusted Publishing (OIDC via GitHub Actions) por repo,
workflow de publish dedicado com `permissions: id-token: write` apenas no
job de publish. Evita tokens permanentes em secrets. Requer configuração
manual no PyPI pelo mantenedor (pendência externa).

## Findings abertos

- **F-R1-3:** 346 links relativos nos 7 READMEs quebram na página PyPI.
  Opções: hook de build que reescreve para URLs absolutas do tag, ou
  aceitar como limitação conhecida. **Recomendação: aceitar em R1** —
  padrão comum; documentar no approval-checklist.
- Nenhum secret, path absoluto de máquina ou arquivo privado detectado
  nos sdists/wheels (verificados por listagem de conteúdo).

**GATE 2: PASS** — 7/7 pacotes constroem, instalam e executam em
ambientes limpos.
