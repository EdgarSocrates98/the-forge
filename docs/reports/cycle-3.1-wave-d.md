# Cycle 3.1 — Wave D: adapters Forge Doctor Data + Forge Doctor API

Escopo: Phases 9–12 e 34 do `prompt_evo_cycle3_1.md`. Dois providers novos sob o
Provider SDK — **zero mudanças no core** (Phase 34): os Doctors entram como
distribuições `theforge_doctordata`/`theforge_doctorapi`, stdlib-only, instaladas
no interpretador de cada especialista, falando Forge Protocol v1.

## O que mudou

- **`theforge_doctordata` 0.2.0** (`forge-doctor-data`, compat `>=1.0.0rc1,<2.0.0`):
  - `data.scan`/`analyze` via seam público `accept_request` (`kind=scan`) do
    `forge_doctor_data.core.forger` — HandoffBundle `forge-contracts/1` vira
    artefato nativo + findings/evidence/unknowns no barramento do Forge.
  - `data.verify`/`verify` via `check_conformance` (`core.conformance`) —
    veredito de conformidade do bundle staged, evidência com hash do payload
    verificado (não do artefato do veredito).
  - Grafo de plataforma (entidades/relações) fica íntegro no artefato; o barramento
    recebe resumo `observed` + contagem por domínio — sem fundir grafo estrangeiro.
  - `project.root` sanitizado no artefato (sem path de máquina); o bundle inteiro
    de capabilities do registry vira resumo + unknowns agregados por domínio.
- **`theforge_doctorapi` 0.2.0** (`forge-doctor-api`, compat `>=0.2.0,<0.3.0`):
  - `api.diagnose`/`analyze` via `DoctorBoundary.handle` + `endpoint_dict` do
    `forge_doctor_api.handoff.boundary` (spec 070) — emite ApiHandoffBundle v2 +
    envelope `ForgeHandoff` + `diagnostic-manifest`.
  - `api.verify`/`verify`: strict parse (`ApiHandoffBundle.from_dict`,
    `ForgeHandoff.parse`) + integridade `handoff_id == body_sha256()` (v2).
  - Tradução: findings → `Finding`; `DERIVED` → `inferred`; demais observações →
    `observed`; remediation candidates → `proposed` (nunca `observed`);
    unknowns preservam `subject`/`missing`/`resolve:`; refs/handoff/manifest viram
    evidência de run. Grafo completo só no artefato.
  - `payload.options.bounded` → bridge `--bounded` (economia de contexto).
- **Arquitetura** (ambos): bridge filho (`python -m <adapter>._bridge`) é o único
  módulo que importa o especialista — isolamento do `run_native`, env sem
  credenciais + `PYTHONIOENCODING=utf-8` (corrige corrupção cp1252 no Windows);
  erros nativos tipados `FDD-*`/`FDA-*` (`REQUEST-INVALID` → `refused`, exit 2;
  `NATIVE-FAILURE` → `error`, exit 1); artefato canônico em `native/handoff.json`;
  stage só com entradas verificadas; replay total sem especialista.
- **Fixtures**: `tests/fixtures/native/{doctordata,doctorapi}/` com `default/`
  (environment + health + recordings reais) e `scenarios/{specialist-missing,
  boundary-missing, version-skew, native-error}` — determinísticos, sem CRLF nem
  paths de máquina. Workspace `tests/fixtures/workspaces/data/shop/` (dbt+DAG)
  para o scan do Doctor Data.
- **Health local-only**: python ≥ 3.11 → import do especialista → janela de versão
  (`degraded` em skew) → descoberta do boundary sem importá-lo → `unavailable`
  em ausência.
- **Harness real-provider**: `real_providers.py` + `test_real_providers.py` +
  `test_real_providers_env.py` cobrem os quatro Forges
  (`THEFORGE_REAL_{SPARKFORGE,APIFORGE,DOCTORDATA,DOCTORAPI}_PYTHON`,
  `THEFORGE_REAL_PROVIDERS_REQUIRED`): drift live↔recorded, snapshot drift, ids,
  containment, skew e indisponibilidade. Recorders ganharam `--out`.
