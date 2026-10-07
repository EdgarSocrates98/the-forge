# Cycle 3.1 — relatório de fechamento

- Branch: `feat/cycle3.1` (PR #6)
- Fonte de requisitos: `prompt_evo_cycle3_1.md` (arquivo local, fora do git por `.gitignore`)
- Relatórios de wave: [audit](cycle-3.1-audit.md), [B](cycle-3.1-wave-b.md), [C](cycle-3.1-wave-c.md), [D](cycle-3.1-wave-d.md), [E](cycle-3.1-wave-e.md), [F](cycle-3.1-wave-f.md), [G](cycle-3.1-wave-g.md), [H](cycle-3.1-wave-h.md), [I](cycle-3.1-wave-i.md), [J](cycle-3.1-wave-j.md)

## Baseline

Ponto de partida: `main` no merge do Cycle 3 (`4d75818`), com a auditoria de
realidade do Wave A corrigindo o que o ciclo anterior assumia. 55+ commits em
waves independentemente commitadas (A–J), cada uma com gates locais verdes.

## CI status

**GitHub Actions indisponível: cota da conta esgotada** — informado pelo
responsável. Workflows novos (`provider-surface-drift.yml`,
`release-compat.yml`, `ecosystem-real.yml`) são revisáveis mas não rodaram.
Todos os gates foram executados localmente: `pytest` (3574 testes coletados),
`ruff check .`, `mypy src`, `python -m build`, `check_zero_deps.py`,
`fresh_install.py`, benchmark com baseline e budget, e a suíte
`real_provider` obrigatória (`THEFORGE_REAL_PROVIDERS_REQUIRED=1`).

## Version changes

| componente | versão |
|---|---|
| theforge | 0.2.0 |
| theforge-sparkforge-adapter | 0.3.0 |
| theforge-apiforge-adapter | 0.3.0 |
| theforge-doctordata-adapter | 0.3.0 |
| theforge-doctorapi-adapter | 0.3.0 |

Matriz de compatibilidade atualizada em [versioning.md](../versioning.md)
(linha 0.2.0): sparkforge-aws `>=0.5.0,<0.6.0`, apiforge `>=0.1.0,<0.2.0`
(py3.12), forge-doctor-data `>=1.0.0rc1,<2.0.0`, forge-doctor-api
`>=0.2.0,<0.3.0`.

## Adapter surface changes

- `theforge/ProviderSurfaceIdentity/v1`: versões pareadas com dois
  fingerprints (manifest sha256 + surface fingerprint) computados do manifest
  em uso — `version` deixou de ser identidade.
- Rename upstream absorvido: pacote `sparkforge` → `sparkforge_aws`, CLI
  `sparkforge` → `sparkforge-aws`; o resolver (`native_pkg.py`) aceita ambos
  com fallback pré-rename, e `live_unavailable_reason` probeia pelo resolver
  (bug real corrigido).
- Manifests ganharam `features` (`handoff/v1`, `verify/v1`, `delta/v1`, …) e
  `capabilities[].relations` (`produces`/`consumes`/`requires`/`complements`/
  `conflicts`/`can_verify`/`can_review`).
- `record --check` de 3 vias (`same`/`additive`/`breaking`) nos 4 adapters —
  o classificador do drift gate.

## Doctor integrations

Dois adapters novos (`adapters/doctordata`, `adapters/doctorapi`) via Provider
SDK, zero código de domínio no core: subprocesso `describe`/`health`/`execute`
com bridge filho que usa só seams públicos (`accept_request`/
`check_conformance` no Data; `DoctorBoundary`/handoff no API). O documento
nativo (`forge-contracts/1`) atravessa como artefato `native/handoff.json`
declarado e hasheado; tradução epistêmica lossless — `Confidence.UNKNOWN`
exige `unknowns`, a confiança nativa aparece em `limitations`.

## Authority model

Hierarquia documentada e testada ([architecture.md](../architecture.md),
[security.md](../security.md)): The Forge coordena (WHO/WHEN/HOW); Doctors
observam; specialists engenheiram. Saída de provider é dado — nunca instrução:
claims de routing/policy em resultados são inertes, `manifest.trust` não
altera o trust do registry, proveniência forjada (`derived_from`, refs fora
do namespace permitido) é rejeitada.

## Contract convergence

`forge/v1` como envelope único; fragmentos versionados: `handoff/v1`,
`verify/v1`, `plan-proposal/v1`, `resolve/v1`, `semantic-handoff/v1`,
`economy-receipt/v1`, `trace-ref/v1`, `resume/v1`, `delta/v1`, `graph-refs/v1`.
`ref` ganhou a forma `scheme:opaque` validada (`check_ref`) com `pattern`
propagado ao JSON Schema. Todos os contratos regeneram `schemas/` via
`python -m theforge.contracts.schema schemas` (teste de drift em CI).

## Graph federation

`CapabilityGraph` derivado de manifests + descritor do workspace — arestas
declaradas e observadas, cada uma com status epistêmico e evidência,
ordenação determinística, refs não resolvidos visíveis. `theforge graph
--mesh` renderiza a malha por domínio (`observe`/`engineer`/`verify`),
posicionando verificação pelo domínio declarado do verificador ∩ do alvo;
`unplaced` só para relações genuinamente sem candidato.

## Economy federation

`ProviderEconomyReceipt` + `EconomyRollup` (`theforge/.../v1`, Wave F):
métricas com `MetricStatus` de 4 estados (`unknown` ≠ `zero` ≠
`not_applicable`), rollups honestos (só soma o medido), artefato `economy`
no run de plano, seção `Economy:` no explain e `economy_sha256` nos refs.

## Trace federation

`NativeTrace` (pointer limitado ref+summary — spans internos nunca saem do
especialista), `native_trace_ref` linkando o span do nó à trace nativa,
`RunTelemetry` persistido por run e renderizado no explain.

## Security

Modelo de ameaças da federação em [security.md](../security.md) +
`tests/test_federation_adversarial.py` (20 casos): routing-instruction como
dado, proveniência forjada, drift de superfície, tampering de receipt
aninhado, claim de custo vs recibo medido, ref fora de namespace,
relaxamento de policy global, escalada de budget (capado pelo teto global).

## Real-provider proof

- **Specialist-real (35/35, required mode):** os quatro especialistas
  instalados em venvs locais (`.venv-spark` 0.5.0, `.venv-api` 0.1.0
  @`1745f87`, `.venv-dd` 1.0.0rc1, `.venv-da` 0.2.0) — describe/health/
  execute live através do core, com fingerprints, receipts e verificação de
  hashes intactos.
- **Protocol-real:** toda a suíte offline roda os adapters por subprocesso +
  JSON sobre gravações regravadas das superfícies atuais.
- **Prova de ecossistema** (`tests/test_ecosystem_contracts.py`,
  `test_final_ecosystem_proof_chain`): plano de 4 nós — Doctor Data observe
  → Spark engineer (handoff consumido) → verificação independente pelo
  Doctor Data; Doctor API observe → API engineer → verificação independente
  pelo Doctor API; receipts filhos ligados ao plan run; `verify_run_hashes`
  limpo em todos os runs; `ExplainReport` completo em plano e filhos com
  spans de provider no trace.

## Benchmarks

- `scripts/bench/run_bench.py`: latência mediana/p90 com baseline
  (`scripts/bench/baseline.json`) e budget (`budget.json`), workspace
  sintético determinístico, caches isolados — gate local verde.
- `scripts/bench/run_context_economy.py`: direct vs mesh sobre o mesmo
  workspace sintético (404 arquivos): o mesh reduz o scan repetido pela
  metade (808 → 408 arquivos: cada engenheiro downstream varre ~2 arquivos
  em vez de 404) ao custo de bytes serializados agregados maiores (o
  handoff/evidência estruturados do observer). Tokens/modelo: `null`
  explícito (não mensurável offline). Resultado reportado honestamente —
  não é um gate de performance.

## Known limitations

- **CI não executada**: quota de GitHub Actions esgotada; gates 100% locais.
- O benchmark de economia prova redução de *varredura*, não de *bytes*:
  serialização handoff/evidência pode exceder a do scan direto.
- `complexity` não é medido em runs com `--from <plan>` — o arquivo fixa o
  perfil (decisão registrada; a avaliação existe no caminho de decomposição).
- Delta depende do `FingerprintStore`: cache desabilitado/descartado → sem
  dica (correto: nunca delta fabricado).
- Prova cross-forge exige api-forge `>=1745f87` — já em `main` (PR #34);
  releases 0.1.0 anteriores degradam com limitação em vez de consumir
  handoff.
- Snapshots/handoff dos Doctors viajam no ContextPack por design
  (`.forge-doctor*/` não é ignorado — é o que permite o baseline resolver).

## Deferred work

- ADR 0031/0032: surfaces A2A/MCP permanecem **decisão documentada** — o A2A
  experimental do Spark e o MCP local do Doctor API continuam fora do
  protocolo Forge até uma adoção deliberada.
- `main` CI verde: pendente da quota de Actions; os workflows estão prontos
  e os gates equivalentes rodaram localmente.

## Definition of Done (Phase 60)

| item | status | evidência |
|---|---|---|
| main CI green | **BLOCKED** | quota esgotada; gates locais verdes (abaixo) |
| versioning (core/adapters/matriz/fingerprints) | DONE | tabela acima; `ProviderSurfaceIdentity` |
| spark: snapshot corrente, drift green, mapping atual | DONE | `record --check` same; fixtures regravadas |
| api: handoff estável em main, sem feature branch | DONE | `1745f87` em `main` |
| doctor data/api integrados, handoff mapeado, verify | DONE | adapters + `verify` ops no manifest |
| arquitetura: hierarquia, nested, sem routing de domínio | DONE | architecture.md; planos aninhados testados |
| evidência Doctor↔Forge cross-domain com proveniência | DONE | `test_ecosystem_contracts.py` |
| economia federada, unknown≠zero, budget global | DONE | `EconomyRollup`; policy 10.2 |
| trace cross-provider + native refs | DONE | `NativeTrace`, `native_trace_ref` |
| 4 especialistas reais executam (local reproduzível) | DONE | 35/35 `real_provider` required |

## Status matrix (Phase 84)

| requisito | status | evidência | limitação |
|---|---|---|---|
| Mesh de capabilities federada | DONE | `graph --mesh`, `test_capability_graph.py` | — |
| Delta handoff `delta/v1` | DONE | `test_delta_handoff.py` (9) | cache off → sem dica |
| Economia federada | DONE | `test_plan_economy.py` (13) | tokens offline `null` |
| Trace federado | DONE | Wave F; explain `Native trace:` | spans internos ficam no especialista |
| Hierarquia de autoridade/policy | DONE | adversariais (20) | — |
| Proveniência + hash chain | DONE | `verify_run_hashes` em todos os runs | — |
| Ontologia + epistêmico lossless | DONE | ontology.md; `Confidence.UNKNOWN`→unknowns | — |
| Contratos versionados + drift | DONE | `record --check` 3 vias; schema regen | — |
| Segurança: dado ≠ instrução | DONE | Wave H + bundle forjado | — |
| Prova specialist-real ×4 | DONE | 35/35 required | venvs locais |
| Prova protocol-real (replay) | DONE | suíte offline inteira | — |
| Benchmarks (latência + economia) | DONE | run_bench, run_context_economy | economia não é gate |
| CI em main | **BLOCKED** | workflows prontos | quota de Actions esgotada |
| Documentação sincronizada | DONE | docs/*, README, ADR index | — |

## Veredito

**PARTIAL → implementação encerrada.** Tudo que era implementável foi
entregue e verificado localmente, incluindo a prova real dos quatro
especialistas. O ciclo só não fecha formalmente porque a Phase 85 proíbe
declarar completo com CI não executada — a quota de Actions é o único
bloqueio, externo ao código. Quando a quota voltar: rodar `ci.yml` +
`ecosystem-real.yml` no merge e revalidar este status.
