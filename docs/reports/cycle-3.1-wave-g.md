# Cycle 3.1 — Wave G: contratos compartilhados, interop externa, ontologia e identidade

Escopo: Phases 27–30 (auditoria de contratos, decisão forge-contracts,
non-goal do kernel, Forge Protocol vs A2A/MCP) e 69–79 (decisões A2A/MCP,
ontologia, epistemic vocabulary, tradução lossless, proveniência, semântica
de hash, hierarquia de runs, invalidação por fingerprint de superfície).

Wave de decisão e documentação — nenhum contrato mudou: o trabalho foi
auditar o que existe, escolher o que **não** construir e fixar as regras
que o código já implementa porém não declarava.

## G.1 — Decisão de contratos compartilhados (Phases 27–29)

Auditoria das implementações irmãs (Phase 27):

- `theforge/contracts/` — protocolo (fonte: dataclasses → `schemas/`).
- `forge_doctor_data/contracts/` + `sdk.py` — HandoffBundle e modelos de scan.
- `forge_doctor_api/core/models.py` + `handoff/` — `Evidence`, `Finding`,
  `UnknownFact`, bundle, envelope, delta.
- `apiforge`/`sparkforge_aws` — modelos internos traduzidos pelo adapter.

**Decisão ([ADR 0031](../adr/0031-shared-contracts.md)): opção B — shared
schema repository.** `schemas/` é formalmente a superfície de
interoperabilidade: conformidade se prova contra o JSON Schema publicado,
não contra o Python alheio. Opção C (pacote `forge-contracts` stdlib-only)
fica revisitável se surgir uma quinta implementação de protocolo — hoje a
tradução adapter-lado continuaria existindo e o pacote só adicionaria
acoplamento de release entre quatro repos com ciclos independentes. Opção D
(`forge-kernel` com routing/planning/memory/runtime) vetada pela Phase 29 —
reforça o [ADR 0004](../adr/0004-no-forge-kernel-yet.md).

## G.2 — Interoperabilidade externa (Phases 30, 69–70)

**Decisão ([ADR 0032](../adr/0032-external-protocol-interop.md))**: Forge
Protocol permanece o protocolo nativo; nenhuma dependência A2A/MCP no core.

- **MCP**: complementar, no nível do provider. Doctor API já expõe surface
  MCP local (`handoff/mcp.py` + `mcp_server.py`); especialistas podem
  publicar tools via MCP sem o core saber — as superfícies coexistem.
- **A2A**: deferido. Se um especialista precisar falar com agentes
  externos, a ponte é adapter do especialista (A2A task → op nativa) — o
  Spark Forge já tem surface experimental (`A2A-SPEC-REVIEW.md` upstream).

## G.3 — Ontologia e epistemologia (Phases 71–73)

`docs/ontology.md` fixa o vocabulário compartilhado:

- **Conceitos**: Evidence, Finding, Capability, Unknown, Decision,
  Artifact, Graph (3 níveis), Receipt — com dono por conceito.
- **Vocabulário epistêmico** (`confirmed|observed|inferred|proposed|
  unresolved`): eixo é *como o fato foi obtido*, não a confiança do
  emissor — tabela de mapeamento por provider.
- **Tradução lossless** (Phase 73): campo sem equivalente é preservado
  verbatim em `limitations` (`native confidence: low`); ausência na fonte
  é ausência no protocolo (nunca default fabricado); aproximações são
  declaradas. Os translates dos dois Doctors já implementam as três regras
  — cobertas por `test_contracts.py` e testes de adapter.

## G.4 — Proveniência, hash e identidade (Phases 74–76)

Nova seção `protocol.md` §Proveniência e identidade:

- **Cadeia** (Phase 74): Doctor finding → handoff item (`origin`) →
  evidence `derived_from` (check `handoff-provenance`) → `VerifyRequest`
  verbatim → síntese citando node ids. Cada elo cita `sha256` do anterior
  em vez de copiar.
- **Semântica de hash** (Phase 75): `sha256_of` cobre o contrato serializado
  completo — `schema` + `producer` inclusos — então hash liga conteúdo,
  versão do schema e produtor por construção. Hash é integridade, **nunca
  autoria** (autoria é trust/identity, não digest).
- **Hierarquia de runs** (Phase 76): raiz `kind=plan` → nó `kind=node`
  (`parent_run`, `plan_node`) → run nativo (alcançável por
  `ProviderReceipt.ref`/`NativeTrace.ref`, nunca fundido). `explain`
  navega os dois sentidos.

## G.5 — Invalidação por superfície (Phases 77–79)

Documentado em `capabilities.md` §Identidade de superfície e invalidação —
regra uniforme: **mudança de superfície não herda nada**.

| Superfície | Mecanismo | Já implementado em |
|---|---|---|
| Registry cache | digest da entry + sha256 do manifest + ambos fingerprints + protocolo negociado | `registry._load_cached` |
| Provider performance | escopo `(provider, capability, surface)`; fingerprint novo = histórico novo | `ProviderPerformance.score` |
| Capability graph | reconstruído por comando de records verificados — sem snapshot persistido | `build_capability_graph` |
| Snapshots nativos | `native_surface_fingerprint` comparado ao especialista instalado | adapters (manifests) |

## Prova

- Suite offline verde nos arquivos tocados; docs-only além dos ADRs.
- As regras documentadas correspondem a testes existentes:
  `test_provider_performance*` (escopo por fingerprint), testes de
  `handoff-provenance`, `test_schemas.py` (conformidade publicada),
  testes de explain aninhado (hierarquia de runs).
- Nenhum comportamento alterado; nenhuma dependência adicionada;
  `pyproject.toml` intocado (ADR 0032 honrado).

## Arquivos

- `docs/adr/0031-shared-contracts.md`, `0032-external-protocol-interop.md`
  (novos), `docs/adr/README.md` (índice)
- `docs/ontology.md` (novo), `docs/protocol.md` (§Proveniência e
  identidade), `docs/capabilities.md` (§Identidade de superfície),
  `README.md` (índice de docs)
