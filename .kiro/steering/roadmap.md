# Roadmap

## Overview
O Cycle 2 de The Forge transforma o core determinístico do Cycle 1 (Forge Protocol v1 + registry/routing/context/runs/security locais, provado só contra fixtures) em base comprovada contra Spark Forge REAL e API Forge REAL, sem overengineering. Fonte: `prompt_evo_passo1.md`; auditoria de código em 2026-10-02 (core, `spark-forge-aws`, `api-forge`).

## Approach Decision
- **Chosen**: decomposição por wave em 5 specs, ordem REALITY → VALIDATION → HARDENING → REAL PROVIDERS → CONTEXT → CROSS-FORGE.
- **Why**: o requisito único inicial (`cycle2-reality-hardening`, 18 áreas) carregava 5+ fronteiras independentes; o design review gate exige split. Hardening primeiro porque adapters reais dependem de invariantes de contrato, policy e isolamento.
- **Rejected alternatives**: spec única guarda-chuva (design gigante, viola gate de fronteiras); só Wave A sem specs futuras (perde rastreabilidade dos requisitos já revisados).

## Scope
- **In**: hardening de contratos/protocol/routing/trust/env/policy + CI; adapters reais Spark/API e conformance; Context Intelligence v2 + economy + baseline de performance; contratos multi-provider e prova cross-forge; explicabilidade/erros/reprodutibilidade; paridade agentic, documentação, ADRs, relatório final.
- **Out**: web UI, server, database, broker, orquestrador distribuído, Kubernetes, cloud control plane, vector DB, marketplace/instalador automático, remote registry, forge-kernel, LLM routing obrigatório, sandbox de SO obrigatório.

## Constraints
Runtime stdlib-only (Python >= 3.11, 0 deps runtime); integração só via Forge Protocol (subprocess + JSON); routing determinístico (ambíguo ≠ chute); nenhum sucesso sem `ExecutionResult` válido; tudo persistido passa por `security.redact`; contratos `theforge/<Name>/v1` com `schemas/` regenerado; mudanças em repositórios filhos mínimas e aceitas pelo dono. API Forge exige Python 3.12 (ausente nesta máquina): testes de integração pulam com motivo explícito.

## Boundary Strategy
- **Why this split**: cada spec tem um seam próprio — core governance (A), fronteira com especialistas (B), seleção de contexto/economy (C), composição multi-provider (D), assets/documentação (E).
- **Shared seams to watch**: novos códigos de erro (A cria, D formaliza taxonomia); contratos de `ExecutionResult`/evidence (A valida, B produz via adapters, D encadeia); policy/RiskAssessment (A) consumido por B e D; ContextPack (A valida, C evolui); documentação de protocolo tocada por A, B, C. B e C rodam em paralelo e editam os mesmos pontos: contrato de manifest (`Capability`, `ForgeManifest`), `contracts/codes.py`, `schemas/` (incl. `ForgeManifest.schema.json`), `forger/orchestrator.py`, `cli/render.py` e `docs/protocol.md` — regra: quem fizer merge por último regenera `schemas/` e reroda a paridade. `Evidence.hash` = sha256 do conteúdo exato em `location.path` (faixa de linhas quando houver), definido por B e C. ADRs congelados: 0014/0017 B, 0015/0016 C, 0018/0019 D, 0020 E. `docs/errors.md` (D) é a lista canônica de códigos. Quem subir `theforge.__version__` adiciona a linha da matriz em `docs/versioning.md` (B).

## Specs (dependency order)
- [x] cycle2-reality-hardening -- Wave A: invariantes de contrato, protocol adversarial, routing resistente a spam, trust/cache/identidade, env/cwd, policy/risk foundation, CI e quality gates. Dependencies: none
- [x] real-provider-integration -- Wave B: adapters reais Spark Forge e API Forge, conformance offline/integração, versionamento/compatibilidade, taxonomia de capabilities. Dependencies: cycle2-reality-hardening
- [x] context-intelligence-v2 -- Wave C: tiers de contexto, git read-only, cache de fingerprints, TOCTOU, economy material, telemetria, baseline de performance. Dependencies: cycle2-reality-hardening
- [x] cross-forge-foundation -- Wave D: ExecutionPlan, WorkspaceDescriptor, grafo mínimo, VerificationResult, handoff estruturado, prova real Spark→API, explain/erros/reprodutibilidade. Dependencies: real-provider-integration, context-intelligence-v2
- [x] agentic-maintainability -- Wave E: paridade de assets agentic, CLAUDE.md/AGENTS.md, documentação/ADRs consolidados, relatório final do ciclo. Dependencies: cross-forge-foundation
