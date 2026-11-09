# Phase 2 — Ownership Matrix

Regra: cada capacidade tem um único dono de implementação. Os consumidores usam
contratos/adapters finos e não duplicam motores especializados.

| Capacidade | Dono | Consumidores | Não fazer |
|---|---|---|---|
| Context capsule/ref, classificação e policy | Platform Forge para runtime de plataforma; contratos compartilhados no The Forge | AWS, Azure, API, Agent Bridge | copiar gateway inteiro em cada Forge |
| Applicability de knowledge pack | Platform Forge | agentes e adapters | inferir aplicabilidade por domínio apenas |
| Freshness de fontes Azure | Spark Forge Azure | Azure adapter/Portal | tratar ausência de data como fresh |
| Knowledge retrieval e change-control de API | API Forge | API adapter/Portal | criar busca paralela no adapter |
| Contratos Obsidian | The Forge | Product Forge, quatro adapters, Portal | redefinir schemas em cada Forge |
| Formatos Obsidian, segurança de vault e sync planner | `forge_obsidian` (distribuição técnica neutra `forge-obsidian`, fonte canônica no Product Forge, commit `4cdf153`) | Product Forge, Portal e adapters finos | fazer cada Forge escrever ou sincronizar vault próprio |
| Motor AWS Spark/Glue/EMR/Athena/Iceberg/LF | Spark Forge AWS | AWS adapter/MCP | alterar o caminho operacional comprovado |
| Motor Azure/Databricks/Fabric/ADF/Event Hubs | Spark Forge Azure | Azure adapter/MCP | depender do Product Forge |
| API IR/contratos/graph | API Forge | API adapter/Code Atlas | tratar Obsidian como contrato autoritativo |
| Grafo de código e relações documentais | Code Atlas Forge | Portal, adapters | criar símbolos de código para notas |
| Autorização inter-Forge/contexto externo | Forge Agent Bridge | Portal, adapters, The Forge | confiar em texto de nota ou URI hash |
| Telemetria sanitizada | Forge Lens | Portal/adapters/sync | registrar corpo completo da nota |
| UI Portal | Forge Portal | usuários | criar um segundo frontend |
| Orquestração/catalogação/MCP | The Forge | Portal e hosts | replicar engines especialistas |

## Ownership de contratos

- `theforge/Obsidian*` e envelopes de proveniência: The Forge.
- Parser/Writer/Scanner/Sync: `forge_obsidian` é a implementação técnica
  canônica, extraída e testada dentro do wheel do Product Forge; o import path
  `product_forge.knowledge.obsidian` permanece apenas como fachada de
  compatibilidade. A publicação como distribuição técnica separada e a adoção
  pelos demais adapters continuam gates explícitos.
- Contratos de domínio (Spark, Azure, API, Platform): cada Forge especialista.
- Relações documentais: Code Atlas (`context.obsidian` body-free), por extensão
  aditiva ao grafo existente.
- Receipts/telemetria: Forge Lens (`adapters.obsidian`) e os receipts nativos de cada Forge, sem
  armazenar payload sensível por padrão.

