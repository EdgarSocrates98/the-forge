# ADR 0027 — Grafo de capabilities como estrutura de relações declaradas + observadas

- Status: aceito (2026-10-07)

## Contexto

O routing por sinais responde "quem pode", mas não sabia dizer "em que ordem"
nem "quem verifica quem": dois providers qualificados numa tarefa composta não
tinham uma ordem fundamentada em declaração, e a verificação independente não
tinha como descobrir quem declara `can_verify` sobre quê. A spec do ciclo 3
(Wave B) pede um grafo de capabilities — e o princípio do projeto exige que
cada aresta carregue status epistêmico e evidência: declaração de manifest e
observação do workspace não são o mesmo tipo de fato.

## Decisão

- **`CapabilityGraph/v1`** (`capability_graph.build_capability_graph`) com três
  fontes e nenhuma quarta: manifests em cache (providers, domínios,
  capabilities, ações, `relations.*`), o `WorkspaceDescriptor` (repositórios e
  tecnologias observadas) e nada mais — o grafo nunca executa provider nem
  infere relação não declarada.
- **Dois planos de verdade na mesma estrutura**: arestas `explicit` vêm de
  `capabilities[].relations` (`produces`/`consumes` sobre tipos de artefato;
  `requires`, `complements`, `conflicts`, `can_verify`, `can_review` sobre
  capabilities, com refs `cap.id` ou `provider/cap.id`) e das mecânicas
  (`in_domain`, `has_capability`, `has_action`); arestas `observed` vêm do
  workspace (`uses_technology` de arquivos de dependência, `relevant_to` do
  match de sinais). Toda aresta carrega `epistemic` e `evidence`.
- **Consumidores determinísticos**: o decompositor ordena o pipeline por
  `requires` e cadeias produces→consumes (regra `capability-graph`), recusa
  `conflicts` e ciclos como `ambiguous`; a verificação independente descobre
  verifiers via `can_verify`; o handoff filtra artifacts por `consumes`
  declarado. Nenhum consumidor trata a aresta como mais do que ela é —
  `can_verify` declarado não prova capacidade, só candidatura.
- **Alvos ausentes não quebram o grafo**: uma relação para capability fora do
  registry mantém a aresta e vira limitação `declared relation targets not in
  the registry` — declaração apodrecida é visível, não silenciada.

## Consequências

- O grafo é persistido (`capability-graph` em runs de plano) e inspecionável
  sem run (`theforge graph`, cache-only — Wave Q).
- Provider sem manifest em cache não tem suas declarações no grafo — a
  limitação `no cached manifest` diz isso em vez de fingir cobertura.
- O grafo é derivado por demanda, não materializado: rebuilds sobre o mesmo
  cache + descriptor são idênticos, e o artefato persistido é a prova do que o
  planner viu naquele run.
