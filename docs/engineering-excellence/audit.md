# Engineering Excellence — Baseline Audit

Data: 2026-10-12  
Branch de trabalho: `codex/evo-grill-2026-10-12`  
Escopo: oito Forjas em `E:\projetos\FORJAS`

## Método

Auditoria inicial combinou:

- leitura integral de `prompt_evo_grill.md`;
- inspeção de branch, commit e working tree;
- análise estrutural por graph memory;
- leitura de registries, contratos, docs, testes, adapters e entrypoints;
- pesquisa de práticas de skills composáveis, grill, TDD, task graph, review e retro.

Auditoria não executa rede, não usa credencial, não altera projeto auditado. Implementação posterior deve preservar esse limite.

## Baseline

| Repositório | Commit-base | Capacidades observadas | Estado inicial |
|---|---:|---|---|
| the-forge | `06b7d1c` | router, install, registry, policies, MCP, CLI, Portal adapter, doctors | forte; falta visão federada reproduzível |
| api-forge | `4ed0360` | contracts, runtime, context, SDD, economy, evals, observability | forte; falta paridade comparável |
| spark-forge-aws | `b554143` | cases, code intelligence, agents, registry, economy, evals | forte em especialidade AWS |
| spark-forge-azure | `59e25c0` | agents, code intelligence, decision, economy, graph, context, evals | forte em especialidade Azure |
| platform-forge | `17a6f45` | ops, live, agents, economy, graph, UI, analytics, token saving | ampla; fitness e blast radius precisam evidência unificada |
| forge-doctor-api | `c1dc3c3` | analyzers, verifiers, factory, benchmarks, CLI | forte em diagnóstico; publicação federada pendente |
| forge-doctor-data | `4975032` | diagnostic core, graph, context, evals, SQL/HCL/JS | forte em diagnóstico; contrato de capability pendente |
| forge-portal | `f1c0611` | Angular shell, API client, federation/install views, routes | útil; falta painel de evidência federada |

## Findings

1. Capacidades estão presentes. Duplicação de implementação seria desperdício.
2. Docs e ADRs já formam memória técnica local. Falta índice federado com estado, evidência, confiança, custo e próximo passo.
3. Registries locais já são autoridade. Auditoria deve projetar dados, não criar autoridade concorrente.
4. CLI, MCP e Portal existem em graus diferentes. Compatibilidade precisa declarar `supported`, `partial`, `unknown` e `unavailable`.
5. Testes, evals e benchmarks existem, mas comparação entre Forjas ainda depende de leitura manual.
6. Loop Factory CLI não está instalado neste ambiente. Spec e artefatos seguem contrato manual rastreável; instalação do binário fica como gap explícito.

## Evidence inventory

- The Forge: `docs/capabilities.md`, `docs/capability-negotiation.md`, `docs/ontology.md`, `docs/portable-installation/`, `factory/specs/`, `factory/reviews/`.
- API Forge: contracts, runtime, context, SDD, economy, evals e observability packages.
- AWS/Azure: registries, cases, routing, agentic/code intelligence, evals e economy.
- Platform: `GLOSSARY.md`, `CAPABILITIES.md`, ADRs e benchmarks.
- Doctors: analyzers, verifiers, findings, graphs e test suites.
- Portal: install/federation screens e API client.

## Limits

- Graph index Azure, Platform, Doctor API/Data contém arquivos parcialmente parseados. Operações citando esses caminhos exigem cobertura explícita.
- Screenshot modificado em Portal já existia antes desta branch; permanece intocado.
- CI, credenciais remotas e estado GitHub ainda não foram executados nesta onda.