- **`mypy`**: `mypy_path`/`files` estendidos aos dois adapters; overrides
  `ignore_missing_imports` para `forge_doctor_data.*`/`forge_doctor_api.*`
  (especialistas nunca instalados no env do core).
- **Catálogo**: `docs/capabilities.md` + `test_capability_catalog_doc.py` cobrem
  as 4 capabilities novas (21 total); `test_adapter_shell.py` pin `0.2.0` — os
  quatro adapters nascem já na superfície de manifest do Wave B.
- **Docs**: `docs/real-providers.md` (4 providers, env vars, replay, health,
  boundaries, troubleshooting), `docs/protocol.md` (famílias `FDD-*`/`FDA-*`,
  `DOCTOR*-ADAPTER-*`), READMEs dos dois adapters.

## Fix upstream necessário (repo forge-doctor-api)

`ApiHandoffBundle.from_dict` falhava em runtime: `DeltaContext` estava sob
`TYPE_CHECKING` mas `Model.from_dict` chama `get_type_hints` (resolve anotações
em runtime) → `NameError`. Fix com regression test: PR
[#13](https://github.com/EdgarSocrates98/forge-doctor-api/pull/13) **mergeado**
(`035b635` na main). RC discipline honrada: root cause + teste, sem bump de
versão, sem mudança de contrato. O `api.verify` do adapter passou a retornar
`"integrity": "ok", "valid": true` no bundle real.

## Gates (local — GitHub CI fora de cota)

- Focados: `test_adapter_doctordata.py` + `test_adapter_doctorapi.py` — **65 pass**.
- `test_adapter_shell.py` (4 adapters), `test_capability_catalog_doc.py`,
  `test_real_providers*.py` — verdes (1 skip = real providers não obrigatórios).
- `ruff check .`: limpo. `mypy` (src + scripts + 4 adapters): limpo.
- Smoke real `.venv-dd`: `data.scan` → 74 findings/8 entidades (vs. local: −3
  findings GIT, corretos — stage sem `.git`); `data.verify` → conformidade ok.
- Smoke real `.venv-da`: `api.diagnose` → 7 findings/22 evidências/15 unknowns
  (authz, paginação, security evidence); `api.verify` → integridade ok.
- forge-doctor-api (repo irmão): **1701 pass, 40 skip** (extras MCP/GraphQL),
  ruff limpo, `integrity: ok` no verify.

## Decisões

- Bridge filho em vez de CLI nativa: os Doctors não expõem verbos que emitem o
  bundle cru; o boundary público (spec 070 / `forger`) é o seam projetado — o
  subprocess herda o isolamento, timeouts e scrub de env do `run_native`.
- `data.verify`/`api.verify` amarram evidência ao **payload staged** —
  `location.path` + `hash` do item do ContextPack verificado. Evidência derivada
  do artefato (`handoff-envelope`, `platform-graph`, `service-graph`,
  `domain-hashes`) **não** carrega `hash`: por protocolo `Evidence.hash` só
  existe com `location` de pack; a proveniência do artefato fica em
  `artifacts[].sha256`.
- Remediation candidates nunca viram `observed` — são `proposed` (evidência
  proposta, não fato observado).
- `PYTHONIOENCODING=utf-8` no env nativo + bytes UTF-8 no `stdout.buffer` do
  bridge — cp1252 do Windows corrompia saída com `§`.
- 1.0.0rc1 parseado com sufixo rc no `in_window` (SemVer pré-release).

## Gaps / próximos passos

- `api.change-control` segue `hand-built` (recusa legítima do gravador por path
  de máquina) — destrava quando o verbo portabilizar paths.
- Doctors ainda não plugados nos pipelines observe→engineer nem nas relações
  `can_verify`/`consumes` do grafo — Waves E/F.
- CI do GitHub indisponível (cota esgotada): gates locais são a evidência.
