# Cycle 5.1 — Ecosystem Expansion Validation

**Status:** IMPLEMENTATION COMPLETE / LOCAL_GATES_GREEN /
REMOTE_VALIDATION_BLOCKED (GitHub Actions quota — owner decision; not a code
failure). Fechamento formal aguarda CI remota em `main`.

Branch `devin/cycle51-ecosystem` · um commit por wave (W0–W6).

## 1. Executive Summary

O prompt exigia provar que o ecossistema cresce de quatro para seis
especialistas **sem mudança fundamental de arquitetura e sem condicionais
hardcoded no core** (`if forge == "platform-forge":` é o antipadrão proibido).
Foi entregue: dois adapters novos (`theforge-sparkforge-azure-adapter`,
`theforge-platformforge-adapter`), conformidade federada sobre os seis, a
escada de maturidade derivada de evidência, benchmarks cloud-aware
adversariais (B16–B25) e um teste de onboarding genérico (`example-forge`) com
gate AST de zero-hardcode.

**Única mudança de produção no core em todo o ciclo:** cinco linhas genéricas
em `capability_graph.produces_consumes_order` — relações `can_verify`/
`can_review` passam a ordenar o verificador depois do capability nomeada
(antes só `verified_by` ordenava). Nenhum provider é nomeado; a correção vale
para qualquer ecossistema. A auditoria W5 (AST sobre `src/theforge`) confirma
zero referência a provider-ids, módulos nativos ou domínio.

## 2. Especialistas e adapters

| Provider | Adapter | Especialista | Janela | Maturidade |
|---|---|---|---|---|
| `spark-forge-aws` | `adapters/sparkforge_aws` | `sparkforge-aws` | `>=0.5.0,<0.6.0` | VERIFICATION_READY |
| `spark-forge-azure` | `adapters/sparkforge_azure` | `sparkforge-azure` | `>=0.1.0,<0.2.0` | EXECUTION_READY |
| `api-forge` | `adapters/apiforge` | `apiforge` | `>=0.1.0,<0.2.0` | VERIFICATION_READY |
| `platform-forge` | `adapters/platformforge` | `platformforge` | `>=0.1.0,<0.2.0` | EXECUTION_READY |
| `forge-doctor-data` | `adapters/doctordata` | `forge-doctor-data` | `>=1.0.0rc1,<2.0.0` | EXECUTION_READY |
| `forge-doctor-api` | `adapters/doctorapi` | `forge-doctor-api` | `>=0.2.0,<0.3.0` | EXECUTION_READY |

A escada é **derivada, nunca declarada** (`tests/test_federation_conformance.py`):
DISCOVERABLE (describe ok) → CONTRACT_COMPATIBLE (taxonomia+limites) →
SURFACE_VALIDATED (fingerprint de superfície gravado) → PLANNABLE (≥1 cap
read-only roteável) → EXECUTION_READY (≥1 cap.action com gravação de execute
— prova ponta-a-ponta) → VERIFICATION_READY (≥1 capability com verificador no
grafo federado). Cobertura de fixture não é prontidão; EXECUTION_READY exige
uma prova, não exaustão.

Capabilities expostas: Spark AWS 15 · API 2 · Doctors 4 · Spark Azure 5 ·
Platform 9 = **35** (catálogo em `docs/capabilities.md`, travado pelo teste
`test_capability_catalog_doc.py` contra o describe replay).

## 3. Reality manifest dos seis

`docs/reality/specialist-reality.json` regenerado por
`scripts/reality/collect.py` (SPECIALISTS estendido de 4 para 6, por convenção
`.venv-<tail>`):

| Specialist | SHA instalado | Versão | Surface hash | Relação c/ origin/main | Status |
|---|---|---|---|---|---|
| spark-forge-aws | `828827d7` | 0.5.0 | `49f6db89cea5` | diverged | snapshot_fresh_install_diverged |
| api-forge | `1745f872` | 0.1.0 | `b2be601baaab` | diverged | snapshot_fresh_install_diverged |
| forge-doctor-data | `3a8d7a56` | 1.0.0rc1 | `1e2b1f4293da` | same | fresh |
| forge-doctor-api | `035b635` | 0.2.0 | `ad03aa4f33d7` | diverged | snapshot_fresh_install_diverged |
| spark-forge-azure | `6e74262e` | 0.1.0 | `7ff22053153b` | descendant | snapshot_fresh_install_ahead |
| platform-forge | `0aee5c6f` | 0.1.0 | `f7aa77bb67f4` | same | fresh |

Leitura honesta: os snapshots empacotados casam com os especialistas
**instalados**; o drift observado é de checkout vs `origin/main`, preservado
em vez de escondido. `spark-forge-azure` roda um descendente da main
publicada; `platform-forge` e `forge-doctor-data` estão `fresh`.

## 4. Adapters novos (W1, W2)

Ambos seguem o padrão canônico (byte-idêntico `_shell.py`, stdlib-only, sem
import de `theforge`, bridge filho como único módulo que importa o
especialista):

- **Spark Forge Azure** — seams `sdd.checks.check`, `sdd.status.status`,
  `azure.pipeline.run_case`, `fabric.pipeline.run_fabric_case`,
  `doctor.run`. Sem equivalência falsa AWS↔Azure: nenhuma capability alias
  (`azure.access-diagnose` ≠ `lakeformation.access-analysis`). Evidência de
  `evidence_paths` re-vinculada ao sha256 verificado do arquivo estagiado.
  Recusas `SFA-*` preservadas; indisponível → `SPARKFORGE_AZURE-ADAPTER-UNAVAILABLE`.
- **Platform Forge** — nove seams `analyze_*` + `capability_manifest`
  (manifest nativo `platformforge/capability-manifest/v3`). `secrets.scan`
  varre a árvore inteira como **input**, mas sinaliza com nomes de alto sinal
  (`.env`, `*.pem`, …) — um glob catch-all seria rejeitado como sinal de
  routing. Facts citam `location`/`attrs.file` → evidência re-vinculada ao
  sha256 estagiado. Recusas `PF-*` viram findings nomeadas; indisponível →
  `PLATFORMFORGE-ADAPTER-UNAVAILABLE`.

Documentos nativos gravados verbatim (canonical JSON) em
`native/<capability>.json` com sha256; campos não reconhecidos preservados no
artefato.

## 5. Federação, maturidade e planejamento (W3)

`test_federation_conformance.py` (24 testes) prova sobre os seis adapters:
manifests válidos, ids estáveis/namespaced, fechamento produces→consumes,
arestas cross-forge resolvidas, grafo determinístico, referências de
verificador, `accepts` nos que aceitam handoff, tipos de artefato Azure/
Platform namespaced e não consumidos especulativamente, ordenação
determinística de composições de seis providers, verificador depois do
verificado, capabilities Azure/Platform endereçáveis e **rejeição
adversarial** de capability AWS-only atribuída a provider Azure
(`PlanNode(role="standalone")` + `ExecutionPlan(status="validated")` +
`check_plan` → violação).

Achado real de dogfooding incorporado: `_surface_diff` normalizava `tools`
assumindo dict — Azure/Platform expõem listas; o helper agora normaliza
dict/lista-de-nomes/lista-de-objetos antes de comparar. Fixture do Doctor
Data regravada (drift ambiental: `AWS001` mudou com a versão do aws-cli da
máquina — conteúdo, não forma).

## 6. Benchmarks B16–B25 (W4)

`scripts/bench/run_scenarios.py` — dez cenários novos, todos verdes (25/25):
descoberta/planejamento Platform, composições API→Platform e Spark→Platform,
seleção cloud-aware AWS vs Azure, ambiguidade de nuvem, incompatibilidade
cross-cloud, artefato Spark portátil e onboarding de Forge desconhecido.
B22 (ambiguidade) resolve `ambiguous` — nunca um chute; B23 prova que o
planner não mistura artefatos incompatíveis entre nuvens.

## 7. Onboarding genérico + auditoria (W5)

`tests/test_generic_onboarding.py` (7 testes) onboards `example-forge` —
provider desconhecido dirigido por `tests/fixtures/providers/fixture_forge.py`
+ `fixture-example.json` — pelo caminho normal (describe → graph → plan →
execute replay), sem nenhuma linha de código específica. O gate AST percorre
`src/theforge` e falha se qualquer provider-id real, módulo nativo ou nome de
domínio aparecer fora de docstring/comentário.

Auditoria do ciclo sobre `src/theforge`: uma única mudança (5 linhas,
`capability_graph.py`), genérica. Nomes de provider restantes no core estão só
em docstrings (`contracts/identity.py`, `contracts/types.py`,
`registry/surface.py`).

## 8. Verificação

| Suite | Resultado |
|---|---|
| Conformidade federada (6 adapters) | 24/24 |
| Adapter shell (6 adapters, byte-identity `_shell.py`) | verde |
| Catálogo ↔ describe (6 adapters) | verde (35 capabilities) |
| Onboarding genérico | 7/7 |
| Real providers (6 venvs live) | 48/48 |
| Benchmarks B01–B25 | 25/25 |
| `ruff check` + `ruff format` | limpo |
| `audit_assets.py` (paridade de hosts) | limpo |

CI remota: `REMOTE_VALIDATION_BLOCKED` — quota de GitHub Actions esgotada na
conta (decisão do owner; nenhum resultado falsificado).

## 9. Prova do princípio

> 4 specialists → 6 specialists não exige mudança fundamental de arquitetura.

Evidência: zero condicionais por provider no core; os dois adapters nasceram
pela mesma receita dos quatro originais (catálogo positivo + snapshot +
`_shell.py` + bridge de seams); o grafo federado compõe seis providers
deterministicamente; e um Forge completamente desconhecido (`example-forge`)
onboards pelo mesmo caminho. O freeze criterion do prompt é atendido: os seis
estão em discovery + surface recognition + capability ingestion +
compatibility classification + planning participation; execução real provada
end-to-end via replay nos seis e live nos seis venvs locais.

## 10. Limitações declaradas

- `VERIFICATION_READY` para Azure/Platform exige que algum provider declare
  `can_verify`/`can_review` sobre suas capabilities — hoje nenhum declara
  (classificação honesta, não defeito).
- `spark-forge-azure` roda um checkout descendente da `origin/main`
  (`snapshot_fresh_install_ahead`); os três checkouts divergentes dos
  especialistas anteriores permanecem classificados como tal.
- O caso live do Azure usa `azure.access-diagnose` (que expõe
  `evidence_paths`) para provar hash-binding; `sdd.check` tem evidência de
  run sem refs de arquivo.
- CI remota não rodou (quota); todos os gates citados são locais.
